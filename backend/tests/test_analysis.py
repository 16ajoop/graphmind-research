"""Analysis queries vs expected answers, on the gold graph (oracle mode). Run from backend/: pytest tests/test_analysis.py -v"""
import json
import os
from pathlib import Path

import pytest
from falkordb import FalkorDB

from app.graph.analysis import Analysis, Q
from app.graph.gold_loader import load_gold

ROOT = Path(__file__).resolve().parents[2]
EXP = json.loads((ROOT / "ground_truth" / "expected_answers.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def A():
    db = FalkorDB(host=os.getenv("FALKORDB_HOST", "localhost"), port=int(os.getenv("FALKORDB_PORT", "6379")))
    g = db.select_graph("research_gold_test")
    load_gold(g, ROOT / "ground_truth" / "gold_graph.json")
    yield Analysis(g)
    g.delete()


def test_every_query_has_a_test_case(A):
    covered = {"pair_citations", "pair_shared_authors", "pair_shared_datasets", "pair_shared_methods", "pair_lineage",
               "pair_claims", "pair_result_links", "pair_quotes", "library_papers", "library_edges", "lineage_up",
               "lineage_down", "method_origin", "leaderboard", "claim_conflicts", "claim_support", "sota_check",
               "missing_cit_candidates", "missing_cit_shared_datasets", "missing_cit_similar_methods",
               "missing_cit_stronger_results", "stale_citations", "external_hubs", "gap_method_dataset", "gap_metric_coverage",
               "gap_dataset_depth", "gap_unreproduced", "gap_task_without_method", "influential_papers",
               "bridge_authors", "author_groups", "affiliation_history", "claim_pair_candidates", "unlinked_method_pairs"}
    assert covered == set(Q)
    assert len(A.run("library_papers")) == 12 and len(A.run("library_edges")) == 36 and len(A.run("method_origin")) == 8


def test_pair_reproduction(A):
    r = A.relationship("P03", "P08")
    assert r["citations"][0]["intent"] == "reproduces"
    assert r["shared_authors"]["authors"] == ["Jonas Weber"]
    assert len([x for x in r["result_links"] if x["relation"] == "REPRODUCES"]) == 4
    assert {(c["from_claim"], c["relation"], c["to_claim"]) for c in r["claims"]} == {("C08", "CONTRADICTS", "C03")}


def test_pair_extension_and_quotes(A):
    r = A.relationship("P06", "P10")
    assert [x["chain"] for x in r["lineage"]] == [["LiteGraphFuse", "GraphFuse"]]
    assert {(q["split"], q["value"]) for q in r["quotes"]} == {("2-hop", 57.9), ("3-hop", 46.3)}


def test_lineage(A):
    up = sorted(x["chain"] for x in A.run("lineage_up", method="m-litegraphfuse"))
    assert up == sorted(EXP["lineage"]["LiteGraphFuse_ancestors"])
    assert [x["chain"] for x in A.run("lineage_down", method="m-densehop")] == EXP["lineage"]["DenseHop_descendants"]


@pytest.mark.parametrize("key,args", [
    ("KaveriHop 3-hop EM", ("ds-kaveri", "3-hop", "metric-em")),
    ("TriHop-Bench 4-hop EM", ("ds-trihop", "4-hop", "metric-em")),
    ("KaveriHop latency (lower is better)", ("ds-kaveri", "all", "metric-latency")),
    ("VaigaiQA 2-hop EM", ("ds-vaigai", "2-hop", "metric-em")),
])
def test_leaderboards(A, key, args):
    got = [(r["method"], r["value"], r["paper"]) for r in A.leaderboard(*args)]
    want = [(r["method"], float(r["value"]), r["paper"]) for r in EXP["leaderboards"][key]]
    assert got == want


def test_corrected_value_wins(A):
    top = A.leaderboard("ds-trihop", "4-hop", "metric-em")[0]
    assert top["corrected"] and top["as_published"] == 22.7 and top["value"] == 19.4


def test_claims(A):
    conflicts = {(r["relation"], r["claim"], r["other_claim"]) for r in A.run("claim_conflicts")}
    assert {(c, o) for rel, c, o in conflicts if rel == "CONTRADICTS"} == {tuple(x) for x in EXP["claims"]["contradicts"]}
    assert {(c, o) for rel, c, o in conflicts if rel == "QUALIFIES"} == {tuple(x) for x in EXP["claims"]["qualifies"]}
    assert {(r["claim"], r["supported_claim"]) for r in A.run("claim_support")} == {tuple(x) for x in EXP["claims"]["supports"]}
    sota = {(r["claim"], r["dataset"], r["better_value"]) for r in A.run("sota_check")}
    assert sota == {("C12", "KaveriHop", 46.3), ("C12", "TriHop-Bench", 41.2)}


def test_citation_hygiene(A):
    flagged = {}
    for i in range(1, 13):
        pid = f"P{i:02d}"
        rows = A.missing_citations(pid, min_score=5)
        if rows:
            flagged[pid] = [(r["paper"], r["score"]) for r in rows]
    assert flagged == {"P12": [("P06", 10), ("P04", 5)]}
    assert [(r["paper"], r["cites"], r["correction"]) for r in A.run("stale_citations")] == [("P10", "P06", "P09")]
    hubs = {r["id"]: sorted(r["cited_by"]) for r in A.run("external_hubs", min=2)}
    assert hubs == {h["id"]: h["cited_by"] for h in EXP["citation_hygiene"]["external_hubs"]}


def test_gaps(A):
    never = {r["method"]: set(r["never_evaluated_on"]) for r in A.run("gap_method_dataset")}
    assert {m for m, ds in never.items() if "VaigaiQA" in ds} == set(EXP["research_gaps"]["never_evaluated_in_tamil"])
    latency = next(r for r in A.run("gap_metric_coverage") if r["metric"] == "Latency")
    assert set(latency["never_reported_on"]) == set(EXP["research_gaps"]["latency_never_reported_on"])
    assert {r["method"] for r in A.run("gap_unreproduced")} == set(EXP["research_gaps"]["never_independently_reproduced"])
    task = A.run("gap_task_without_method")[0]
    assert task["task"] == "Entity linking" and sorted(task["claims"]) == ["C07", "C08", "C11"]
    tamil = [r for r in A.run("gap_dataset_depth") if r["language"] == "Tamil"]
    assert tamil == [{"dataset": "VaigaiQA", "language": "Tamil", "splits": ["2-hop"]}]


def test_people_and_algorithms(A):
    assert A.run("influential_papers", k=1)[0]["id"] == "P01"
    assert {r["author"] for r in A.run("bridge_authors", k=2)} == set(EXP["people"]["bridge_authors_top2"])
    groups = [sorted(r["authors"]) for r in A.run("author_groups")]
    assert sorted(EXP["people"]["isolated_group"]) in groups
    hist = [[r["institution"], r["first_year"], r["last_year"]] for r in A.run("affiliation_history", author="auth-mehta")]
    assert hist == EXP["people"]["affiliation_change"]["history"]


def test_llm_candidate_generation(A):
    # Gold relations are already in the graph, so remove them to see what the candidate query would send to the LLM.
    A.graph.query("MATCH (:Claim)-[r:SUPPORTS|CONTRADICTS|QUALIFIES]->(:Claim) WITH r, startNode(r).id AS a, endNode(r).id AS b, type(r) AS t "
                  "CREATE (:Tmp {a: a, b: b, t: t}) DELETE r")
    pairs = {(r["newer"], r["older"]) for r in A.run("claim_pair_candidates")}
    gold = {tuple(x) for k in ("contradicts", "qualifies", "supports") for x in EXP["claims"][k]}
    assert gold <= pairs and len(pairs) <= 40          # every true relation is a candidate; LLM sees under 40 pairs
    for a, b, t in A.graph.query("MATCH (x:Tmp) RETURN x.a, x.b, x.t").result_set:
        A.graph.query(f"MATCH (c1:Claim {{id: $a}}), (c2:Claim {{id: $b}}) CREATE (c1)-[:{t}]->(c2)", {"a": a, "b": b})
    A.graph.query("MATCH (x:Tmp) DELETE x")
    unlinked = {(r["name_a"], r["name_b"]) for r in A.run("unlinked_method_pairs")}
    assert ("HopLens", "HopRank") in unlinked or ("HopRank", "HopLens") in unlinked
    assert not {("GraphFuse", "LiteGraphFuse"), ("DenseHop", "HopRank")} & unlinked   # lineage already explains these
