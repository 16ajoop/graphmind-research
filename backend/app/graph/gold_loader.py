"""Oracle mode: load ground_truth/gold_graph.json straight into FalkorDB.

Use it to build and test the analysis queries, agent and UI before PDF extraction is finished,
and as the reference when scoring extraction. Never present oracle mode as extraction in the demo.
"""
import json
from collections import defaultdict
from pathlib import Path


def load_gold(graph, path: Path) -> dict:
    gold = json.loads(Path(path).read_text(encoding="utf-8"))
    try:
        graph.delete()
    except Exception:
        pass
    label_of = {n["id"]: n["label"] for n in gold["nodes"]}
    by_label = defaultdict(list)
    for n in gold["nodes"]:
        by_label[n["label"]].append(n["props"])
    for label, rows in by_label.items():
        graph.query(f"CREATE INDEX FOR (n:{label}) ON (n.id)")
        graph.query(f"UNWIND $rows AS row CREATE (n:{label}) SET n = row", {"rows": rows})
    groups = defaultdict(list)
    for e in gold["edges"]:
        groups[(label_of[e["src"]], e["type"], label_of[e["dst"]])].append({"s": e["src"], "d": e["dst"], "p": e["props"]})
    for (sl, rel, dl), rows in groups.items():
        graph.query(f"UNWIND $rows AS r MATCH (a:{sl} {{id: r.s}}), (b:{dl} {{id: r.d}}) CREATE (a)-[e:{rel}]->(b) SET e = r.p",
                    {"rows": rows})
    # Co-authorship has no direction, but FalkorDB algorithms (betweenness) follow edge direction.
    # Store every COAUTHOR edge both ways so algorithms treat it as undirected.
    added = graph.query("""MATCH (a:Author)-[c:COAUTHOR]->(b:Author)
                           WHERE NOT (b)-[:COAUTHOR]->(a)
                           CREATE (b)-[:COAUTHOR {papers: c.papers, count: c.count}]->(a)""").relationships_created
    added = int(added)
    return {"nodes": len(gold["nodes"]), "edges": len(gold["edges"]) + added}


if __name__ == "__main__":
    import argparse
    import sys

    from app.config import ROOT
    from app.graph.client import graph_for

    parser = argparse.ArgumentParser(description="Load the gold graph into ws_<workspace> (oracle mode).")
    parser.add_argument("--workspace", default="gold", help="workspace name; the graph is ws_<workspace>")
    args = parser.parse_args()

    try:
        graph = graph_for(args.workspace)
    except ValueError as exc:
        sys.exit(str(exc))
    counts = load_gold(graph, ROOT / "ground_truth" / "gold_graph.json")
    print(json.dumps({"graph": graph.name, **counts}))
