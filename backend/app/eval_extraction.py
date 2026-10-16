"""Score the extracted graph against ground_truth/gold_graph.json.

Usage (from backend/):  python -m app.eval_extraction --workspace demo
Prints precision / recall per relationship type. Put the table in your README: judges trust measured numbers.
"""
import argparse
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

from rapidfuzz import fuzz

ROOT = Path(__file__).resolve().parents[2]


def words(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode()
    return " ".join(re.findall(r"[a-z0-9]+", t.lower()))


def norm(t: str) -> str:
    return words(t).replace(" ", "")


def pr(got: set | Counter, want: set | Counter) -> dict:
    if isinstance(got, Counter):
        tp = sum((got & want).values())
        g, w = sum(got.values()), sum(want.values())
    else:
        tp, g, w = len(got & want), len(got), len(want)
    return {"precision": round(tp / g, 3) if g else 0.0, "recall": round(tp / w, 3) if w else 0.0, "got": g, "want": w}


def score(graph) -> dict:
    gold = json.loads((ROOT / "ground_truth" / "gold_graph.json").read_text(encoding="utf-8"))
    gn = {n["id"]: n for n in gold["nodes"]}
    ge = gold["edges"]
    rs = lambda c: graph.ro_query(c).result_set          # scoring only reads

    # Map extracted nodes onto gold ids: papers by title, methods/datasets by any alias.
    gold_paper = {words(n["props"]["title"]): n["id"] for n in gold["nodes"] if n["label"] == "Paper"}
    alias = {(n["label"], norm(a)): n["id"] for n in gold["nodes"] if n["label"] in ("Method", "Dataset") for a in n["props"]["aliases"]}
    paper_map = {pid: gold_paper.get(words(t), f"?{pid}") for pid, t in rs("MATCH (p:Paper) RETURN p.id, p.title")}
    ent_map = {}
    for label in ("Method", "Dataset"):
        for eid, keys in rs(f"MATCH (e:{label}) RETURN e.id, e.keys"):
            hits = {alias.get((label, k)) for k in (keys or [])} - {None}
            ent_map[eid] = hits.pop() if len(hits) == 1 else f"?{eid}"
    claim_map = {}
    gold_claims = [(words(n["props"]["text"]), n["id"]) for n in gold["nodes"] if n["label"] == "Claim"]
    for cid, text in rs("MATCH (c:Claim) RETURN c.id, c.text"):
        best = max(gold_claims, key=lambda g: fuzz.token_set_ratio(words(text), g[0]))
        claim_map[cid] = best[1] if fuzz.token_set_ratio(words(text), best[0]) >= 85 else f"?{cid}"

    def mapped(a, b):
        return paper_map.get(a) or ent_map.get(a) or claim_map.get(a) or a, paper_map.get(b) or ent_map.get(b) or claim_map.get(b) or b

    report = {}
    for rel in ("CITES", "PROPOSES", "INTRODUCES", "EVALUATES_ON", "USES", "EXTENDS", "SIMILAR_TO", "CORRECTS",
                "SUPPORTS", "CONTRADICTS", "QUALIFIES"):
        got = {mapped(a, b) for a, b in rs(f"MATCH (a)-[:{rel}]->(b) WHERE NOT a:Result RETURN a.id, b.id")}
        want = {(e["src"], e["dst"]) for e in ge if e["type"] == rel and gn[e["src"]]["label"] != "Result"}
        report[rel] = pr(got, want)

    gold_intent = {(e["src"], e["dst"]): e["props"]["intent"] for e in ge if e["type"] == "CITES"}
    rows = rs("MATCH (a:Paper)-[c:CITES]->(b:Paper) RETURN a.id, b.id, c.intent")
    judged = [(gold_intent.get(mapped(a, b)), i) for a, b, i in rows if mapped(a, b) in gold_intent]
    report["CITES.intent_accuracy"] = round(sum(g == i for g, i in judged) / len(judged), 3) if judged else 0.0
    report["CITES.intent_confusions"] = Counter((g, i) for g, i in judged if g != i).most_common(5)

    res_edges = {}
    for e in ge:
        res_edges.setdefault(e["src"], {})[e["type"]] = e["dst"]
    want_r = Counter()
    for n in gold["nodes"]:
        if n["label"] == "Result":
            x = res_edges[n["id"]]
            want_r[(n["props"]["paper"], x["OF_METHOD"], x["ON_DATASET"], n["props"]["split"], x["MEASURED_BY"],
                    round(n["props"]["value"], 1), n["props"]["origin"])] += 1
    got_r = Counter()
    for p, m, d, sp, mt, v, o in rs("""MATCH (p:Paper)-[:REPORTS]->(r:Result)-[:OF_METHOD]->(m), (r)-[:ON_DATASET]->(d),
                                             (r)-[:MEASURED_BY]->(mt) RETURN p.id, m.id, d.id, r.split, mt.id, r.value, r.origin"""):
        got_r[(paper_map.get(p), ent_map.get(m), ent_map.get(d), sp, mt, round(v, 1), o)] += 1
    report["Result"] = pr(got_r, want_r)
    report["Claim"] = pr(set(claim_map.values()), {n["id"] for n in gold["nodes"] if n["label"] == "Claim"})
    report["unmapped"] = sorted(v for v in list(paper_map.values()) + list(ent_map.values()) if v.startswith("?"))
    return report


if __name__ == "__main__":
    from app.graph.client import UnknownWorkspace, graph_for

    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", required=True, help="workspace name; the graph is ws_<workspace>")
    args = ap.parse_args()
    try:
        graph = graph_for(args.workspace, must_exist=True)
    except UnknownWorkspace as e:
        raise SystemExit(str(e))
    rep = score(graph)
    width = max(len(k) for k in rep)
    for k, v in rep.items():
        print(f"{k:<{width}}  {v}")
