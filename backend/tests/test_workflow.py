"""The research agent on the gold graph: each demo question gets the facts in ground_truth/expected_answers.json.
The LLM is switched off (template answers) except in the last test, which fakes it. Run: pytest tests/test_workflow.py -v"""
import os
from pathlib import Path

import pytest
from falkordb import FalkorDB

from app.agent import llm, memory, workflow
from app.graph.gold_loader import load_gold

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def g():
    db = FalkorDB(host=os.getenv("FALKORDB_HOST", "localhost"), port=int(os.getenv("FALKORDB_PORT", "6379")))
    graph = db.select_graph("workflow_test")
    load_gold(graph, ROOT / "ground_truth" / "gold_graph.json")
    yield graph
    graph.delete()


def facts(state):
    return [f["text"] for f in state["facts"]]


def test_how_two_papers_are_related(g):
    s = workflow.ask(g, "How are GraphWalker-QA and Revisiting Graph Gains related?", use_llm=False)
    text = " | ".join(facts(s))
    assert s["intent"] == "relate_papers"
    assert "intent: reproduces" in text and "Jonas Weber" in text and "KaveriHop" in text
    assert "CONTRADICTS" in text and text.count("REPRODUCES:") == 4


def test_is_hoplens_really_state_of_the_art(g):
    s = workflow.ask(g, "Is HopLens really state of the art?", use_llm=False)
    assert s["intent"] == "sota" and s["answer"].startswith("No.")
    text = " | ".join(facts(s))
    assert "GraphFuse reports 46.3 on KaveriHop 3-hop" in text and "GraphFuse reports 41.2 on TriHop-Bench 3-hop" in text
    assert "does not cite GraphFuse (score 10" in text and "does not cite HopRank (score 5" in text


def test_leaderboards_use_the_corrected_number(g):
    s = workflow.ask(g, "What is the leaderboard on KaveriHop 3-hop?", use_llm=False)
    assert facts(s)[0].startswith("1. GraphFuse: 46.3") and facts(s)[1].startswith("2. HopLens: 44.8")
    s = workflow.ask(g, "Which method is best on TriHop-Bench 4-hop?", use_llm=False)
    assert facts(s)[0].startswith("1. GraphFuse: 19.4 (corrected, published as 22.7)")


def test_lineage(g):
    s = workflow.ask(g, "Where does LiteGraphFuse come from?", use_llm=False)
    assert s["intent"] == "lineage"
    assert sorted(facts(s)) == ["Lineage: LiteGraphFuse -> GraphFuse -> GraphWalker-QA (each one extends the next).",
                                "Lineage: LiteGraphFuse -> GraphFuse -> HopRank -> DenseHop (each one extends the next)."]


def test_disagreements_and_people(g):
    s = workflow.ask(g, "Which claims contradict each other?", use_llm=False)
    assert any(f.startswith("Revisiting Graph Gains CONTRADICTS GraphWalker-QA") for f in facts(s))
    s = workflow.ask(g, "Which authors bridge the groups?", use_llm=False)
    bridges = [f for f in facts(s) if f.startswith("Bridge author")]
    assert "Lena Fischer" in bridges[0] and "Ananya Iyer" in bridges[1]
    assert "Co-author group: Hana Kobayashi, Mateo Rossi." in facts(s)


def test_unknown_names_ask_for_clarification(g):
    s = workflow.ask(g, "How are FooBar and Baz related?", use_llm=False)
    assert s["answer_source"] == "clarify" and "Which two papers" in s["answer"] and "HopLens" in s["answer"]


def test_every_query_is_logged_with_its_cypher_and_questions_are_remembered(g):
    session = memory.start_session(g, "demo")
    events = list(workflow.stream(g, "Is HopLens really state of the art?", session_id=session, use_llm=False))
    steps = [e["step"] for e in events]
    assert steps[:2] == ["understand", "plan"] and steps[-1] == "final" and "remember" in steps
    log = next(e for e in events if e["step"] == "run_tools")["tool_log"]
    assert any("MATCH" in cypher for t in log for cypher in t["cypher"].values())
    about = g.query("""MATCH (:ResearchSession {id: $s})-[:ASKED]->(q:Question)-[:ABOUT]->(x)
                       RETURN q.intent, collect(x.id)""", {"s": session}).result_set
    assert about[0][0] == "sota" and "m-hoplens" in about[0][1]
    memory.save_insight(g, session, "HopLens missed GraphFuse", ["m-hoplens"])
    s = workflow.ask(g, "What did I save earlier about HopLens?", session_id=session, use_llm=False)
    assert s["intent"] == "recall" and any("HopLens missed GraphFuse" in f for f in facts(s))


def test_llm_answer_is_used_only_if_it_names_nothing_outside_the_facts(g, monkeypatch):
    reply = {"answer": "No: GraphFuse is higher on both 3-hop splits [1][2]."}
    monkeypatch.setattr(llm, "ollama_json", lambda system, user, schema, timeout=120: reply)
    s = workflow.ask(g, "Is HopLens really state of the art?")
    assert s["answer_source"] == "llm" and s["answer"].startswith("No: GraphFuse")
    reply["answer"] = "No: LinkLite is better."                    # LinkLite is in the graph but not in these facts
    s = workflow.ask(g, "Is HopLens really state of the art?")
    assert s["answer_source"] == "template" and s["answer"].startswith("No. HopLens")
