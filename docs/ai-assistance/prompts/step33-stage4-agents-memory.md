# Stage 4 (Step 33): pipeline agents and research memory

Save as `docs/prompts/step33.md` and tell Claude Code: "Do docs/prompts/step33.md".
Tested on FalkorDB 6.0.1: `pytest -q` gives 45 passed (38 before + 4 memory + 3 pipeline).

## What this stage adds and why

| Piece | What it does | Why it matters for judging |
|---|---|---|
| `Job` nodes | One per uploaded PDF. Agents move it parse -> extract -> link -> critique -> done and write their name into `history`. | Track 02 "shared state and hand-offs": the hand-off is a property change on a graph node every agent can see. |
| Atomic claim | `job_claim` is ONE write query. FalkorDB runs write queries one at a time per graph, so two agents can never take the same job. No Python locks. | Safe coordination with no extra infrastructure. |
| Stage waves | A stage waits until no job is still in an earlier stage. | Citation intents and claim pairs depend on which papers exist, so the agents build exactly the same graph as the batch run (the test checks this). |
| `Lock` node | A mutex in the graph for steps that rewrite the whole graph (ingest, reconcile, labelling intents, sota check). Per-paper LLM work runs in parallel. | Works across threads and processes because it lives in FalkorDB. |
| Retries | A crash puts the job back to `ready`; after 3 attempts it is `failed` with the error on the node. | The pipeline board can show errors in red. |
| `ResearchSession`, `Question`, `Insight` | Questions (with the full answer as JSON), saved insights, a reading list, all linked `ABOUT` papers and methods. `whats_new_since` finds papers added after a question that touch its topics. | Track 02 memory: it survives restarts and is queryable like the rest of the graph. No SQLite (rule 8). |

## The prompt for Claude Code

Create these four files with EXACTLY the code below (memory.py replaces Reference J of BUILD_GUIDE.md: it adds
the stage waves, the graph lock, stale-job requeue and helper functions). Then:

1. From backend/ run `pytest -q`. Expect 45 passed.
2. Add to CLAUDE.md under "FalkorDB 6.0.1 notes": "Agents coordinate only through the graph: Job nodes (atomic
   claim = one write query) and the Lock node (graph_lock). Never add Python-side locks or queues."
3. In docs/DATA_MODEL.md, under runtime labels, add Lock (name, holder, acquired_at) and the Job properties
   (stage, status, claimed_by, attempts, history, error, paper) with one line each.
4. Explain: why job_claim is safe without locks; why stages run in waves; what graph_lock protects and what runs in
   parallel; what whats_new_since returns. Then stop. Do not run the real pipeline; I will run it myself.

### backend/app/agent/memory.py

````python
"""Shared state in FalkorDB: pipeline jobs that agents hand to each other, and research-session memory.

Nothing here lives in Python memory or SQLite. Every agent reads and writes the same graph, so the graph IS the
coordination channel (Track 02: shared state and hand-offs) and the memory that survives restarts.
"""
import json
import time
import uuid
from contextlib import contextmanager

STAGES = ["parse", "extract", "link", "critique", "done"]

MEM_Q = {
    # ---------- jobs: one per uploaded PDF, moved through the stages by different agents
    "job_create": """
        MERGE (j:Job {id: $id}) SET j.stage = 'parse', j.status = 'ready', j.file = $file,
              j.created_at = timestamp(), j.attempts = 0, j.history = [], j.error = NULL""",
    # One write query = one atomic step: FalkorDB runs write queries one at a time per graph, so two agents can never
    # claim the same job. A stage waits until no job is still in an earlier stage (ready or running): citation
    # intents and claim pairs depend on which papers exist, so each stage runs as a wave over the whole upload.
    "job_claim": """
        OPTIONAL MATCH (k:Job) WHERE k.stage IN $earlier AND k.status IN ['ready', 'running']
        WITH count(k) AS blocking
        MATCH (j:Job {stage: $stage, status: 'ready'}) WHERE blocking = 0
        WITH j ORDER BY j.created_at LIMIT 1
        SET j.status = 'running', j.claimed_by = $agent, j.claimed_at = timestamp(), j.attempts = j.attempts + 1
        RETURN j.id AS id, j.file AS file""",
    "job_link_paper": """
        MATCH (j:Job {id: $id}), (p:Paper {id: $paper}) MERGE (j)-[:FOR_PAPER]->(p) SET j.paper = $paper""",
    "job_advance": """
        MATCH (j:Job {id: $id})
        SET j.history = j.history + [$agent + ':' + j.stage], j.stage = $next, j.attempts = 0,
            j.status = CASE WHEN $next = 'done' THEN 'done' ELSE 'ready' END, j.claimed_by = NULL""",
    "job_fail": """
        MATCH (j:Job {id: $id})
        SET j.error = $error, j.claimed_by = NULL,
            j.status = CASE WHEN j.attempts >= $max_attempts THEN 'failed' ELSE 'ready' END""",
    # A job left 'running' by a crashed process goes back to 'ready' after $older_ms.
    "job_requeue_stale": """
        MATCH (j:Job {status: 'running'}) WHERE j.claimed_at < timestamp() - $older_ms
        SET j.status = 'ready', j.claimed_by = NULL RETURN count(j) AS requeued""",
    "job_board": """
        MATCH (j:Job) OPTIONAL MATCH (j)-[:FOR_PAPER]->(p:Paper)
        RETURN j.id AS id, j.file AS file, p.title AS title, j.stage AS stage, j.status AS status,
               j.claimed_by AS agent, j.attempts AS attempts, j.history AS history, j.error AS error,
               j.created_at AS created_at
        ORDER BY created_at""",

    # ---------- a mutex in the graph, for steps that change the whole graph (ingest, reconcile, intent labels).
    # Same trick as job_claim: one atomic write query. A holder older than $stale_ms is presumed crashed.
    "lock_acquire": """
        MERGE (l:Lock {name: $name})
        WITH l WHERE l.holder IS NULL OR l.holder = $agent OR l.acquired_at < timestamp() - $stale_ms
        SET l.holder = $agent, l.acquired_at = timestamp()
        RETURN l.holder AS holder""",
    "lock_release": """
        MATCH (l:Lock {name: $name}) WHERE l.holder = $agent SET l.holder = NULL""",

    # ---------- research sessions (episodic memory) and insights (what the user decided to keep)
    "session_start": """
        MERGE (s:ResearchSession {id: $id}) ON CREATE SET s.started_at = timestamp(), s.title = $title
        SET s.last_active = timestamp()""",
    # The full answer is stored on the Question node as JSON text: no second database (CLAUDE.md rule 8).
    "question_log": """
        MATCH (s:ResearchSession {id: $session})
        CREATE (q:Question {id: $id, text: $text, intent: $intent, asked_at: timestamp(), answer: $answer})
        CREATE (s)-[:ASKED]->(q)
        WITH q UNWIND $about AS aid MATCH (x {id: aid}) MERGE (q)-[:ABOUT]->(x)""",
    "insight_save": """
        MATCH (s:ResearchSession {id: $session})
        CREATE (i:Insight {id: $id, text: $text, saved_at: timestamp()})
        CREATE (s)-[:SAVED]->(i)
        WITH i UNWIND $about AS aid MATCH (x {id: aid}) MERGE (i)-[:ABOUT]->(x)""",
    "reading_list_add": """
        MATCH (s:ResearchSession {id: $session}), (p:Paper {id: $paper}) MERGE (s)-[r:READING_LIST]->(p)
        SET r.added_at = timestamp(), r.reason = $reason""",
    "recall_insights": """
        MATCH (i:Insight)-[:ABOUT]->(x) WHERE x.id IN $ids
        MATCH (s:ResearchSession)-[:SAVED]->(i)
        RETURN i.text AS insight, collect(DISTINCT x.id) AS about, s.title AS session, i.saved_at AS saved_at
        ORDER BY saved_at DESC""",
    "session_history": """
        MATCH (s:ResearchSession {id: $session})-[:ASKED]->(q:Question)
        RETURN q.id AS id, q.text AS question, q.intent AS intent, q.asked_at AS asked_at, q.answer AS answer
        ORDER BY asked_at""",
    # Papers added after the session last asked about a topic, connected to that topic.
    "whats_new_since": """
        MATCH (s:ResearchSession {id: $session})-[:ASKED]->(q:Question)-[:ABOUT]->(x)
        MATCH (p:Paper {in_library: true})-[r]->(x)
        WHERE p.added_at > q.asked_at
        RETURN DISTINCT p.id AS paper_id, p.title AS paper, type(r) AS relation, x.id AS topic, q.text AS earlier_question""",
}

READ_ONLY = {"job_board", "recall_insights", "session_history", "whats_new_since"}


def run(graph, query_name: str, /, **params) -> list:
    """Run one MEM_Q query; reads use ro_query (never create a graph), writes use query.
    query_name is positional-only, so a query parameter may itself be called 'name'."""
    res = (graph.ro_query if query_name in READ_ONLY else graph.query)(MEM_Q[query_name], params)
    cols = [c[1] if isinstance(c, (list, tuple)) else c for c in (res.header or [])]
    return [dict(zip(cols, r)) for r in res.result_set]


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


# ---------------------------------------------------------------- jobs
def create_job(graph, file: str) -> str:
    job_id = new_id("job")
    run(graph, "job_create", id=job_id, file=str(file))
    return job_id


def claim(graph, stage: str, agent: str) -> dict | None:
    earlier = STAGES[:STAGES.index(stage)]
    rows = run(graph, "job_claim", stage=stage, agent=agent, earlier=earlier)
    return rows[0] if rows else None


def advance(graph, job_id: str, stage: str, agent: str) -> None:
    run(graph, "job_advance", id=job_id, agent=agent, next=STAGES[STAGES.index(stage) + 1])


def fail(graph, job_id: str, error: str, max_attempts: int = 3) -> None:
    run(graph, "job_fail", id=job_id, error=error[:500], max_attempts=max_attempts)


def board(graph) -> list:
    return run(graph, "job_board")


@contextmanager
def graph_lock(graph, name: str, agent: str, poll: float = 0.2, stale_ms: int = 600_000):
    """Only one agent at a time runs the block, across threads and processes, because the lock lives in the graph."""
    while not run(graph, "lock_acquire", name=name, agent=agent, stale_ms=stale_ms):
        time.sleep(poll)
    try:
        yield
    finally:
        run(graph, "lock_release", name=name, agent=agent)


# ---------------------------------------------------------------- research memory
def start_session(graph, title: str = "", session_id: str | None = None) -> str:
    session_id = session_id or new_id("session")
    run(graph, "session_start", id=session_id, title=title or time.strftime("Session %Y-%m-%d %H:%M"))
    return session_id


def log_question(graph, session_id: str, text: str, intent: str, answer: dict, about: list) -> str:
    qid = new_id("q")
    run(graph, "question_log", session=session_id, id=qid, text=text, intent=intent,
        answer=json.dumps(answer, ensure_ascii=False), about=list(about))
    return qid


def save_insight(graph, session_id: str, text: str, about: list) -> str:
    iid = new_id("insight")
    run(graph, "insight_save", session=session_id, id=iid, text=text, about=list(about))
    return iid


def add_to_reading_list(graph, session_id: str, paper_id: str, reason: str = "") -> None:
    run(graph, "reading_list_add", session=session_id, paper=paper_id, reason=reason)


def recall_insights(graph, ids: list) -> list:
    return run(graph, "recall_insights", ids=list(ids))


def whats_new_since(graph, session_id: str) -> list:
    return run(graph, "whats_new_since", session=session_id)
````

### backend/app/agent/pipeline.py

(If app/config.py names the Chroma path setting differently from `settings.chroma_path`, use that name.)

````python
"""Four agents that turn uploaded PDFs into the knowledge graph, coordinating ONLY through the graph:
Job nodes carry the work from stage to stage, and one Lock node guards the steps that rewrite the whole graph.

    Parser    (stage 'parse')     PDF -> papers, authors, citations, results; passages -> ChromaDB      no LLM
    Extractor (stage 'extract')   citation intents (graph rules), claims (LLM picks a sentence)
    Linker    (stage 'link')      reconcile entities, SIMILAR_TO between look-alike methods (embeddings)
    Critic    (stage 'critique')  claim relations (LLM on graph-picked pairs), sota claims vs numbers

No agent calls another. Each one claims a job for its stage from the graph, does its work, and moves the job on.
Run on a folder (no API needed):  python -m app.agent.pipeline --workspace agents --workers 2 ../corpus/pdf
"""
import threading
import time
import traceback

from app.agent import enrich, memory


class Agent(threading.Thread):
    stage = ""

    def __init__(self, name: str, ctx: dict, stop: threading.Event, poll: float = 0.5):
        super().__init__(name=name, daemon=True)
        self.ctx, self.stop_event, self.poll = ctx, stop, poll

    def run(self):
        graph = self.ctx["graph"]
        while not self.stop_event.is_set():
            job = memory.claim(graph, self.stage, self.name)
            if job is None:
                self.stop_event.wait(self.poll)        # nothing for this stage yet: look again shortly
                continue
            try:
                self.work(job)
                memory.advance(graph, job["id"], self.stage, self.name)
            except Exception as exc:                   # the job goes back to 'ready' (or 'failed' after 3 tries)
                memory.fail(graph, job["id"], f"{self.name}: {exc.__class__.__name__}: {exc}")
                if self.ctx.get("verbose"):
                    traceback.print_exc()

    def paper_of(self, job: dict) -> str:
        rows = self.ctx["graph"].ro_query("MATCH (:Job {id: $id})-[:FOR_PAPER]->(p:Paper) RETURN p.id",
                                          {"id": job["id"]}).result_set
        if not rows:
            raise RuntimeError("job has no paper yet")
        return rows[0][0]

    def work(self, job: dict) -> None:
        raise NotImplementedError


class ParserAgent(Agent):
    stage = "parse"

    def work(self, job):
        from app.graph.ingest import ingest_pdf
        g = self.ctx["graph"]
        # Ingestion matches papers and merges entities across the whole graph: one parser at a time.
        with memory.graph_lock(g, "graph-write", self.name):
            pid = ingest_pdf(g, job["file"], self.ctx["ontology"], self.ctx["store"])
            memory.run(g, "job_link_paper", id=job["id"], paper=pid)
            # Citations INTO this paper were labelled while it was a stub: label them again now it is here.
            g.query("MATCH (:Paper)-[c:CITES]->(:Paper {id: $pid}) SET c.intent = 'unclassified'", {"pid": pid})


class ExtractorAgent(Agent):
    stage = "extract"

    def work(self, job):
        g, pid = self.ctx["graph"], self.paper_of(job)
        with memory.graph_lock(g, "graph-write", self.name):          # labels every unlabelled citation, then reconciles
            enrich.classify_citations(g, use_llm=self.ctx["intents_by"] == "llm")
        enrich.extract_claims(g, pid, self.ctx["ontology"])           # per paper: agents run this in parallel


class LinkerAgent(Agent):
    stage = "link"

    def work(self, job):
        from app.graph.ingest import reconcile
        g, pid = self.ctx["graph"], self.paper_of(job)
        with memory.graph_lock(g, "graph-write", self.name):
            reconcile(g)
        enrich.link_similar_methods(g, self.ctx["store"], self.ctx["threshold"], pid)


class CriticAgent(Agent):
    stage = "critique"

    def work(self, job):
        g, pid = self.ctx["graph"], self.paper_of(job)
        enrich.relate_claims(g, self.ctx["store"], pid)               # per paper, in parallel
        with memory.graph_lock(g, "graph-write", self.name):
            enrich.check_claims(g)


AGENTS = [ParserAgent, ExtractorAgent, LinkerAgent, CriticAgent]
SHORT = {"parse": "parser", "extract": "extractor", "link": "linker", "critique": "critic"}


def start_agents(ctx: dict, workers_per_stage: int = 1) -> tuple[threading.Event, list]:
    """Start N agents per stage. Returns the stop event and the threads (call stop.set() to end them)."""
    stop = threading.Event()
    threads = [cls(f"{SHORT[cls.stage]}-{i + 1}", ctx, stop) for cls in AGENTS for i in range(workers_per_stage)]
    for t in threads:
        t.start()
    return stop, threads


def finished(rows: list) -> bool:
    return bool(rows) and all(r["status"] in ("done", "failed") for r in rows)


if __name__ == "__main__":
    import argparse
    import json
    from pathlib import Path

    from app.config import settings
    from app.docs.docstore import DocStore
    from app.graph.client import graph_for
    from app.graph.ingest import _expand

    ap = argparse.ArgumentParser(description="Run the four pipeline agents on a folder of PDFs.")
    ap.add_argument("--workspace", required=True)
    ap.add_argument("--workers", type=int, default=1, help="agents per stage")
    ap.add_argument("--intents-by", choices=["llm", "keywords"], default="keywords")
    ap.add_argument("--threshold", type=float, default=0.85)
    ap.add_argument("--verbose", action="store_true", help="print the full traceback when an agent's work fails")
    ap.add_argument("pdfs", nargs="+")
    args = ap.parse_args()

    graph = graph_for(args.workspace)
    ctx = {"graph": graph, "store": DocStore(str(settings.chroma_path), args.workspace),
           "ontology": json.loads((Path(__file__).resolve().parents[3] / "ontology.json").read_text(encoding="utf-8")),
           "intents_by": args.intents_by, "threshold": args.threshold, "verbose": args.verbose}
    jobs = [memory.create_job(graph, str(f)) for f in _expand(args.pdfs)]
    print(f"{len(jobs)} jobs created; {args.workers} agent(s) per stage")
    stop, _ = start_agents(ctx, args.workers)
    t0, last = time.time(), None
    while True:
        rows = [r for r in memory.board(graph) if r["id"] in jobs]
        counts = {s: sum(r["stage"] == s for r in rows) for s in memory.STAGES}
        running = sorted(f"{r['agent']}" for r in rows if r["status"] == "running")
        line = "  ".join(f"{s}:{n}" for s, n in counts.items()) + f"   running: {', '.join(running) or '-'}"
        if line != last:
            print(f"{time.time() - t0:6.0f}s  {line}")
            last = line
        if finished(rows):
            break
        time.sleep(1)
    stop.set()
    failed = [r for r in rows if r["status"] == "failed"]
    for r in failed:
        print(f"FAILED {Path(r['file']).name}: {r['error']}")
    print(f"done in {time.time() - t0:.0f}s; history of the first job: {rows[0]['history']}")
````

### backend/tests/test_memory.py

````python
"""Shared state in the graph: atomic job claims, stage waves, retries, the graph lock, and research memory.
Run: pytest tests/test_memory.py -v"""
import os
import threading
from collections import Counter

import pytest
from falkordb import FalkorDB

from app.agent import memory


@pytest.fixture
def g():
    db = FalkorDB(host=os.getenv("FALKORDB_HOST", "localhost"), port=int(os.getenv("FALKORDB_PORT", "6379")))
    graph = db.select_graph("memory_test")
    try:
        graph.delete()
    except Exception:
        pass
    graph = db.select_graph("memory_test")
    yield graph
    graph.delete()


def test_no_job_is_claimed_twice_and_stages_run_in_waves(g):
    jobs = [memory.create_job(g, f"paper{i}.pdf") for i in range(12)]
    assert memory.claim(g, "extract", "early") is None          # parse jobs still waiting: extract must wait
    claims, lock = Counter(), threading.Lock()

    def agent(name, stage):
        later = memory.STAGES.index(stage)
        while True:
            job = memory.claim(g, stage, name)
            if job:
                with lock:
                    claims[(job["id"], stage)] += 1
                memory.advance(g, job["id"], stage, name)
            elif all(memory.STAGES.index(r["stage"]) > later for r in memory.board(g)):
                return

    threads = [threading.Thread(target=agent, args=(f"{s}-{i}", s)) for s in memory.STAGES[:-1] for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    rows = memory.board(g)
    assert all(r["status"] == "done" for r in rows) and len(rows) == 12
    assert len(claims) == 48 and set(claims.values()) == {1}       # every job, every stage: exactly one agent
    assert all(len(r["history"]) == 4 for r in rows)               # who did each stage is recorded on the job


def test_failed_job_is_retried_then_given_up(g):
    job = memory.create_job(g, "broken.pdf")
    for attempt in (1, 2, 3):
        assert memory.claim(g, "parse", "parser-1")["id"] == job
        memory.fail(g, job, f"boom {attempt}")
    row = memory.board(g)[0]
    assert row["status"] == "failed" and row["attempts"] == 3 and row["error"] == "boom 3"
    assert memory.claim(g, "parse", "parser-1") is None


def test_graph_lock_lets_one_agent_in_at_a_time(g):
    g.query("CREATE (:Counter {n: 0})")
    inside, most, guard = [0], [0], threading.Lock()

    def agent(name):
        for _ in range(5):
            with memory.graph_lock(g, "graph-write", name, poll=0.01):
                with guard:
                    inside[0] += 1
                    most[0] = max(most[0], inside[0])
                n = g.query("MATCH (c:Counter) RETURN c.n").result_set[0][0]
                g.query("MATCH (c:Counter) SET c.n = $n", {"n": n + 1})      # read-modify-write: unsafe without the lock
                with guard:
                    inside[0] -= 1

    threads = [threading.Thread(target=agent, args=(f"agent-{i}",)) for i in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    assert most[0] == 1 and g.query("MATCH (c:Counter) RETURN c.n").result_set[0][0] == 30


def test_research_memory_recall_and_whats_new(g):
    g.query("""CREATE (:Paper {id: 'P03', title: 'GraphWalker-QA', in_library: true, added_at: 1}),
                      (:Method {id: 'm-gwqa', name: 'GraphWalker-QA'})""")
    s = memory.start_session(g, "Is graph retrieval worth it?")
    memory.log_question(g, s, "How good is GraphWalker-QA?", "lineage", {"answer": "...", "facts": []}, ["m-gwqa"])
    memory.save_insight(g, s, "GraphWalker-QA's gain needs gold entity links", ["m-gwqa", "P03"])
    memory.add_to_reading_list(g, s, "P03", "original paper")
    assert memory.recall_insights(g, ["m-gwqa"])[0]["insight"].startswith("GraphWalker-QA's gain")
    assert memory.whats_new_since(g, s) == []
    # a paper uploaded later that talks about the same method shows up as new for this session
    g.query("""MATCH (m:Method {id: 'm-gwqa'})
               CREATE (:Paper {id: 'P11', title: 'Entity linking is the bottleneck', in_library: true,
                               added_at: timestamp() + 1000})-[:USES]->(m)""")
    new = memory.whats_new_since(g, s)
    assert [(r["paper_id"], r["relation"], r["topic"]) for r in new] == [("P11", "USES", "m-gwqa")]
    history = memory.run(g, "session_history", session=s)
    assert history[0]["question"] == "How good is GraphWalker-QA?" and '"answer"' in history[0]["answer"]
````

### backend/tests/test_pipeline.py

````python
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
````
