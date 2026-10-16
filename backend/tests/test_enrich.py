"""Enrichment with a perfect fake LLM that answers from the gold graph.

This proves the graph logic on its own: candidate pairs, entity resolution, sota scope, EXTENDS from
intents, CONFLICTS_WITH_RESULT, method similarity. If these pass, any gap in the real run is model
quality, not pipeline wiring. Run: pytest tests/test_enrich.py -v
"""
import hashlib
import json
import math
import os
import re
from pathlib import Path

import pytest
from falkordb import FalkorDB

from app.agent import enrich, llm
from app.docs.docstore import DocStore
from app.eval_extraction import score
from app.graph.ingest import ingest_pdf, words

ROOT = Path(__file__).resolve().parents[2]
PDFS = sorted((ROOT / "corpus" / "pdf").glob("*.pdf"))
ONTOLOGY = json.loads((ROOT / "ontology.json").read_text(encoding="utf-8"))
GOLD = json.loads((ROOT / "ground_truth" / "gold_graph.json").read_text(encoding="utf-8"))
NODE = {n["id"]: n for n in GOLD["nodes"]}
BY_TITLE = {words(n["props"]["title"]): n["id"] for n in GOLD["nodes"] if n["label"] == "Paper"}
INTENT = {(e["src"], e["dst"]): e["props"]["intent"] for e in GOLD["edges"] if e["type"] == "CITES"}
MAKES = {e["dst"]: e["src"] for e in GOLD["edges"] if e["type"] == "MAKES"}
ABOUT = {}
for e in GOLD["edges"]:
    if e["type"] == "ABOUT":
        ABOUT.setdefault(e["src"], []).append(NODE[e["dst"]]["props"]["name"])
CLAIM_BY_TEXT = {words(n["props"]["text"]): n["id"] for n in GOLD["nodes"] if n["label"] == "Claim"}
RELATION = {(e["src"], e["dst"]): e["type"] for e in GOLD["edges"] if e["type"] in ("SUPPORTS", "CONTRADICTS", "QUALIFIES")}
SCOPE_AS_MODEL_WRITES_IT = {"C12": ["KaveriHop|3-hop|EM", "TriHop-Bench|3-hop|EM"]}


def fake_intent(citing_title, cited_title, contexts, fallback, options=None, facts=None):
    """A perfect model that can still only answer from the options the graph allows."""
    options = options or llm.INTENTS
    gold = INTENT[(BY_TITLE[words(citing_title)], BY_TITLE[words(cited_title)])]
    return (gold if gold in options else options[0]), "llm"


def fake_claims(title, abstract, conclusion, known, notes=None):
    pid = BY_TITLE[words(title)]
    return [{"text": NODE[c]["props"]["text"], "type": NODE[c]["props"]["type"], "about": ABOUT[c],
             "scope": SCOPE_AS_MODEL_WRITES_IT.get(c, [])} for c, p in MAKES.items() if p == pid]


def fake_judge(newer, older, facts=None):
    rel = RELATION.get((CLAIM_BY_TEXT[words(newer["text"])], CLAIM_BY_TEXT[words(older["text"])]), "UNRELATED")
    return {"relation": rel, "basis": "gold"}


def fake_embed(texts, kind):
    """Bag of words hashed into 256 dimensions (offline stand-in for nomic-embed-text)."""
    out = []
    for t in texts:
        v = [0.0] * 256
        for w in re.findall(r"[a-z]+", t.lower()):
            v[int(hashlib.md5(w.encode()).hexdigest(), 16) % 256] += 1.0
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        out.append([x / n for x in v])
    return out


@pytest.fixture(scope="module")
def enriched(tmp_path_factory):
    db = FalkorDB(host=os.getenv("FALKORDB_HOST", "localhost"), port=int(os.getenv("FALKORDB_PORT", "6379")))
    g = db.select_graph("enrich_test")
    try:
        g.delete()
    except Exception:
        pass
    g = db.select_graph("enrich_test")
    store = DocStore(str(tmp_path_factory.mktemp("chroma")), "enrich_test", embed=fake_embed)
    for f in PDFS:
        ingest_pdf(g, f, ONTOLOGY, store)
    mp = pytest.MonkeyPatch()
    mp.setattr(llm, "classify_intent", fake_intent)
    mp.setattr(llm, "extract_claims", fake_claims)
    mp.setattr(llm, "judge_claims", fake_judge)
    papers = [r[0] for r in g.query("MATCH (p:Paper {in_library: true}) RETURN p.id").result_set]
    out = {"intents": enrich.classify_citations(g),
           "claims": sum(len(enrich.extract_claims(g, p, ONTOLOGY)) for p in papers),
           "candidates": len(enrich.Analysis(g).run("claim_pair_candidates")),
           "relations": enrich.relate_claims(g, store),
           "conflicts": enrich.check_claims(g),
           "similar": enrich.link_similar_methods(g, store, threshold=2.0),     # score only, write nothing
           "report": score(g)}
    mp.undo()
    yield g, out
    g.delete()


def test_intents_give_lineage(enriched):
    g, out = enriched
    rep = out["report"]
    assert out["intents"] == {"graph": 30, "keywords": 6, "llm": 13}   # the LLM only sees prose-only citations
    assert rep["CITES.intent_accuracy"] >= 0.97                  # 48/49: gold calls one re-run baseline 'uses_method'
    assert rep["EXTENDS"] == {"precision": 1.0, "recall": 1.0, "got": 4, "want": 4}


def test_claims_and_their_entities(enriched):
    g, out = enriched
    assert out["claims"] == 13 and out["report"]["Claim"]["recall"] == 1.0
    scope = g.query("MATCH (c:Claim {type: 'sota'}) RETURN c.scope").result_set[0][0]
    ids = dict(g.query("MATCH (d:Dataset) RETURN d.name, d.id").result_set)
    assert sorted(scope) == sorted(f"{ids[n]}|3-hop|metric-em" for n in ("KaveriHop", "TriHop-Bench"))   # names -> graph ids


def test_graph_picks_the_pairs_and_relations_match_gold(enriched):
    g, out = enriched
    judged = sum(out["relations"].values())
    assert judged < out["candidates"] < 13 * 12 // 2           # 78 possible pairs -> same-method pairs -> cited pairs
    for rel in ("SUPPORTS", "CONTRADICTS", "QUALIFIES"):
        assert out["report"][rel]["precision"] == 1.0, rel
    assert out["report"]["SUPPORTS"]["recall"] == out["report"]["CONTRADICTS"]["recall"] == 1.0
    # QUALIFIES 1 of 3: VaigaiQA never cites TriHop-Bench (pair skipped), and LiteGraphFuse's Tamil finding adds
    # no dataset the VaigaiQA finding lacks (the guard needs a narrower setting it can see in the graph).
    assert out["report"]["QUALIFIES"]["recall"] >= 0.33


def test_sota_claim_conflicts_with_graphfuse(enriched):
    g, out = enriched
    rows = g.query("""MATCH (:Claim {type: 'sota'})-[:CONFLICTS_WITH_RESULT]->(r:Result)-[:OF_METHOD]->(m:Method)
                      RETURN m.name, r.split, r.value ORDER BY r.value DESC""").result_set
    assert out["conflicts"] == 2 and {m for m, _, _ in rows} == {"GraphFuse"}


def test_similarity_scores_every_unlinked_pair(enriched):
    g, out = enriched
    pairs = out["similar"]
    assert pairs and all(-1.0 <= p["score"] <= 1.0 for p in pairs)
    assert {pairs[0]["name_a"], pairs[0]["name_b"]} == {"HopLens", "HopRank"}       # the planted look-alike ranks first


def test_sota_scope_falls_back_to_the_sentence(enriched):
    g, _ = enriched
    ids = dict(g.query("MATCH (d:Dataset) RETURN d.name, d.id").result_set)
    text = "HopLens achieves state-of-the-art exact match on 3-hop questions in both KaveriHop and TriHop-Bench."
    assert enrich._scope(text, [], enrich.known_entities(g), ONTOLOGY) == sorted(
        f"{ids[n]}|3-hop|metric-em" for n in ("KaveriHop", "TriHop-Bench"))     # no model scope: read it from the sentence


def test_reset_keeps_ingestion_and_removes_enrichment(enriched):
    g, _ = enriched
    enrich.reset_enrichment(g)
    rows = g.query("""MATCH ()-[c:CITES]->() WITH count(c) AS cites, sum(CASE WHEN c.intent = 'unclassified' THEN 1 ELSE 0 END) AS open
                      RETURN cites, open""").result_set[0]
    assert rows == [49, 49]
    assert g.query("MATCH (c:Claim) RETURN count(c)").result_set[0][0] == 0
    assert g.query("MATCH ()-[e:EXTENDS|SIMILAR_TO]->() RETURN count(e)").result_set[0][0] == 0
    assert g.query("MATCH (r:Result) RETURN count(r)").result_set[0][0] == 70


def test_graph_rules_decide_most_intents_correctly(enriched):
    g, _ = enriched
    decided = right = 0
    for a, a_title, b, b_title, contexts in g.query("""MATCH (a:Paper)-[c:CITES]->(b:Paper)
                                                       RETURN a.id, a.title, b.id, b.title, c.contexts""").result_set:
        intent, _ = enrich.rule_intent(enrich.citation_facts(g, a, b), contexts or [])
        if intent is not None:
            decided += 1
            right += intent == INTENT[(BY_TITLE[words(a_title)], BY_TITLE[words(b_title)])]
    assert decided == 36 and right >= 35          # 36 of 49 citations need no LLM; the other 13 are prose-only
