"""Analysis tools: every relationship the agent reports comes from one of these parameterised Cypher queries."""
import json
from dataclasses import dataclass, field

Q = {
    # ---------- two papers: every way they are connected
    "pair_citations": """
        MATCH (a:Paper {id: $a})-[c:CITES]-(b:Paper {id: $b})
        RETURN startNode(c).id AS citing, endNode(c).id AS cited, c.intent AS intent, c.contexts AS contexts""",
    "pair_shared_authors": """
        MATCH (:Paper {id: $a})<-[:WROTE]-(x:Author)-[:WROTE]->(:Paper {id: $b})
        RETURN collect(x.name) AS authors""",
    "pair_shared_datasets": """
        MATCH (:Paper {id: $a})-[:EVALUATES_ON|INTRODUCES]->(d:Dataset)<-[:EVALUATES_ON|INTRODUCES]-(:Paper {id: $b})
        RETURN collect(DISTINCT d.name) AS datasets""",
    "pair_shared_methods": """
        MATCH (:Paper {id: $a})-[:PROPOSES|USES]->(m:Method)<-[:PROPOSES|USES]-(:Paper {id: $b})
        RETURN collect(DISTINCT m.name) AS methods""",
    "pair_lineage": """
        MATCH (:Paper {id: $a})-[:PROPOSES]->(ma:Method), (:Paper {id: $b})-[:PROPOSES]->(mb:Method)
        MATCH path = (ma)-[:EXTENDS*1..5]->(mb)
        RETURN [n IN nodes(path) | n.name] AS chain""",
    "pair_claims": """
        MATCH (:Paper {id: $a})-[:MAKES]->(c1:Claim)-[r:SUPPORTS|CONTRADICTS|QUALIFIES]-(c2:Claim)<-[:MAKES]-(:Paper {id: $b})
        RETURN startNode(r).id AS from_claim, type(r) AS relation, endNode(r).id AS to_claim,
               r.basis AS basis, c1.text AS claim_a, c2.text AS claim_b""",
    "pair_result_links": """
        MATCH (:Paper {id: $a})-[:REPORTS]->(x:Result)-[r:REPRODUCES|CORRECTS]->(y:Result)<-[:REPORTS]-(:Paper {id: $b})
        MATCH (x)-[:OF_METHOD]->(m:Method)
        RETURN type(r) AS relation, m.name AS method, x.split AS split, x.value AS new_value, y.value AS original_value, x.setting AS setting""",
    "pair_quotes": """
        MATCH (:Paper {id: $a})-[:REPORTS]->(r:Result)-[:QUOTED_FROM]->(:Paper {id: $b}), (r)-[:OF_METHOD]->(m:Method), (r)-[:ON_DATASET]->(d:Dataset)
        RETURN m.name AS method, d.name AS dataset, r.split AS split, r.value AS value""",

    # ---------- whole library
    "library_papers": """
        MATCH (p:Paper {in_library: true})
        OPTIONAL MATCH (a:Author)-[:WROTE]->(p)
        RETURN p.id AS id, p.title AS title, p.year AS year, p.published AS published, collect(a.name) AS authors
        ORDER BY published""",
    "library_edges": """
        MATCH (a:Paper {in_library: true})-[c:CITES]->(b:Paper {in_library: true})
        RETURN a.id AS source, b.id AS target, c.intent AS intent""",

    # ---------- methods
    "lineage_up": """
        MATCH path = (m:Method {id: $method})-[:EXTENDS*1..6]->(root:Method)
        WHERE NOT (root)-[:EXTENDS]->()
        RETURN [n IN nodes(path) | n.name] AS chain""",
    "lineage_down": """
        MATCH path = (leaf:Method)-[:EXTENDS*1..6]->(m:Method {id: $method})
        WHERE NOT ()-[:EXTENDS]->(leaf)
        RETURN [n IN nodes(path) | n.name] AS chain""",
    "method_origin": """
        MATCH (m:Method) OPTIONAL MATCH (p:Paper)-[:PROPOSES]->(m)
        RETURN m.id AS id, m.name AS name, m.aliases AS aliases, p.id AS paper, p.year AS year, p.in_library AS in_library""",

    # ---------- results
    # One dataset/split/metric: every non-quoted result, with an erratum's value swapped in through (fix)-[:CORRECTS]->(r).
    "leaderboard": """
        MATCH (d:Dataset {id: $dataset})<-[:ON_DATASET]-(r:Result)-[:MEASURED_BY]->(mt:Metric {id: $metric}),
              (r)-[:OF_METHOD]->(m:Method), (p:Paper)-[:REPORTS]->(r)
        WHERE r.split = $split AND r.origin IN ['proposed', 'baseline_run', 'reproduced']
        OPTIONAL MATCH (fix:Result)-[:CORRECTS]->(r)
        RETURN m.name AS method, coalesce(fix.value, r.value) AS value, r.value AS as_published,
               fix IS NOT NULL AS corrected, r.origin AS origin, r.setting AS setting, p.id AS paper, p.published AS published,
               mt.higher_is_better AS higher_is_better
        ORDER BY CASE WHEN mt.higher_is_better THEN -coalesce(fix.value, r.value) ELSE coalesce(fix.value, r.value) END""",

    # ---------- claims
    "claim_conflicts": """
        MATCH (c1:Claim)-[r:CONTRADICTS|QUALIFIES]->(c2:Claim), (p1:Paper)-[:MAKES]->(c1), (p2:Paper)-[:MAKES]->(c2)
        RETURN type(r) AS relation, c1.id AS claim, c1.text AS text, p1.id AS paper, c2.id AS other_claim,
               c2.text AS other_text, p2.id AS other_paper, r.basis AS basis""",
    "claim_support": """
        MATCH (c1:Claim)-[r:SUPPORTS]->(c2:Claim), (p1:Paper)-[:MAKES]->(c1), (p2:Paper)-[:MAKES]->(c2)
        RETURN c1.id AS claim, p1.id AS paper, c2.id AS supported_claim, p2.id AS supported_paper, r.basis AS basis""",
    # A 'state of the art' claim is checked against every earlier, non-quoted result in its scope.
    "sota_check": """
        MATCH (p:Paper)-[:MAKES]->(c:Claim {type: 'sota'}), (p)-[:PROPOSES]->(m:Method)
        UNWIND c.scope AS s
        WITH p, c, m, split(s, '|') AS parts
        MATCH (p)-[:REPORTS]->(own:Result)-[:OF_METHOD]->(m), (own)-[:ON_DATASET]->(d:Dataset {id: parts[0]}),
              (own)-[:MEASURED_BY]->(mt:Metric {id: parts[2]})
        WHERE own.split = parts[1]
        MATCH (op:Paper)-[:REPORTS]->(other:Result)-[:OF_METHOD]->(om:Method), (other)-[:ON_DATASET]->(d), (other)-[:MEASURED_BY]->(mt)
        WHERE other.split = parts[1] AND om <> m AND op.published < p.published
          AND other.origin IN ['proposed', 'baseline_run', 'reproduced']
        OPTIONAL MATCH (fix:Result)-[:CORRECTS]->(other)
        WITH c, p, d, parts, own, om, op, coalesce(fix.value, other.value) AS value, mt
        WHERE (mt.higher_is_better AND value > own.value) OR (NOT mt.higher_is_better AND value < own.value)
        RETURN c.id AS claim, p.id AS paper, d.name AS dataset, parts[1] AS split, own.value AS claimed_value,
               om.name AS better_method, value AS better_value, op.id AS better_paper
        ORDER BY better_value DESC""",

    # Pairs worth an LLM judgement: claims from different papers about the same method (newer -> older).
    "claim_pair_candidates": """
        MATCH (p1:Paper)-[:MAKES]->(c1:Claim)-[:ABOUT]->(m:Method)<-[:ABOUT]-(c2:Claim)<-[:MAKES]-(p2:Paper)
        WHERE p1.published > p2.published AND NOT (c1)-[:SUPPORTS|CONTRADICTS|QUALIFIES]->(c2)
        WITH c1, c2, p1, p2, collect(DISTINCT m.name) AS shared_methods
        OPTIONAL MATCH (c1)-[:ABOUT]->(d:Dataset)<-[:ABOUT]-(c2)
        RETURN c1.id AS newer, c1.text AS newer_text, p1.title AS newer_paper,
               c2.id AS older, c2.text AS older_text, p2.title AS older_paper,
               shared_methods, collect(DISTINCT d.name) AS shared_datasets""",
    # Methods with no lineage and no citation between their papers: compare their descriptions by embedding.
    "unlinked_method_pairs": """
        MATCH (p1:Paper {in_library: true})-[:PROPOSES]->(m1:Method), (p2:Paper {in_library: true})-[:PROPOSES]->(m2:Method)
        WHERE m1.id < m2.id AND NOT (m1)-[:EXTENDS*1..5]-(m2) AND NOT (p1)-[:CITES]-(p2)
        RETURN m1.id AS method_a, m1.name AS name_a, p1.id AS paper_a, m2.id AS method_b, m2.name AS name_b, p2.id AS paper_b""",

    # ---------- citation hygiene
    # Missing citations = earlier library papers this paper does not cite, scored by three signals.
    # Each signal is its own query: on FalkorDB 6.0.1, chained OPTIONAL MATCH ... collect() stages lose
    # rows, and a WHERE with a pattern predicate (NOT (p)-[:CITES]->(q)) must be followed by WITH
    # before the next MATCH, or later variables come back "not defined".
    "missing_cit_candidates": """
        MATCH (p:Paper {id: $paper}), (q:Paper {in_library: true})
        WHERE q <> p AND q.published < p.published AND NOT (p)-[:CITES]->(q)
        RETURN q.id AS paper, q.title AS title""",
    "missing_cit_shared_datasets": """
        MATCH (p:Paper {id: $paper}), (q:Paper {in_library: true})
        WHERE q <> p AND q.published < p.published AND NOT (p)-[:CITES]->(q)
        WITH p, q
        MATCH (p)-[:EVALUATES_ON]->(d:Dataset)<-[:EVALUATES_ON]-(q)
        RETURN q.id AS paper, collect(DISTINCT d.name) AS items""",
    "missing_cit_similar_methods": """
        MATCH (p:Paper {id: $paper}), (q:Paper {in_library: true})
        WHERE q <> p AND q.published < p.published AND NOT (p)-[:CITES]->(q)
        WITH p, q
        MATCH (p)-[:PROPOSES]->(:Method)-[:SIMILAR_TO]-(sm:Method)<-[:PROPOSES]-(q)
        RETURN q.id AS paper, collect(DISTINCT sm.name) AS items""",
    "missing_cit_stronger_results": """
        MATCH (p:Paper {id: $paper}), (q:Paper {in_library: true})
        WHERE q <> p AND q.published < p.published AND NOT (p)-[:CITES]->(q)
        WITH p, q
        MATCH (p)-[:PROPOSES]->(pm:Method)<-[:OF_METHOD]-(pr:Result)<-[:REPORTS]-(p)
        MATCH (q)-[:PROPOSES]->(qm:Method)<-[:OF_METHOD]-(qr:Result)<-[:REPORTS]-(q)
        WHERE qr.split = pr.split AND qr.value > pr.value
        MATCH (pr)-[:ON_DATASET]->(d:Dataset)<-[:ON_DATASET]-(qr)
        MATCH (pr)-[:MEASURED_BY]->(:Metric {higher_is_better: true})<-[:MEASURED_BY]-(qr)
        RETURN q.id AS paper, collect(DISTINCT qm.name + ' > ' + pm.name + ' on ' + d.name + ' ' + qr.split) AS items""",
    # Stale citation: a paper cites X, an erratum corrected X before the paper came out, and the paper never cites the erratum.
    "stale_citations": """
        MATCH (p:Paper {in_library: true})-[c:CITES]->(orig:Paper)<-[:CORRECTS]-(err:Paper)
        WHERE p <> err AND p.published > err.published AND NOT (p)-[:CITES]->(err)
        RETURN p.id AS paper, orig.id AS cites, err.id AS correction, c.contexts AS contexts""",
    "external_hubs": """
        MATCH (s:Paper {in_library: false})<-[:CITES]-(p:Paper {in_library: true})
        WITH s, collect(p.id) AS cited_by WHERE size(cited_by) >= $min
        RETURN s.id AS id, s.title AS title, s.year AS year, cited_by ORDER BY size(cited_by) DESC, title""",

    # ---------- research gaps
    "gap_method_dataset": """
        MATCH (:Paper {in_library: true})-[:PROPOSES]->(m:Method), (d:Dataset)
        OPTIONAL MATCH (r:Result)-[:OF_METHOD]->(m) WHERE (r)-[:ON_DATASET]->(d) AND r.origin <> 'quoted'
        WITH m, d, count(r) AS n
        RETURN m.name AS method, collect(CASE WHEN n = 0 THEN d.name END) AS never_evaluated_on,
               collect(CASE WHEN n > 0 THEN d.name END) AS evaluated_on ORDER BY method""",
    "gap_metric_coverage": """
        MATCH (d:Dataset), (mt:Metric)
        OPTIONAL MATCH (r:Result)-[:ON_DATASET]->(d) WHERE (r)-[:MEASURED_BY]->(mt)
        WITH d, mt, count(r) AS n
        RETURN mt.name AS metric, collect(CASE WHEN n = 0 THEN d.name END) AS never_reported_on""",
    "gap_dataset_depth": """
        MATCH (d:Dataset) RETURN d.name AS dataset, d.language AS language, d.splits AS splits ORDER BY language""",
    "gap_unreproduced": """
        MATCH (p:Paper {in_library: true})-[:PROPOSES]->(m:Method)
        WHERE NOT (m)<-[:OF_METHOD]-(:Result {origin: 'reproduced'})
        RETURN m.name AS method, p.id AS paper""",
    "gap_task_without_method": """
        MATCH (c:Claim)-[:ABOUT]->(m:Method)-[:FOR_TASK]->(t:Task)
        WHERE NOT (t)<-[:FOR_TASK]-(:Method)<-[:PROPOSES]-(:Paper {in_library: true})
        RETURN t.name AS task, collect(DISTINCT m.name) AS external_methods, collect(DISTINCT c.id) AS claims""",

    # ---------- people and influence (FalkorDB algorithms)
    # PageRank over CITES: a paper ranks high when papers that are themselves well cited cite it.
    "influential_papers": """
        CALL algo.pageRank('Paper', 'CITES') YIELD node, score
        RETURN node.id AS id, node.title AS title, node.in_library AS in_library, score ORDER BY score DESC LIMIT $k""",
    # Betweenness over COAUTHOR (stored both ways). FalkorDB samples betweenness, so the seed is fixed for repeatable rankings.
    "bridge_authors": """
        CALL algo.betweenness({nodeLabels: ['Author'], relationshipTypes: ['COAUTHOR'], samplingSize: 1000, samplingSeed: 7})
        YIELD node, score
        RETURN node.name AS author, score ORDER BY score DESC LIMIT $k""",
    # Weakly connected components over COAUTHOR: groups of authors with no co-author path between them.
    "author_groups": """
        CALL algo.WCC({nodeLabels: ['Author'], relationshipTypes: ['COAUTHOR']}) YIELD node, componentId
        RETURN componentId, collect(node.name) AS authors ORDER BY size(authors) DESC""",
    "affiliation_history": """
        MATCH (a:Author {id: $author})-[r:AFFILIATED_WITH]->(i:Institution)
        RETURN i.name AS institution, r.first_year AS first_year, r.last_year AS last_year ORDER BY first_year""",
}


@dataclass
class Analysis:
    graph: object
    log: list = field(default_factory=list)

    def run(self, name, **params):
        res = self.graph.ro_query(Q[name], params)   # read-only: never creates or changes a graph
        cols = [c[1] if isinstance(c, (list, tuple)) else c for c in res.header]
        rows = [dict(zip(cols, r)) for r in res.result_set]
        self.log.append({"query": name, "params": params, "rows": len(rows)})
        return rows

    def relationship(self, a, b) -> dict:
        """Everything that connects two papers, in both directions where direction matters."""
        out = {"citations": self.run("pair_citations", a=a, b=b)}
        for name in ("pair_shared_authors", "pair_shared_datasets", "pair_shared_methods"):
            out[name.removeprefix("pair_")] = self.run(name, a=a, b=b)[0]
        out["lineage"] = self.run("pair_lineage", a=a, b=b) + self.run("pair_lineage", a=b, b=a)
        out["claims"] = self.run("pair_claims", a=a, b=b)
        out["result_links"] = self.run("pair_result_links", a=a, b=b) + self.run("pair_result_links", a=b, b=a)
        out["quotes"] = self.run("pair_quotes", a=a, b=b) + self.run("pair_quotes", a=b, b=a)
        return out

    def missing_citations(self, paper, min_score=5) -> list:
        """Score = 2 x shared datasets + 3 x similar methods + 2 x results that beat this paper's own."""
        out = {r["paper"]: {"paper": r["paper"], "title": r["title"], "shared_datasets": [],
                            "similar_methods": [], "stronger_results": []}
               for r in self.run("missing_cit_candidates", paper=paper)}
        for key in ("shared_datasets", "similar_methods", "stronger_results"):
            for r in self.run(f"missing_cit_{key}", paper=paper):
                out[r["paper"]][key] = r["items"]
        for o in out.values():
            o["score"] = 2 * len(o["shared_datasets"]) + 3 * len(o["similar_methods"]) + 2 * len(o["stronger_results"])
        return sorted((o for o in out.values() if o["score"] >= min_score), key=lambda o: -o["score"])

    def leaderboard(self, dataset, split, metric) -> list:
        """One row per method: the authoritative number plus every other measurement of it."""
        rows = self.run("leaderboard", dataset=dataset, split=split, metric=metric)
        best = {}
        # The method's own paper is authoritative; otherwise the earliest independent run.
        for r in sorted(rows, key=lambda r: (r["origin"] != "proposed", r["origin"] != "baseline_run", r["published"])):
            entry = best.setdefault(r["method"], {"method": r["method"], "value": None, "paper": None, "other_runs": []})
            primary = r["origin"] == "proposed" or (entry["value"] is None and r["origin"] == "baseline_run")
            if primary and entry["paper"] is None:
                entry.update(value=r["value"], paper=r["paper"], corrected=r["corrected"], as_published=r["as_published"])
            else:
                entry["other_runs"].append({k: r[k] for k in ("value", "origin", "setting", "paper")})
        for e in best.values():
            if e["value"] is None and e["other_runs"]:
                first = e["other_runs"].pop(0)
                e.update(value=first["value"], paper=first["paper"])
            vals = [e["value"]] + [o["value"] for o in e["other_runs"]]
            e["spread"] = round(max(vals) - min(vals), 1)
        hib = rows[0]["higher_is_better"] if rows else True
        return sorted(best.values(), key=lambda e: -e["value"] if hib else e["value"])


def _parse_value(raw: str):
    """'5' -> 5, 'a,b' -> ['a', 'b'], '1,2' -> [1, 2], anything else stays a string."""
    if "," in raw:
        return [_parse_value(part) for part in raw.split(",") if part != ""]
    try:
        return int(raw)
    except ValueError:
        return raw


if __name__ == "__main__":
    import sys

    from app.graph.client import UnknownWorkspace, graph_for

    usage = "usage: python -m app.graph.analysis <workspace> <query_name> key=value ..."
    if len(sys.argv) < 3:
        sys.exit(f"{usage}\nqueries: {', '.join(Q)}")
    workspace, name, *pairs = sys.argv[1:]
    if name not in Q and name != "missing_citations":
        sys.exit(f"unknown query {name!r}\nqueries: {', '.join(Q)}")
    params = {}
    for pair in pairs:
        key, sep, raw = pair.partition("=")
        if not sep or not key:
            sys.exit(f"bad argument {pair!r}: expected key=value\n{usage}")
        params[key] = _parse_value(raw)
    try:
        graph = graph_for(workspace, must_exist=True)
    except ValueError as exc:
        sys.exit(str(exc))
    except UnknownWorkspace as exc:
        print(exc, file=sys.stderr)
        sys.exit(2)
    analysis = Analysis(graph)
    if name == "missing_citations":
        rows = analysis.missing_citations(**params)
    else:
        rows = analysis.run(name, **params)
    print(json.dumps(rows, indent=2, ensure_ascii=False, default=str))
