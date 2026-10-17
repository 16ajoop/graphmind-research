# Step 35: the HTTP API (FastAPI)

Save as `docs/prompts/step35.md` and tell Claude Code: "Do docs/prompts/step35.md".
Tested on FalkorDB 6.0.1: `pytest -q` gives 58 passed (53 before + 5 API tests).

## What it serves

| Route | What the UI uses it for |
|---|---|
| `GET /api/health` | Health dot: FalkorDB, Ollama, which workspaces have agents running. 503 when FalkorDB is down. |
| `GET/POST /api/workspaces` | Workspace switcher |
| `POST /api/workspaces/{ws}/papers` (multipart, many PDFs) | Upload: saves the files, creates one Job per file, starts the four agents for the workspace |
| `GET .../jobs` | Pipeline board (poll every second) |
| `GET .../papers`, `GET .../papers/{id}` | Library list; paper panel (citations with intent and sentence, claims, results) |
| `GET .../graph/library` | Library map (all papers, CITES edges with intent) |
| `GET .../entities` | Pickers (papers, methods, datasets, authors) |
| `GET .../leaderboard/options`, `GET .../leaderboard?dataset=&split=&metric=` | Leaderboards |
| `GET .../pair?a=&b=` | Compare two papers |
| `GET .../claims` | Disagreements: contradicts/qualifies, supports, sota claims beaten by numbers |
| `GET .../citations` | Missing and stale citations, external hubs |
| `GET .../gaps`, `GET .../people` | Research gaps; influential papers, bridge authors, groups |
| `GET/POST .../sessions`, `GET .../sessions/{sid}` | Sessions: questions with answers, saved insights |
| `POST .../sessions/{sid}/ask` | The agent, streamed as server-sent events: one event per step, the last is `final` with answer, facts and evidence |
| `POST .../sessions/{sid}/insights`, `GET .../sessions/{sid}/whats-new` | Memory |
| `GET .../eval` | Scorecard (synthetic corpus only) |

Every route checks FalkorDB first with a 1-second ping and answers 503 if it is down: that is the "remove FalkorDB"
moment in the demo video.

## The prompt for Claude Code

Create these three files with EXACTLY the code below (`backend/app/api/__init__.py` is empty). Then:
1. From backend/ run `pytest -q`. Expect 58 passed.
2. Start the server: `python -m uvicorn app.api.main:app --port 8000` and in a second terminal check
   `curl http://localhost:8000/api/health` and `curl http://localhost:8000/api/workspaces`. Stop the server.
3. README: add "Run the API: `python -m uvicorn app.api.main:app --port 8000` (from backend/)" under the run commands.
4. Explain: how the 503 check works; how an upload becomes jobs and starts the agents; why the ask route streams
   server-sent events instead of returning one JSON. Then stop.

If app/config.py names settings differently (falkordb_host, falkordb_port, ollama_url, chroma_path, upload_dir,
workers_per_stage), `_setting()` falls back to the environment variables from .env, so no change is needed.

### backend/app/api/main.py

````python
"""HTTP API for the React UI. Every route reads FalkorDB; if FalkorDB is down, every route answers 503.

Run from backend/:  uvicorn app.api.main:app --port 8000
The UI calls /api/... and Vite forwards it here (frontend/vite.config.ts).
"""
import json
import os
import re
import shutil
import threading
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import redis
from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from app.agent import memory, pipeline, workflow
from app.config import settings
from app.docs.docstore import DocStore
from app.eval_extraction import score
from app.graph.analysis import Analysis
from app.graph.client import UnknownWorkspace, get_db, graph_for, list_workspaces

BACKEND = Path(__file__).resolve().parents[2]
ROOT = BACKEND.parent


def _setting(name: str, default):
    """Read a value from app.config.settings if it has it, else from the environment (.env), else the default."""
    value = getattr(settings, name, None)
    return value if value not in (None, "") else os.getenv(name.upper(), default)


FALKOR_HOST = _setting("falkordb_host", "localhost")
FALKOR_PORT = int(_setting("falkordb_port", 6379))
OLLAMA_URL = _setting("ollama_url", "http://localhost:11434")
CHROMA_PATH = str(_setting("chroma_path", BACKEND / "chroma_data"))
UPLOAD_DIR = Path(_setting("upload_dir", BACKEND / "uploads"))
UPLOAD_DIR = UPLOAD_DIR if UPLOAD_DIR.is_absolute() else BACKEND / UPLOAD_DIR
WORKERS = int(_setting("workers_per_stage", 1))
ONTOLOGY = json.loads((ROOT / "ontology.json").read_text(encoding="utf-8"))

# Read-only queries behind the UI views (the analysis queries themselves are in app/graph/analysis.py).
VIEW_Q = {
    "paper": """
        MATCH (p:Paper {id: $id})
        OPTIONAL MATCH (a:Author)-[w:WROTE]->(p)
        WITH p, a, w ORDER BY w.position
        RETURN p.id AS id, p.title AS title, p.year AS year, p.published AS published, p.abstract AS abstract,
               p.in_library AS in_library, collect(a.name) AS authors""",
    "paper_cites": """
        MATCH (p:Paper {id: $id})-[c:CITES]->(q:Paper)
        RETURN q.id AS id, q.title AS title, q.in_library AS in_library, c.intent AS intent, c.contexts AS contexts""",
    "paper_cited_by": """
        MATCH (q:Paper)-[c:CITES]->(p:Paper {id: $id})
        RETURN q.id AS id, q.title AS title, c.intent AS intent, c.contexts AS contexts""",
    "paper_claims": """
        MATCH (p:Paper {id: $id})-[:MAKES]->(c:Claim)
        OPTIONAL MATCH (c)-[:ABOUT]->(x)
        RETURN c.id AS id, c.text AS text, c.type AS type, collect(x.name) AS about""",
    "paper_results": """
        MATCH (p:Paper {id: $id})-[:REPORTS]->(r:Result)-[:OF_METHOD]->(m:Method), (r)-[:ON_DATASET]->(d:Dataset),
              (r)-[:MEASURED_BY]->(mt:Metric)
        RETURN m.name AS method, d.name AS dataset, r.split AS split, mt.name AS metric, r.value AS value,
               r.origin AS origin, r.setting AS setting
        ORDER BY dataset, split, method""",
    "library_graph": """
        MATCH (p:Paper)
        RETURN p.id AS id, p.title AS title, p.year AS year, p.in_library AS in_library""",
    "library_cites": """
        MATCH (a:Paper)-[c:CITES]->(b:Paper)
        RETURN a.id AS source, b.id AS target, c.intent AS intent""",
    "leaderboard_options": """
        MATCH (r:Result)-[:ON_DATASET]->(d:Dataset), (r)-[:MEASURED_BY]->(m:Metric)
        RETURN d.id AS dataset, d.name AS dataset_name, r.split AS split, m.id AS metric, m.name AS metric_name,
               count(r) AS results
        ORDER BY dataset_name, split, metric_name""",
    "conflicts_with_results": """
        MATCH (p:Paper)-[:MAKES]->(c:Claim)-[x:CONFLICTS_WITH_RESULT]->(r:Result)-[:OF_METHOD]->(m:Method),
              (r)-[:ON_DATASET]->(d:Dataset)
        RETURN c.id AS claim, c.text AS text, p.title AS paper, m.name AS method, d.name AS dataset,
               r.split AS split, r.value AS value, x.basis AS basis""",
    "sessions": """
        MATCH (s:ResearchSession)
        OPTIONAL MATCH (s)-[:ASKED]->(q:Question)
        RETURN s.id AS id, s.title AS title, s.started_at AS started_at, count(q) AS questions
        ORDER BY started_at DESC""",
    "session_insights": """
        MATCH (:ResearchSession {id: $session})-[:SAVED]->(i:Insight)
        OPTIONAL MATCH (i)-[:ABOUT]->(x)
        RETURN i.id AS id, i.text AS text, i.saved_at AS saved_at, collect(x.name) AS about
        ORDER BY saved_at DESC""",
}

_lock = threading.Lock()
_agents: dict = {}          # workspace -> (stop event, threads)
_stores: dict = {}          # workspace -> DocStore


def stop_agents() -> None:
    """Stop every agent thread (on shutdown, and in tests before a workspace is deleted)."""
    with _lock:
        running = list(_agents.values())
        _agents.clear()
    for stop, threads in running:
        stop.set()
        for t in threads:
            t.join(timeout=10)


@asynccontextmanager
async def lifespan(app):
    yield
    stop_agents()


app = FastAPI(title="GraphMind Research API", lifespan=lifespan)


# ---------------------------------------------------------------- FalkorDB first
def falkordb_up() -> bool:
    try:
        return bool(redis.Redis(host=FALKOR_HOST, port=FALKOR_PORT, socket_connect_timeout=1, socket_timeout=2).ping())
    except redis.exceptions.RedisError:
        return False


@app.exception_handler(redis.exceptions.ConnectionError)
@app.exception_handler(redis.exceptions.TimeoutError)
async def falkordb_down(request: Request, exc: Exception):
    return JSONResponse(status_code=503, content={"detail": "FalkorDB is not reachable. Start it: docker start <name>"})


def require_falkordb():
    if not falkordb_up():
        raise HTTPException(503, "FalkorDB is not reachable. Start it: docker start <name>")


def ws_graph(ws: str, _=Depends(require_falkordb)):
    try:
        return graph_for(ws, must_exist=True)
    except UnknownWorkspace as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


def store_for(ws: str) -> DocStore:
    with _lock:
        if ws not in _stores:
            _stores[ws] = DocStore(CHROMA_PATH, ws)
        return _stores[ws]


def rows(graph, query: str, **params) -> list:
    res = graph.ro_query(VIEW_Q[query], params)
    cols = [c[1] if isinstance(c, (list, tuple)) else c for c in res.header]
    return [dict(zip(cols, r)) for r in res.result_set]


def ensure_agents(ws: str, graph) -> None:
    """Start the four pipeline agents for a workspace once; they keep polling its graph for jobs."""
    with _lock:
        if ws in _agents:
            return
        ctx = {"graph": graph, "store": None, "ontology": ONTOLOGY, "intents_by": "keywords", "threshold": 0.85}
    ctx["store"] = store_for(ws)
    memory.run(graph, "job_requeue_stale", older_ms=60_000)
    with _lock:
        _agents[ws] = pipeline.start_agents(ctx, WORKERS)


# ---------------------------------------------------------------- health and workspaces
@app.get("/api/health")
def health():
    status = {"falkordb": falkordb_up(), "ollama": False, "agents": sorted(_agents)}
    try:
        status["ollama"] = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=2).status_code == 200
    except httpx.HTTPError:
        pass
    return JSONResponse(status, status_code=200 if status["falkordb"] else 503)


class NewWorkspace(BaseModel):
    name: str


@app.get("/api/workspaces")
def workspaces(_=Depends(require_falkordb)):
    return list_workspaces()


@app.post("/api/workspaces")
def create_workspace(body: NewWorkspace, _=Depends(require_falkordb)):
    try:
        graph = graph_for(body.name)
    except ValueError as e:
        raise HTTPException(400, str(e))
    graph.query("MERGE (w:Workspace {name: $n}) ON CREATE SET w.created_at = timestamp()", {"n": body.name})
    return {"name": body.name}


# ---------------------------------------------------------------- papers and the pipeline
@app.post("/api/workspaces/{ws}/papers")
def upload(ws: str, files: list[UploadFile] = File(...), _=Depends(require_falkordb)):
    try:
        graph = graph_for(ws)                       # uploading may create the workspace
    except ValueError as e:
        raise HTTPException(400, str(e))
    folder = UPLOAD_DIR / ws
    folder.mkdir(parents=True, exist_ok=True)
    jobs = []
    for f in files:
        name = re.sub(r"[^A-Za-z0-9._-]", "_", Path(f.filename or "upload.pdf").name)
        if not name.lower().endswith(".pdf"):
            raise HTTPException(400, f"{name}: only PDF files")
        path = folder / name
        with path.open("wb") as out:
            shutil.copyfileobj(f.file, out)
        jobs.append(memory.create_job(graph, str(path)))
    ensure_agents(ws, graph)
    return {"jobs": jobs}


@app.get("/api/workspaces/{ws}/jobs")
def jobs(ws: str, graph=Depends(ws_graph)):
    for r in (board := memory.board(graph)):
        r["file"] = Path(r["file"]).name
    return board


@app.get("/api/workspaces/{ws}/papers")
def papers(ws: str, graph=Depends(ws_graph)):
    return Analysis(graph).run("library_papers")


@app.get("/api/workspaces/{ws}/papers/{pid}")
def paper(ws: str, pid: str, graph=Depends(ws_graph)):
    meta = rows(graph, "paper", id=pid)
    if not meta:
        raise HTTPException(404, f"no paper {pid}")
    return {**meta[0], "cites": rows(graph, "paper_cites", id=pid), "cited_by": rows(graph, "paper_cited_by", id=pid),
            "claims": rows(graph, "paper_claims", id=pid), "results": rows(graph, "paper_results", id=pid)}


@app.get("/api/workspaces/{ws}/graph/library")
def library_graph(ws: str, graph=Depends(ws_graph)):
    return {"nodes": rows(graph, "library_graph"), "edges": rows(graph, "library_cites")}


@app.get("/api/workspaces/{ws}/entities")
def entities(ws: str, graph=Depends(ws_graph)):
    return [{k: e[k] for k in ("id", "label", "name")} for e in workflow.catalogue(graph)]


# ---------------------------------------------------------------- analysis views
@app.get("/api/workspaces/{ws}/leaderboard/options")
def leaderboard_options(ws: str, graph=Depends(ws_graph)):
    return rows(graph, "leaderboard_options")


@app.get("/api/workspaces/{ws}/leaderboard")
def leaderboard(ws: str, dataset: str, split: str, metric: str, graph=Depends(ws_graph)):
    return Analysis(graph).leaderboard(dataset, split, metric)


@app.get("/api/workspaces/{ws}/pair")
def pair(ws: str, a: str, b: str, graph=Depends(ws_graph)):
    return Analysis(graph).relationship(a, b)


@app.get("/api/workspaces/{ws}/claims")
def claims(ws: str, graph=Depends(ws_graph)):
    A = Analysis(graph)
    return {"conflicts": A.run("claim_conflicts"), "support": A.run("claim_support"), "sota": A.run("sota_check"),
            "conflicts_with_results": rows(graph, "conflicts_with_results")}


@app.get("/api/workspaces/{ws}/citations")
def citations(ws: str, graph=Depends(ws_graph)):
    A = Analysis(graph)
    missing = [{**m, "citing": p["id"], "citing_title": p["title"]}
               for p in A.run("library_papers") for m in A.missing_citations(p["id"])]
    return {"missing": missing, "stale": A.run("stale_citations"), "external_hubs": A.run("external_hubs", min=3)}


@app.get("/api/workspaces/{ws}/gaps")
def gaps(ws: str, graph=Depends(ws_graph)):
    A = Analysis(graph)
    return {name: A.run(name) for name in ("gap_method_dataset", "gap_metric_coverage", "gap_dataset_depth",
                                           "gap_unreproduced", "gap_task_without_method")}


@app.get("/api/workspaces/{ws}/people")
def people(ws: str, graph=Depends(ws_graph)):
    A = Analysis(graph)
    return {"influential": A.run("influential_papers", k=8), "bridges": A.run("bridge_authors", k=5),
            "groups": A.run("author_groups")}


@app.get("/api/workspaces/{ws}/eval")
def evaluation(ws: str, graph=Depends(ws_graph)):
    return score(graph)


# ---------------------------------------------------------------- sessions and the agent
class NewSession(BaseModel):
    title: str = ""


class Question(BaseModel):
    question: str


class NewInsight(BaseModel):
    text: str
    about: list[str] = []


@app.get("/api/workspaces/{ws}/sessions")
def sessions(ws: str, graph=Depends(ws_graph)):
    return rows(graph, "sessions")


@app.post("/api/workspaces/{ws}/sessions")
def new_session(ws: str, body: NewSession, graph=Depends(ws_graph)):
    return {"id": memory.start_session(graph, body.title)}


@app.get("/api/workspaces/{ws}/sessions/{sid}")
def session(ws: str, sid: str, graph=Depends(ws_graph)):
    history = memory.run(graph, "session_history", session=sid)
    for h in history:
        h["answer"] = json.loads(h["answer"] or "{}")
    return {"history": history, "insights": rows(graph, "session_insights", session=sid)}


@app.post("/api/workspaces/{ws}/sessions/{sid}/ask")
def ask(ws: str, sid: str, body: Question, graph=Depends(ws_graph)):
    """Server-sent events: one 'data:' line per agent step, the last one is {"step": "final", ...}."""
    store = store_for(ws) if store_for(ws).col.count() else None

    def events():
        try:
            for event in workflow.stream(graph, body.question, store, sid):
                yield f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"
        except redis.exceptions.RedisError:
            yield f"data: {json.dumps({'step': 'error', 'detail': 'FalkorDB is not reachable'})}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


@app.post("/api/workspaces/{ws}/sessions/{sid}/insights")
def save_insight(ws: str, sid: str, body: NewInsight, graph=Depends(ws_graph)):
    return {"id": memory.save_insight(graph, sid, body.text, body.about)}


@app.get("/api/workspaces/{ws}/sessions/{sid}/whats-new")
def whats_new(ws: str, sid: str, graph=Depends(ws_graph)):
    return memory.whats_new_since(graph, sid)
````

### backend/tests/test_api.py

````python
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
````
