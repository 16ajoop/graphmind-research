"""The four agents, two per stage, process the 12 PDFs through the graph and build the same graph as the batch run.
The LLM is replaced by a perfect fake (answers from the gold graph) and embeddings by a hashed bag of words,
so this tests coordination, not model quality. Run: pytest tests/test_pipeline.py -v"""
import hashlib
import json
import math
import os
import re
import time
from pathlib import Path

import pytest
from falkordb import FalkorDB

from app.agent import enrich, llm, memory, pipeline
from app.docs.docstore import DocStore
from app.eval_extraction import score
from app.graph.ingest import words

ROOT = Path(__file__).resolve().parents[2]
PDFS = sorted((ROOT / "corpus" / "pdf").glob("*.pdf"))
ONTOLOGY = json.loads((ROOT / "ontology.json").read_text(encoding="utf-8"))
GOLD = json.loads((ROOT / "ground_truth" / "gold_graph.json").read_text(encoding="utf-8"))
NODE = {n["id"]: n for n in GOLD["nodes"]}
BY_TITLE = {words(n["props"]["title"]): n["id"] for n in GOLD["nodes"] if n["label"] == "Paper"}
MAKES = {e["dst"]: e["src"] for e in GOLD["edges"] if e["type"] == "MAKES"}
ABOUT = {}
for e in GOLD["edges"]:
    if e["type"] == "ABOUT":
        ABOUT.setdefault(e["src"], []).append(NODE[e["dst"]]["props"]["name"])
CLAIM_BY_TEXT = {words(n["props"]["text"]): n["id"] for n in GOLD["nodes"] if n["label"] == "Claim"}
RELATION = {(e["src"], e["dst"]): e["type"] for e in GOLD["edges"] if e["type"] in ("SUPPORTS", "CONTRADICTS", "QUALIFIES")}


def fake_claims(title, abstract, conclusion, known, notes=None):
    pid = BY_TITLE[words(title)]
    return [{"text": NODE[c]["props"]["text"], "type": NODE[c]["props"]["type"], "about": ABOUT[c],
             "scope": ["KaveriHop|3-hop|EM", "TriHop-Bench|3-hop|EM"] if c == "C12" else []}
            for c, p in MAKES.items() if p == pid]


def fake_judge(newer, older, facts=None):
    rel = RELATION.get((CLAIM_BY_TEXT[words(newer["text"])], CLAIM_BY_TEXT[words(older["text"])]), "UNRELATED")
    return {"relation": rel, "basis": "gold"}


def fake_embed(texts, kind):
    out = []
    for t in texts:
        v = [0.0] * 256
        for w in re.findall(r"[a-z]+", t.lower()):
            v[int(hashlib.md5(w.encode()).hexdigest(), 16) % 256] += 1.0
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        out.append([x / n for x in v])
    return out


@pytest.fixture(scope="module")
def processed(tmp_path_factory):
    db = FalkorDB(host=os.getenv("FALKORDB_HOST", "localhost"), port=int(os.getenv("FALKORDB_PORT", "6379")))
    g = db.select_graph("pipeline_test")
    try:
        g.delete()
    except Exception:
        pass
    g = db.select_graph("pipeline_test")
    mp = pytest.MonkeyPatch()
    mp.setattr(llm, "extract_claims", fake_claims)
    mp.setattr(llm, "judge_claims", fake_judge)
    # one forced failure: the first extract attempt for any paper crashes, and must be retried by an agent
    real_extract, crashed = enrich.extract_claims, []

    def flaky_extract(graph, paper_id, ontology):
        if not crashed:
            crashed.append(paper_id)
            raise RuntimeError("forced failure")
        return real_extract(graph, paper_id, ontology)

    mp.setattr(enrich, "extract_claims", flaky_extract)
    ctx = {"graph": g, "store": DocStore(str(tmp_path_factory.mktemp("chroma")), "pipeline_test", embed=fake_embed),
           "ontology": ONTOLOGY, "intents_by": "keywords", "threshold": 0.85}
    jobs = [memory.create_job(g, str(f)) for f in PDFS]
    stop, threads = pipeline.start_agents(ctx, workers_per_stage=2)
    deadline = time.time() + 300
    while not pipeline.finished(memory.board(g)) and time.time() < deadline:
        time.sleep(0.5)
    stop.set()
    for t in threads:
        t.join(timeout=10)
    mp.undo()
    yield g, jobs, crashed
    g.delete()


def test_every_job_goes_through_four_agents(processed):
    g, jobs, _ = processed
    rows = memory.board(g)
    assert len(rows) == 12 and all(r["status"] == "done" for r in rows)
    for r in rows:
        stages = [h.split(":")[1] for h in r["history"]]
        agents = [h.split(":")[0] for h in r["history"]]
        assert stages == ["parse", "extract", "link", "critique"]                 # in order, each exactly once
        assert [a.rsplit("-", 1)[0] for a in agents] == ["parser", "extractor", "linker", "critic"]


def test_forced_failure_was_retried(processed):
    g, _, crashed = processed
    row = [r for r in memory.board(g) if r["error"]]
    assert crashed and len(row) == 1 and "forced failure" in row[0]["error"] and row[0]["status"] == "done"


def test_agents_build_the_same_graph_as_the_batch_run(processed):
    g, _, _ = processed
    rep = score(g)
    assert rep["CITES"]["recall"] == rep["CITES"]["precision"] == 1.0
    assert rep["Result"]["recall"] == rep["Result"]["precision"] == 1.0
    assert rep["EXTENDS"] == {"precision": 1.0, "recall": 1.0, "got": 4, "want": 4}
    assert rep["CITES.intent_accuracy"] >= 0.9                       # graph rules + keywords, as in the batch run
    assert rep["Claim"]["recall"] == 1.0
    for rel in ("SUPPORTS", "CONTRADICTS"):
        assert rep[rel]["precision"] == rep[rel]["recall"] == 1.0, rel
    conflicts = g.query("MATCH (:Claim)-[x:CONFLICTS_WITH_RESULT]->(:Result) RETURN count(x)").result_set[0][0]
    assert conflicts == 2
    assert g.query("MATCH (l:Lock) WHERE l.holder IS NOT NULL RETURN count(l)").result_set[0][0] == 0   # lock released
