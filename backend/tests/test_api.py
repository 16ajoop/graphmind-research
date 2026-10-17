"""The HTTP API: health, 503 without FalkorDB, upload -> agents -> papers, views, and the agent over server-sent events.
The LLM and the embedder are faked so the test needs neither Ollama nor a model. Run: pytest tests/test_api.py -v"""
import hashlib
import json
import math
import re
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.agent import llm
from app.api import main
from app.docs.docstore import DocStore
from app.graph.client import get_db, graph_for
from app.graph.gold_loader import load_gold

ROOT = Path(__file__).resolve().parents[2]
PDFS = sorted((ROOT / "corpus" / "pdf").glob("*.pdf"))


def fake_embed(texts, kind):
    out = []
    for t in texts:
        v = [0.0] * 64
        for w in re.findall(r"[a-z]+", t.lower()):
            v[int(hashlib.md5(w.encode()).hexdigest(), 16) % 64] += 1.0
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        out.append([x / n for x in v])
    return out


def drop(name):
    if f"ws_{name}" in get_db().list_graphs():
        get_db().select_graph(f"ws_{name}").delete()


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    mp = pytest.MonkeyPatch()
    chroma = tmp_path_factory.mktemp("chroma")
    mp.setattr(main, "DocStore", lambda path, ws: DocStore(str(chroma), ws, embed=fake_embed))
    mp.setattr(main, "UPLOAD_DIR", tmp_path_factory.mktemp("uploads"))
    mp.setattr(llm, "OLLAMA_URL", "http://127.0.0.1:1")           # no model: template answers, keyword fallbacks
    for name in ("apitest", "apigold"):
        drop(name)
    load_gold(graph_for("apigold"), ROOT / "ground_truth" / "gold_graph.json")
    with TestClient(main.app) as c:
        yield c
    main.stop_agents()                                               # before deleting: agents would recreate the graph
    for name in ("apitest", "apigold"):
        drop(name)
    mp.undo()


def test_health_and_503_without_falkordb(client, monkeypatch):
    assert client.get("/api/health").json()["falkordb"] is True
    monkeypatch.setattr(main, "falkordb_up", lambda: False)
    assert client.get("/api/health").status_code == 503
    assert client.get("/api/workspaces/apigold/papers").status_code == 503
    assert client.get("/api/workspaces").status_code == 503


def test_unknown_workspace_is_404_and_not_created(client):
    assert client.get("/api/workspaces/nosuchspace/papers").status_code == 404
    assert "ws_nosuchspace" not in get_db().list_graphs()


def test_upload_runs_the_agents_and_fills_the_graph(client):
    # P05 writes "GW-QA [3]": that citation anchor is what tells the graph GW-QA in P08's table is GraphWalker-QA.
    files = [("files", (p.name, p.read_bytes(), "application/pdf")) for p in PDFS if p.name[:3] in ("P03", "P05", "P08")]
    jobs = client.post("/api/workspaces/apitest/papers", files=files).json()["jobs"]
    assert len(jobs) == 3
    deadline = time.time() + 120
    while time.time() < deadline:
        board = client.get("/api/workspaces/apitest/jobs").json()
        if all(j["status"] in ("done", "failed") for j in board):
            break
        time.sleep(0.5)
    assert [j["status"] for j in board] == ["done"] * 3 and all(len(j["history"]) == 4 for j in board)
    papers = {p["title"].split(":")[0]: p["id"] for p in client.get("/api/workspaces/apitest/papers").json()}
    assert set(papers) == {"GraphWalker-QA", "TriHop-Bench", "Revisiting Graph Gains"}
    rel = client.get("/api/workspaces/apitest/pair", params={"a": papers["GraphWalker-QA"],
                                                             "b": papers["Revisiting Graph Gains"]}).json()
    assert rel["citations"][0]["intent"] == "reproduces"
    detail = client.get(f"/api/workspaces/apitest/papers/{papers['Revisiting Graph Gains']}").json()
    assert detail["results"] and any(c["intent"] == "reproduces" for c in detail["cites"])


def test_analysis_views_on_the_gold_graph(client):
    lb = client.get("/api/workspaces/apigold/leaderboard",
                    params={"dataset": "ds-kaveri", "split": "3-hop", "metric": "metric-em"}).json()
    assert (lb[0]["method"], lb[0]["value"]) == ("GraphFuse", 46.3)
    options = client.get("/api/workspaces/apigold/leaderboard/options").json()
    assert {"dataset": "ds-trihop", "split": "4-hop", "metric": "metric-em"}.items() <= {
        k: v for o in options if o["dataset"] == "ds-trihop" and o["split"] == "4-hop" for k, v in o.items()}.items()
    claims = client.get("/api/workspaces/apigold/claims").json()
    assert any(c["relation"] == "CONTRADICTS" for c in claims["conflicts"]) and len(claims["sota"]) == 2
    cites = client.get("/api/workspaces/apigold/citations").json()
    assert [(m["citing"], m["paper"], m["score"]) for m in cites["missing"]] == [("P12", "P06", 10), ("P12", "P04", 5)]
    assert cites["stale"][0]["paper"] == "P10"
    people = client.get("/api/workspaces/apigold/people").json()
    assert people["bridges"][0]["author"] == "Lena Fischer"
    graph = client.get("/api/workspaces/apigold/graph/library").json()
    assert len(graph["nodes"]) == 16 and len(graph["edges"]) == 49


def test_ask_streams_every_step_and_remembers(client):
    sid = client.post("/api/workspaces/apigold/sessions", json={"title": "demo"}).json()["id"]
    with client.stream("POST", f"/api/workspaces/apigold/sessions/{sid}/ask",
                       json={"question": "Is HopLens really state of the art?"}) as r:
        events = [json.loads(line[6:]) for line in r.iter_lines() if line.startswith("data: ")]
    steps = [e["step"] for e in events]
    assert steps[0] == "understand" and steps[-1] == "final" and "run_tools" in steps
    final = events[-1]
    assert any("GraphFuse reports 46.3" in f["text"] for f in final["facts"])
    history = client.get(f"/api/workspaces/apigold/sessions/{sid}").json()["history"]
    assert history[0]["question"] == "Is HopLens really state of the art?" and history[0]["intent"] == "sota"
    client.post(f"/api/workspaces/apigold/sessions/{sid}/insights", json={"text": "HopLens missed GraphFuse",
                                                                           "about": ["m-hoplens"]})
    assert client.get(f"/api/workspaces/apigold/sessions/{sid}").json()["insights"][0]["text"] == "HopLens missed GraphFuse"
