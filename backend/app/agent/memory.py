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
