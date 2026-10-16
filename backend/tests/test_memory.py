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
