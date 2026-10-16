"""Enrichment after deterministic ingestion. The graph picks the work; the LLM only judges small, closed questions.

classify_citations    CITES intent: graph facts and explicit wording decide most; the LLM judges prose-only citations
extract_claims        Claim nodes + ABOUT edges (LLM picks sentence numbers; entities resolved by the graph)
link_similar_methods  SIMILAR_TO between methods with no lineage and no citation (embeddings, no LLM)
relate_claims         SUPPORTS / CONTRADICTS / QUALIFIES, only for pairs the graph selects (LLM)
check_claims          CONFLICTS_WITH_RESULT from sota_check (pure Cypher, no LLM)

Run everything for a workspace:  python -m app.agent.enrich --workspace demo
"""
import hashlib
import math
import re
from collections import Counter

from app.agent import llm
from app.docs.docstore import EMBED_MODEL
from app.graph.analysis import Analysis
from app.graph.ingest import keyword_intent, norm, q, reconcile, words


# ---------------------------------------------------------------- 1. citation intent
# What the graph can prove about why paper $a cites paper $b. Each query returns true or false.
FACT_Q = {
    "erratum_of": "MATCH (:Paper {id: $a})-[:CORRECTS]->(:Paper {id: $b}) RETURN count(*) > 0",
    "reruns_their_method": """MATCH (:Paper {id: $a})-[:REPORTS]->(:Result {origin: 'reproduced'})-[:OF_METHOD]->(:Method)
                                    <-[:PROPOSES]-(:Paper {id: $b})
                              RETURN count(*) > 0""",
    # a dataset counts as theirs if they introduced it, or if it is always cited next to them (citation anchor)
    "uses_their_dataset": """MATCH (:Paper {id: $a})-[:EVALUATES_ON]->(d:Dataset)
                             OPTIONAL MATCH (b:Paper {id: $b})-[:INTRODUCES]->(d)
                             WITH d, b WHERE b IS NOT NULL OR $b IN d.anchors
                             RETURN count(d) > 0""",
    "quotes_their_numbers": "MATCH (:Paper {id: $a})-[:REPORTS]->(:Result)-[:QUOTED_FROM]->(:Paper {id: $b}) RETURN count(*) > 0",
    # their method has a result next to another method's result on the same dataset, split and metric: a comparison
    "ranks_their_method": """MATCH (a:Paper {id: $a})-[:REPORTS]->(r:Result)-[:OF_METHOD]->(m:Method)
                             OPTIONAL MATCH (b:Paper {id: $b})-[:PROPOSES]->(m)
                             WITH a, r, m, b WHERE b IS NOT NULL OR $b IN m.anchors
                             MATCH (a)-[:REPORTS]->(r2:Result)-[:OF_METHOD]->(m2:Method)
                             WHERE m2 <> m AND r2.split = r.split
                             WITH r, r2
                             MATCH (r)-[:ON_DATASET]->(:Dataset)<-[:ON_DATASET]-(r2),
                                   (r)-[:MEASURED_BY]->(:Metric)<-[:MEASURED_BY]-(r2)
                             RETURN count(*) > 0""",
    "uses_their_method": """MATCH (:Paper {id: $a})-[:USES]->(m:Method)
                            OPTIONAL MATCH (b:Paper {id: $b})-[:PROPOSES]->(m)
                            WITH m, b WHERE b IS NOT NULL OR $b IN m.anchors
                            RETURN count(m) > 0""",
}
EXTENDS_CUE = re.compile(r"\bextends?\b|\bbuilds? on\b")
SUPPORTS_CUE = re.compile(r"\bsupports?\b|\bconsistent with\b")
# What is left after the rules has no structural trace in the graph: only the prose can tell.
PROSE_ONLY = ["background", "uses_method", "supports", "criticizes"]


def citation_facts(graph, a: str, b: str) -> set:
    """The facts from FACT_Q that hold for paper a citing paper b."""
    return {name for name, cypher in FACT_Q.items() if q(graph, cypher, a=a, b=b)[0][0]}


def rule_intent(facts: set, contexts: list) -> tuple[str | None, str | None]:
    """Decide the intent from graph facts and explicit wording, in order of how certain each rule is.
    Returns (None, None) when nothing applies; the LLM then judges from the sentences."""
    text = " ".join(contexts).lower()
    if "erratum_of" in facts:
        return "corrects", "graph"
    if EXTENDS_CUE.search(text):
        return "extends", "keywords"
    if SUPPORTS_CUE.search(text):
        return "supports", "keywords"
    if "reruns_their_method" in facts and "baseline" not in text:     # re-run to check it, not as a baseline
        return "reproduces", "graph"
    if "uses_their_dataset" in facts:
        return "uses_dataset", "graph"
    if facts & {"reruns_their_method", "quotes_their_numbers", "ranks_their_method"}:
        return "compares_against", "graph"
    if "uses_their_method" in facts:
        return "uses_method", "graph"
    return None, None


def classify_citations(graph, paper_id: str | None = None, use_llm: bool = True) -> Counter:
    """The graph decides every intent it can prove; the LLM judges only prose-only citations, from a short list.
    use_llm=False uses keyword rules for those instead (the baseline the LLM is measured against)."""
    rows = q(graph, """MATCH (a:Paper {in_library: true})-[c:CITES]->(b:Paper)
                       WHERE c.intent = 'unclassified' AND ($pid IS NULL OR a.id = $pid)
                       RETURN a.id, a.title, b.id, b.title, c.contexts""", pid=paper_id)
    sources = Counter()
    for a, a_title, b, b_title, contexts in rows:
        intent, source = rule_intent(citation_facts(graph, a, b), contexts or [])
        if intent is None and use_llm:
            intent, source = llm.classify_intent(a_title, b_title, contexts or [], keyword_intent, PROSE_ONLY)
        elif intent is None:
            guess = keyword_intent(contexts or [])
            intent, source = (guess if guess in PROSE_ONLY else "background"), "keywords"
        q(graph, """MATCH (:Paper {id: $a})-[c:CITES]->(:Paper {id: $b})
                    SET c.intent = $intent, c.intent_source = $source""", a=a, b=b, intent=intent, source=source)
        sources[source] += 1
    if rows:
        reconcile(graph)            # lineage: proposing paper CITES another with intent 'extends' -> EXTENDS
    return sources


# ---------------------------------------------------------------- 2. claims
def known_entities(graph) -> list:
    """Every Method and Dataset with its spellings and the paper that introduced it (helps the LLM map
    general phrases like 'graph-based retrieval' to GraphWalker-QA)."""
    rows = q(graph, """MATCH (e) WHERE e:Method OR e:Dataset
                       OPTIONAL MATCH (p:Paper)-[:PROPOSES|INTRODUCES]->(e)
                       RETURN e.id, e.name, e.aliases, e.keys, labels(e)[0], p.title""")
    out = {}
    for eid, name, aliases, keys, label, origin in rows:
        e = out.setdefault(eid, {"id": eid, "name": name, "label": label, "aliases": aliases or [name],
                                 "keys": keys or [norm(name)], "origin": origin})
        e["origin"] = e["origin"] or origin
    for e in out.values():
        other = [a for a in e["aliases"] if a != e["name"]]
        e["note"] = (f"{e['name']} ({e['label'].lower()}" + (f"; also written {', '.join(other)}" if other else "")
                     + (f"; introduced in \"{e['origin']}\"" if e["origin"] else "") + ")")
    return list(out.values())


def _resolve_dataset(ents: list, name: str) -> str | None:
    key = norm(name)
    hits = [e["id"] for e in ents if e["label"] == "Dataset" and (key in e["keys"] or any(
        len(k) >= 5 and len(key) >= 5 and (k.startswith(key) or key.startswith(k)) for k in e["keys"]))]
    return hits[0] if len(set(hits)) == 1 else None


def _scope(text: str, items: list, ents: list, ontology: dict) -> list:
    """sota scope as '<dataset id>|<split>|<metric id>'. Uses the model's items; if none are valid,
    derives them from the sentence itself (datasets named x splits named x metrics named)."""
    metric_of = {norm(a): m["id"] for m in ontology["metrics"] for a in m["aliases"] + [m["name"]]}
    out = []
    for item in items or []:
        parts = [p.strip() for p in item.split("|")]
        if len(parts) == 3 and re.fullmatch(r"\d+-hop", parts[1].lower()):
            did, mid = _resolve_dataset(ents, parts[0]), metric_of.get(norm(parts[2]))
            if did and mid:
                out.append(f"{did}|{parts[1].lower()}|{mid}")
    if out:
        return sorted(set(out))
    w = f" {words(text)} "
    datasets = {e["id"] for e in ents if e["label"] == "Dataset"
                and any(f" {words(a)} " in w for a in e["aliases"] if len(norm(a)) >= 4)}
    splits = set(re.findall(r"\b(\d+)-hop\b", text.lower()))
    metrics = {m["id"] for m in ontology["metrics"] for a in m["aliases"] + [m["name"]] if f" {words(a)} " in w}
    return sorted(f"{d}|{s}-hop|{m}" for d in datasets for s in splits for m in metrics)


def extract_claims(graph, paper_id: str, ontology: dict) -> list:
    rows = q(graph, "MATCH (p:Paper {id: $id}) RETURN p.title, p.abstract, p.final_section, p.final_text", id=paper_id)
    if not rows:
        return []
    title, abstract, final_heading, final_text = rows[0]
    ents = known_entities(graph)
    key_to_id = {k: e["id"] for e in ents for k in e["keys"] + [norm(a) for a in e["aliases"]]}
    found = llm.extract_claims(title, abstract or "", final_text or "", [e["name"] for e in ents],
                               [e["note"] for e in ents])
    own = [r[0] for r in q(graph, "MATCH (:Paper {id: $id})-[:PROPOSES|INTRODUCES]->(e) RETURN e.id", id=paper_id)]
    label = {e["id"]: e["label"] for e in ents}
    saved = []
    for c in found:
        ids = {key_to_id[norm(n)] for n in c.get("about", []) if norm(n) in key_to_id}
        # The graph adds what it can decide without the model: entities named in the sentence itself, and the
        # paper's own method or dataset (a finding in its abstract or conclusion is about what the paper contributes).
        sentence = f" {words(c['text'])} "
        ids |= {e["id"] for e in ents if any(f" {words(a)} " in sentence for a in e["aliases"] if len(norm(a)) >= 4)}
        ids |= set(own)
        if not ids:
            continue
        cid = "claim-" + hashlib.sha1(f"{paper_id}|{words(c['text'])}".encode()).hexdigest()[:10]
        section = "Abstract" if words(c["text"]) in words(abstract or "") else (final_heading or "")
        scope = _scope(c["text"], c.get("scope"), ents, ontology) if c["type"] == "sota" else []
        q(graph, """MATCH (p:Paper {id: $pid})
                    MERGE (c:Claim {id: $cid})
                    SET c.text = $text, c.type = $type, c.section = $section, c.scope = $scope, c.source = 'llm'
                    MERGE (p)-[:MAKES]->(c)""",
          pid=paper_id, cid=cid, text=c["text"], type=c["type"], section=section, scope=scope)
        for eid in sorted(ids):
            q(graph, f"MATCH (c:Claim {{id: $cid}}), (e:{label[eid]} {{id: $eid}}) MERGE (c)-[:ABOUT]->(e)", cid=cid, eid=eid)
        saved.append({"id": cid, "text": c["text"], "type": c["type"], "about": sorted(ids), "scope": scope})
    return saved


# ---------------------------------------------------------------- 3. method similarity
def cosine(a: list, b: list) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    return dot / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)) or 1.0)


def link_similar_methods(graph, store, threshold: float = 0.85, paper_id: str | None = None) -> list:
    """Compare the Method sections of papers whose methods have no lineage and no citation between them.
    A high score there means 'possible uncredited prior work'. Returns every scored pair, best first."""
    published = dict(q(graph, "MATCH (p:Paper {in_library: true}) RETURN p.id, p.published"))
    scored = []
    for r in Analysis(graph).run("unlinked_method_pairs"):
        if paper_id and paper_id not in (r["paper_a"], r["paper_b"]):
            continue
        va, vb = store.section_vector(r["paper_a"], "Method"), store.section_vector(r["paper_b"], "Method")
        if va is None or vb is None:
            continue
        r["score"] = round(float(cosine(va, vb)), 3)          # ChromaDB returns numpy numbers
        scored.append(r)
        if r["score"] >= threshold:
            a_newer = (published.get(r["paper_a"]) or "") >= (published.get(r["paper_b"]) or "")
            newer, older = (r["method_a"], r["method_b"]) if a_newer else (r["method_b"], r["method_a"])
            q(graph, """MATCH (a:Method {id: $a}), (b:Method {id: $b})
                        MERGE (a)-[s:SIMILAR_TO]->(b)
                        SET s.score = $score, s.basis = 'method-section embedding', s.detected_by = $model""",
              a=newer, b=older, score=r["score"], model=EMBED_MODEL)
    return sorted(scored, key=lambda r: -r["score"])


# ---------------------------------------------------------------- 4. claim relations
def _context(store, paper_id: str | None, text: str) -> str:
    """One passage around the claim, searched only inside the paper that makes it."""
    if store is None or paper_id is None:
        return ""
    hits = store.evidence(text, [paper_id], k=1)
    return hits[0]["excerpt"] if hits else ""


def relate_claims(graph, store=None, paper_id: str | None = None) -> Counter:
    """Pairs the graph selects: claims from different papers about the same method, newer -> older,
    where the newer paper cites the older one (a finding can only answer a finding its authors read)."""
    cites = {(a, b): i for a, b, i in q(graph, "MATCH (a:Paper)-[c:CITES]->(b:Paper) RETURN a.id, b.id, c.intent")}
    paper = dict(q(graph, "MATCH (p:Paper)-[:MAKES]->(c:Claim) RETURN c.id, p.id"))
    rows = [r for r in Analysis(graph).run("claim_pair_candidates")
            if (paper.get(r["newer"]), paper.get(r["older"])) in cites
            and (paper_id is None or paper_id in (paper.get(r["newer"]), paper.get(r["older"])))]
    # All embeddings first, then all LLM calls: alternating the two models makes Ollama swap them in and out.
    contexts = {}
    for r in rows:
        for cid, text in ((r["newer"], r["newer_text"]), (r["older"], r["older_text"])):
            if cid not in contexts:
                contexts[cid] = _context(store, paper.get(cid), text)
    datasets = {}
    for cid, did in q(graph, "MATCH (c:Claim)-[:ABOUT]->(d:Dataset) RETURN c.id, d.id"):
        datasets.setdefault(cid, set()).add(did)
    verdicts = Counter()
    for r in rows:
        intent = cites[(paper[r["newer"]], paper[r["older"]])]
        facts = [f"The newer paper cites the older paper (citation intent: {intent}).",
                 f"Both findings are about: {', '.join(r['shared_methods'] + r['shared_datasets'])}."]
        newer = {"text": r["newer_text"], "paper_title": r["newer_paper"], "context": contexts[r["newer"]]}
        older = {"text": r["older_text"], "paper_title": r["older_paper"], "context": contexts[r["older"]]}
        out = llm.judge_claims(newer, older, facts)
        # QUALIFIES means "holds only in a narrower setting": the graph must see that setting, i.e. the newer
        # finding covers a dataset the older one does not. Otherwise the verdict is not accepted.
        if out["relation"] == "QUALIFIES" and not datasets.get(r["newer"], set()) - datasets.get(r["older"], set()):
            out = {"relation": "UNRELATED", "basis": "QUALIFIES rejected: no new setting in the graph"}
            verdicts["QUALIFIES rejected"] += 1
        verdicts[out["relation"]] += 1
        if out["relation"] in ("SUPPORTS", "CONTRADICTS", "QUALIFIES"):     # closed list: safe to put in Cypher
            q(graph, f"""MATCH (a:Claim {{id: $a}}), (b:Claim {{id: $b}})
                         MERGE (a)-[x:{out['relation']}]->(b) SET x.basis = $basis, x.source = 'llm'""",
              a=r["newer"], b=r["older"], basis=out.get("basis", ""))
    return verdicts


# ---------------------------------------------------------------- 5. claims checked against numbers
def check_claims(graph) -> int:
    """A 'state of the art' claim beaten by an earlier, correction-aware result gets CONFLICTS_WITH_RESULT."""
    n = 0
    for r in Analysis(graph).run("sota_check"):
        basis = (f"{r['better_method']} reports {r['better_value']} on {r['dataset']} {r['split']}; "
                 f"the claim's own result is {r['claimed_value']}")
        n += q(graph, """MATCH (c:Claim {id: $claim}),
                               (:Paper {id: $paper})-[:REPORTS]->(res:Result)-[:OF_METHOD]->(:Method {name: $method}),
                               (res)-[:ON_DATASET]->(:Dataset {name: $dataset})
                         WHERE res.split = $split AND res.origin IN ['proposed', 'baseline_run', 'reproduced']
                         MERGE (c)-[x:CONFLICTS_WITH_RESULT]->(res) SET x.basis = $basis
                         RETURN count(x)""",
               claim=r["claim"], paper=r["better_paper"], method=r["better_method"], dataset=r["dataset"],
               split=r["split"], basis=basis)[0][0]
    return n


# ---------------------------------------------------------------- start again
def reset_enrichment(graph) -> None:
    """Undo everything this module wrote, keep what ingestion wrote: intents back to 'unclassified',
    derived EXTENDS and SIMILAR_TO removed, claims (and their ABOUT, relation and conflict edges) deleted."""
    q(graph, "MATCH ()-[c:CITES]->() SET c.intent = 'unclassified', c.intent_source = NULL")
    q(graph, "MATCH ()-[e:EXTENDS|SIMILAR_TO]->() DELETE e")
    q(graph, "MATCH (c:Claim) DETACH DELETE c")


# ---------------------------------------------------------------- CLI
if __name__ == "__main__":
    import argparse
    import json
    import time
    from pathlib import Path

    from app.config import settings
    from app.docs.docstore import DocStore
    from app.graph.client import UnknownWorkspace, graph_for

    ap = argparse.ArgumentParser(description="LLM enrichment and method similarity for one workspace.")
    ap.add_argument("--workspace", required=True)
    ap.add_argument("--threshold", type=float, default=0.85, help="SIMILAR_TO cut-off for method-section cosine")
    ap.add_argument("--steps", default="intents,claims,similarity,relations,check")
    ap.add_argument("--intents-by", choices=["llm", "keywords"], default="llm")
    ap.add_argument("--redo", action="store_true", help="undo earlier enrichment first (ingested data is kept)")
    args = ap.parse_args()
    try:
        graph = graph_for(args.workspace, must_exist=True)
    except UnknownWorkspace as e:
        raise SystemExit(str(e))
    store = DocStore(str(settings.chroma_path), args.workspace)
    ontology = json.loads((Path(__file__).resolve().parents[3] / "ontology.json").read_text(encoding="utf-8"))
    papers = [r[0] for r in q(graph, "MATCH (p:Paper {in_library: true}) RETURN p.id ORDER BY p.published")]
    steps = args.steps.split(",")
    if args.redo:
        reset_enrichment(graph)
        print("redo        earlier enrichment removed")

    def timed(label, fn):
        t0 = time.time()
        result = fn()
        shown = f"{len(result)} pairs scored" if isinstance(result, list) else result
        print(f"{label:<11} {shown}   ({time.time() - t0:.0f}s)")
        return result

    if "intents" in steps:
        timed("intents", lambda: dict(classify_citations(graph, use_llm=args.intents_by == "llm")))
    if "claims" in steps:
        timed("claims", lambda: sum(len(extract_claims(graph, p, ontology)) for p in papers))
    if "similarity" in steps:
        if store.col.count() == 0:
            print("similarity  skipped: ChromaDB is empty. Run: python -m app.graph.ingest --workspace "
                  f"{args.workspace} --index ../corpus/pdf")
        else:
            pairs = timed("similarity", lambda: link_similar_methods(graph, store, args.threshold))
            for r in pairs:
                mark = "SIMILAR_TO" if r["score"] >= args.threshold else ""
                print(f"            {r['score']:.3f}  {r['name_a']} ~ {r['name_b']}  {mark}")
    if "relations" in steps:
        timed("relations", lambda: dict(relate_claims(graph, store)))
    if "check" in steps:
        timed("check", lambda: check_claims(graph))
