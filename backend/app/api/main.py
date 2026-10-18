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
from redis.backoff import NoBackoff
from redis.retry import Retry
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from app.config import settings
from app.agent import memory, pipeline, workflow
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
    # Check FalkorDB using the configured cloud credentials and TLS settings.
    try:
        return bool(redis.Redis(
            host=FALKOR_HOST,
            port=FALKOR_PORT,
            username=settings.falkordb_username or None,
            password=settings.falkordb_password or None,
            ssl=settings.falkordb_ssl,
            ssl_check_hostname=settings.falkordb_ssl,
            socket_connect_timeout=3,
            socket_timeout=3,
            retry=Retry(NoBackoff(), 0),
        ).ping())
    except redis.exceptions.RedisError as exc:
        print(f"FalkorDB health check failed: {type(exc).__name__}: {exc}", flush=True)
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
    from app.config import settings

    status = {
        "falkordb": falkordb_up(),
        "llm_provider": settings.llm_provider,
        "embed_provider": settings.embed_provider,
        "agents": sorted(_agents),
    }
    return JSONResponse(
        status,
        status_code=200 if status["falkordb"] else 503,
    )



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
