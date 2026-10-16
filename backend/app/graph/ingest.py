"""Deterministic ingestion: parsed PDF -> FalkorDB, plus the reconcile step that makes upload order irrelevant.

What this file decides WITHOUT an LLM:
  papers (and stubs for cited-but-missing papers), authors, affiliations, co-authorship, venues,
  citations with their context sentences, table results, proposed methods / introduced datasets
  (from the title prefix), method/dataset identity (aliases, citation anchors), reproductions,
  corrections, and method lineage once citation intents are known.
What it leaves to the LLM (app/agent/enrich.py, Phase 4):
  citation intent, claims, claim relations, method descriptions for similarity.
"""
import json
import re
import unicodedata
from pathlib import Path

from rapidfuzz import fuzz

from app.graph.pdf_parser import ParsedPaper, parse_pdf


def norm(text: str) -> str:
    """Lowercase ASCII letters and digits only: 'Kaveri-Hop' == 'KaveriHop' == 'kaverihop'."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", text.lower())


def words(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


def slug(text: str, n: int = 6) -> str:
    return "-".join(words(text).split()[:n])


def q(graph, cypher, **params):
    return graph.query(cypher, params).result_set


# ------------------------------------------------------------------ paper identity
def first_surname_from_name(name: str) -> str:
    return norm(name.split()[-1]) if name else ""


def first_surname_from_ref(authors: str) -> str:
    return norm(authors.split(",")[0]) if authors else ""


def same_paper(title_a, year_a, surname_a, title_b, year_b, surname_b) -> bool:
    """Reference lists abbreviate titles, so matching uses three signals.
    Same year + same first author: a loose title match is enough.
    Same year only: titles must be nearly identical. Different years: never the same paper
    (this keeps 'Erratum: X' from being merged with 'X')."""
    if year_a and year_b and year_a != year_b:
        return False
    a, b = words(title_a), words(title_b)
    if surname_a and surname_a == surname_b and fuzz.token_set_ratio(a, b) >= 80:
        return True
    return fuzz.token_sort_ratio(a, b) >= 92


def find_paper(graph, title, year, surname):
    for pid, t, y, s in q(graph, "MATCH (p:Paper) RETURN p.id, p.title, p.year, p.first_author"):
        if same_paper(title, year, surname, t, y, s):
            return pid
    return None


def upsert_library_paper(graph, p: ParsedPaper) -> str:
    surname = first_surname_from_name(p.authors[0]["name"]) if p.authors else ""
    pid = find_paper(graph, p.title, p.year, surname) or f"paper-{slug(p.title)}"
    # An uploaded PDF adopts an existing stub: citations made earlier already point at this node.
    q(graph, """MERGE (x:Paper {id: $id})
                SET x += $props, x.added_at = coalesce(x.added_at, timestamp())""", id=pid, props={
        "title": p.title, "year": p.year, "published": p.published, "first_author": surname,
        "abstract": p.abstract, "keywords": p.keywords, "file": Path(p.file).name, "in_library": True})
    if p.venue:
        q(graph, """MATCH (x:Paper {id: $pid})
                    MERGE (v:Venue {id: $vid}) SET v.short = $venue, v.name = coalesce(v.name, $venue)
                    MERGE (x)-[:PUBLISHED_IN]->(v)""", pid=pid, vid=f"venue-{slug(p.venue)}", venue=p.venue)
    return pid


def upsert_authors(graph, pid: str, p: ParsedPaper):
    ids = []
    for pos, a in enumerate(p.authors, 1):
        aid = f"author-{slug(a['name'])}"
        ids.append(aid)
        q(graph, """MATCH (x:Paper {id: $pid})
                    MERGE (au:Author {id: $aid}) SET au.name = $name
                    MERGE (au)-[w:WROTE]->(x) SET w.position = $pos, w.affiliation = $aff""",
          pid=pid, aid=aid, name=a["name"], pos=pos, aff=a["affiliation"])
        if a["affiliation"]:
            q(graph, """MATCH (au:Author {id: $aid})
                        MERGE (i:Institution {id: $iid}) SET i.name = $inst
                        MERGE (au)-[r:AFFILIATED_WITH]->(i)
                        SET r.first_year = CASE WHEN r.first_year IS NULL OR $y < r.first_year THEN $y ELSE r.first_year END,
                            r.last_year  = CASE WHEN r.last_year  IS NULL OR $y > r.last_year  THEN $y ELSE r.last_year  END""",
              aid=aid, iid=f"inst-{slug(a['affiliation'])}", inst=a["affiliation"], y=p.year)
    # Co-authorship is stored in BOTH directions: FalkorDB algorithms (betweenness) follow edge direction.
    for a in ids:
        for b in ids:
            if a == b:
                continue
            q(graph, """MATCH (x:Author {id: $a}), (y:Author {id: $b})
                        MERGE (x)-[c:COAUTHOR]->(y)
                        SET c.papers = CASE WHEN c.papers IS NULL THEN [$pid]
                                            WHEN $pid IN c.papers THEN c.papers ELSE c.papers + [$pid] END,
                            c.count = size(c.papers)""", a=a, b=b, pid=pid)


def link_references(graph, pid: str, p: ParsedPaper) -> dict:
    """Returns {ref_no: paper_id}. Unknown references become stub papers (in_library=false)."""
    contexts = {}
    for c in p.citations:
        contexts.setdefault(c["ref_n"], []).append(c["sentence"])
    ref_ids = {}
    for r in p.references:
        title = r["title"] or r["raw"]
        surname = first_surname_from_ref(r["authors"])
        rid = find_paper(graph, title, r["year"], surname)
        if rid is None:
            rid = f"paper-{slug(title)}"
            q(graph, """MERGE (s:Paper {id: $id})
                        ON CREATE SET s.title = $title, s.year = $year, s.first_author = $surname,
                                      s.venue = $venue, s.authors_raw = $authors, s.in_library = false""",
              id=rid, title=title, year=r["year"], surname=surname, venue=r["venue"], authors=r["authors"])
        ref_ids[r["n"]] = rid
        q(graph, """MATCH (a:Paper {id: $src}), (b:Paper {id: $dst})
                    MERGE (a)-[c:CITES]->(b)
                    SET c.ref_no = $n, c.contexts = $ctx, c.intent = coalesce(c.intent, 'unclassified')""",
          src=pid, dst=rid, n=r["n"], ctx=contexts.get(r["n"], []))
    return ref_ids


# ------------------------------------------------------------------ methods, datasets, results
def _anchors(name: str, p: ParsedPaper, ref_ids: dict) -> list:
    """Papers cited right after a mention: 'GW-QA [3]' anchors GW-QA to reference 3."""
    pattern = re.compile(re.escape(name) + r"\s*\[(\d+)\]")
    found = {ref_ids[int(n)] for c in p.citations for n in pattern.findall(c["sentence"]) if int(n) in ref_ids}
    return sorted(found)


def resolve_entity(graph, label: str, display: str, anchors: list, allow_prefix: bool) -> str:
    key = norm(display)
    rows = q(graph, f"MATCH (e:{label}) RETURN e.id, e.keys")
    for eid, keys in rows:
        if key in keys:
            hit = eid
            break
    else:
        hit = None
        if allow_prefix and len(key) >= 5:   # 'TriHop' vs 'TriHop-Bench'
            matches = [eid for eid, keys in rows if any(k.startswith(key) or key.startswith(k) for k in keys if len(k) >= 5)]
            hit = matches[0] if len(matches) == 1 else None
    eid = hit or f"{label.lower()}-{slug(display)}"
    q(graph, f"""MERGE (e:{label} {{id: $id}})
                 ON CREATE SET e.name = $name, e.keys = [], e.aliases = [], e.anchors = []
                 SET e.keys = CASE WHEN $key IN e.keys THEN e.keys ELSE e.keys + [$key] END,
                     e.aliases = CASE WHEN $name IN e.aliases THEN e.aliases ELSE e.aliases + [$name] END,
                     e.anchors = e.anchors + [a IN $anchors WHERE NOT a IN e.anchors]""",
      id=eid, name=display, key=key, anchors=anchors)
    return eid


def parse_header(col: str, ontology: dict):
    """'KaveriHop 3-hop EM' -> ('KaveriHop', '3-hop', 'metric-em'); 'Kaveri-Hop latency (ms/query)' -> (.., 'all', ..)."""
    aliases = sorted(((a, m["id"]) for m in ontology["metrics"] for a in m["aliases"]), key=lambda x: -len(x[0]))
    for alias, metric_id in aliases:
        if col.lower().endswith(" " + alias.lower()):
            rest = col[: -len(alias)].strip()
            m = re.search(ontology["split_pattern"], rest)
            split = m.group(1) if m else "all"
            dataset = rest[: m.start()].strip() if m else rest
            return dataset, split, metric_id
    return None


def parse_source(source: str):
    """Source column -> (origin hint, cited reference number or None)."""
    s = source.lower()
    ref = re.match(r"^\[(\d+)\]", source)
    if "corrected" in s:
        return "corrected", None
    if "reproduced" in s:
        return "reproduced", None
    if ref:
        return "quoted", int(ref.group(1))
    if "re-run" in s or "rerun" in s:
        return "baseline_run", None
    return "ours", None


def tables_to_results(graph, pid: str, p: ParsedPaper, ref_ids: dict, ontology: dict):
    title_prefix = norm(p.title.split(":")[0]) if ":" in p.title else ""
    if p.title.lower().startswith(("erratum", "corrigendum")):
        title_prefix = ""
    for m in ontology["metrics"]:
        q(graph, "MERGE (x:Metric {id: $id}) SET x.name = $name, x.aliases = $aliases, x.unit = $unit, x.higher_is_better = $hib",
          id=m["id"], name=m["name"], aliases=m["aliases"], unit=m["unit"], hib=m["higher_is_better"])
    n = 0
    for table in p.tables:
        cols = [parse_header(c, ontology) for c in table["header"]]
        for row in table["rows"]:
            method_display, source = row[0], row[1]
            mid = resolve_entity(graph, "Method", method_display, _anchors(method_display, p, ref_ids), allow_prefix=False)
            if title_prefix and norm(method_display) == title_prefix:
                q(graph, "MATCH (x:Paper {id: $p}), (m:Method {id: $m}) MERGE (x)-[:PROPOSES]->(m)", p=pid, m=mid)
            origin, ref_n = parse_source(source)
            if origin == "ours":
                proposes = q(graph, "MATCH (:Paper {id: $p})-[:PROPOSES]->(m:Method {id: $m}) RETURN count(m)", p=pid, m=mid)[0][0]
                origin = "proposed" if proposes else "baseline_run"
            for col, cell in zip(cols[2:], row[2:]):
                if col is None or cell.strip() in ("", "–", "-"):
                    continue
                ds_display, split, metric_id = col
                did = resolve_entity(graph, "Dataset", ds_display, _anchors(ds_display, p, ref_ids), allow_prefix=True)
                if title_prefix and norm(ds_display) == title_prefix:
                    q(graph, "MATCH (x:Paper {id: $p}), (d:Dataset {id: $d}) MERGE (x)-[:INTRODUCES]->(d) SET d.name = $name",
                      p=pid, d=did, name=ds_display)
                n += 1
                rid = f"result-{pid}-{n:02d}"
                q(graph, """MATCH (x:Paper {id: $p}), (m:Method {id: $m}), (d:Dataset {id: $d}), (mt:Metric {id: $mt})
                            MERGE (r:Result {id: $rid})
                            SET r.value = $v, r.split = $split, r.origin = $origin, r.source = $source,
                                r.reported_as = $display, r.table = $caption, r.paper = $p
                            MERGE (x)-[:REPORTS]->(r) MERGE (r)-[:OF_METHOD]->(m)
                            MERGE (r)-[:ON_DATASET]->(d) MERGE (r)-[:MEASURED_BY]->(mt)""",
                  p=pid, m=mid, d=did, mt=metric_id, rid=rid, v=float(cell.replace(",", "")), split=split,
                  origin=origin, source=source, display=method_display, caption=table["caption"])
                if origin == "quoted" and ref_n in ref_ids:
                    q(graph, "MATCH (r:Result {id: $r}), (s:Paper {id: $s}) MERGE (r)-[:QUOTED_FROM]->(s)", r=rid, s=ref_ids[ref_n])
                if origin != "quoted":
                    q(graph, "MATCH (x:Paper {id: $p}), (d:Dataset {id: $d}) MERGE (x)-[:EVALUATES_ON]->(d)", p=pid, d=did)
                if origin != "proposed":
                    q(graph, "MATCH (x:Paper {id: $p}), (m:Method {id: $m}) WHERE NOT (x)-[:PROPOSES]->(m) MERGE (x)-[:USES]->(m)", p=pid, m=mid)


# ------------------------------------------------------------------ reconcile (run after every upload)
METHOD_EDGES_IN = ["OF_METHOD", "USES", "PROPOSES", "ABOUT"]
DATASET_EDGES_IN = ["ON_DATASET", "EVALUATES_ON", "INTRODUCES", "ABOUT"]


def merge_into(graph, label: str, src: str, dst: str, in_edges: list):
    for rel in in_edges:
        q(graph, f"""MATCH (x)-[e:{rel}]->(:{label} {{id: $src}}) MATCH (d:{label} {{id: $dst}})
                     MERGE (x)-[:{rel}]->(d) DELETE e""", src=src, dst=dst)
    q(graph, f"""MATCH (s:{label} {{id: $src}}), (d:{label} {{id: $dst}})
                 SET d.keys = d.keys + [k IN s.keys WHERE NOT k IN d.keys],
                     d.aliases = d.aliases + [a IN s.aliases WHERE NOT a IN d.aliases],
                     d.anchors = d.anchors + [a IN s.anchors WHERE NOT a IN d.anchors]
                 DELETE s""", src=src, dst=dst)


def reconcile(graph):
    """Idempotent clean-up that makes the final graph independent of upload order."""
    changed = True
    while changed:
        changed = False
        # 1. A mention anchored to paper X is the same entity X proposes/introduces.
        for label, rel, edges_in in (("Method", "PROPOSES", METHOD_EDGES_IN), ("Dataset", "INTRODUCES", DATASET_EDGES_IN)):
            for src, dst in q(graph, f"""MATCH (a:{label}), (p:Paper)-[:{rel}]->(b:{label})
                                         WHERE a <> b AND p.id IN a.anchors RETURN a.id, b.id LIMIT 1"""):
                merge_into(graph, label, src, dst, edges_in)
                changed = True
            # 2. Two nodes that now share a spelling (or a dataset name prefix) are one entity.
            rows = q(graph, f"MATCH (e:{label}) OPTIONAL MATCH (p:Paper)-[:{rel}]->(e) RETURN e.id, e.keys, count(p)")
            for i, (a, ka, pa) in enumerate(rows):
                for b, kb, pb in rows[i + 1:]:
                    same = set(ka) & set(kb) or (label == "Dataset" and any(
                        (x.startswith(y) or y.startswith(x)) and min(len(x), len(y)) >= 5 for x in ka for y in kb))
                    if same:
                        keep, drop = (a, b) if pa >= pb else (b, a)
                        merge_into(graph, label, drop, keep, edges_in)
                        changed = True
                        break
                if changed:
                    break
    # 3. Errata: 'Erratum: <title>' corrects the paper with that title.
    for pid, title in q(graph, "MATCH (p:Paper {in_library: true}) WHERE toLower(p.title) STARTS WITH 'erratum' RETURN p.id, p.title"):
        target = title.split(":", 1)[1].strip()
        for oid, otitle in q(graph, "MATCH (o:Paper) WHERE o.id <> $id RETURN o.id, o.title", id=pid):
            if fuzz.token_sort_ratio(words(target), words(otitle)) >= 92:
                q(graph, "MATCH (e:Paper {id: $e}), (o:Paper {id: $o}) MERGE (e)-[:CORRECTS]->(o)", e=pid, o=oid)
    # 4. Result-level links once both papers are present.
    q(graph, """MATCH (fix:Result {origin: 'corrected'})<-[:REPORTS]-(e:Paper)-[:CORRECTS]->(o:Paper)-[:REPORTS]->(old:Result)
                WHERE old.origin <> 'quoted' AND old.split = fix.split
                  AND (fix)-[:OF_METHOD]->()<-[:OF_METHOD]-(old)
                  AND (fix)-[:ON_DATASET]->()<-[:ON_DATASET]-(old)
                  AND (fix)-[:MEASURED_BY]->()<-[:MEASURED_BY]-(old)
                MERGE (fix)-[:CORRECTS]->(old)""")
    q(graph, """MATCH (r:Result {origin: 'reproduced'})-[:OF_METHOD]->(m:Method)<-[:PROPOSES]-(op:Paper)-[:REPORTS]->(o:Result {origin: 'proposed'})
                WHERE o.split = r.split
                  AND (o)-[:OF_METHOD]->(m)
                  AND (r)-[:ON_DATASET]->()<-[:ON_DATASET]-(o)
                  AND (r)-[:MEASURED_BY]->()<-[:MEASURED_BY]-(o)
                MERGE (r)-[:REPRODUCES]->(o)""")
    # 5. Lineage from citation intent: proposing paper CITES another with intent 'extends'.
    q(graph, """MATCH (p:Paper)-[:CITES {intent: 'extends'}]->(o:Paper), (p)-[:PROPOSES]->(m:Method), (o)-[:PROPOSES]->(n:Method)
                WHERE m <> n MERGE (m)-[:EXTENDS]->(n)""")


def ingest_pdf(graph, path, ontology) -> str:
    p = parse_pdf(path)
    pid = upsert_library_paper(graph, p)
    upsert_authors(graph, pid, p)
    ref_ids = link_references(graph, pid, p)
    tables_to_results(graph, pid, p, ref_ids, ontology)
    reconcile(graph)
    return pid


# ------------------------------------------------------------------ keyword baseline for citation intent
INTENT_RULES = [
    ("reproduces", r"\breproduc"),
    ("extends", r"\bextends?\b|\bbuilds? on\b"),
    ("supports", r"\bsupports?\b|\bconsistent with\b"),
    ("criticizes", r"\bcontradict|\bflaw|\bincorrect"),
    ("uses_method", r"\binitiali[sz]ed from\b|\blinker\b|\breleased code\b|\busing its\b"),
    ("uses_dataset", r"\bevaluate on\b|\bon (the )?\w+ \[\d+\]"),
    ("compares_against", r"\bcompar|\bagainst\b|\bquot|\bpublished numbers?\b|\bbaseline"),
]


def keyword_intent(contexts: list) -> str:
    text = " ".join(contexts).lower()
    for intent, pattern in INTENT_RULES:
        if re.search(pattern, text):
            return intent
    return "background"


def apply_keyword_intents(graph) -> int:
    """Baseline before the LLM: label every still-unclassified citation from its context sentences.
    Then reconcile again, because method lineage (EXTENDS) is derived from 'extends' intents."""
    rows = q(graph, """MATCH (a:Paper)-[c:CITES]->(b:Paper) WHERE c.intent = 'unclassified'
                       RETURN a.id, b.id, c.contexts""")
    for a, b, contexts in rows:
        q(graph, """MATCH (:Paper {id: $a})-[c:CITES]->(:Paper {id: $b})
                    SET c.intent = $intent, c.intent_source = 'keywords'""",
          a=a, b=b, intent=keyword_intent(contexts or []))
    reconcile(graph)
    return len(rows)


# ------------------------------------------------------------------ CLI
def _expand(args: list) -> list:
    """Files, folders or glob patterns. PowerShell passes *.pdf through unexpanded, so expand it here."""
    import glob

    files = []
    for arg in args:
        path = Path(arg)
        if path.is_dir():
            files += sorted(path.glob("*.pdf"))
        else:
            files += sorted(Path(f) for f in glob.glob(arg))
    return files


if __name__ == "__main__":
    import argparse
    import time

    from app.graph.client import graph_for

    ap = argparse.ArgumentParser(description="Ingest PDFs into a workspace graph without any LLM.")
    ap.add_argument("--workspace", required=True, help="workspace name; the graph is ws_<workspace>")
    ap.add_argument("--keyword-intents", action="store_true",
                    help="label citation intents with the keyword baseline (the number the LLM must beat)")
    ap.add_argument("pdfs", nargs="+", help="PDF files, folders or glob patterns")
    args = ap.parse_args()

    files = _expand(args.pdfs)
    if not files:
        raise SystemExit(f"no PDFs matched {args.pdfs}")
    ontology = json.loads((Path(__file__).resolve().parents[3] / "ontology.json").read_text(encoding="utf-8"))
    graph = graph_for(args.workspace)          # ingestion is allowed to create the workspace
    for f in files:
        t0 = time.time()
        pid = ingest_pdf(graph, f, ontology)
        print(f"{f.name:<40} -> {pid}  ({time.time() - t0:.1f}s)")
    if args.keyword_intents:
        print(f"keyword intents: {apply_keyword_intents(graph)} citations labelled")
    papers = dict(q(graph, "MATCH (p:Paper) RETURN p.in_library, count(p)"))
    print(f"papers: {papers.get(True, 0)} in library, {papers.get(False, 0)} stubs | "
          f"nodes: {q(graph, 'MATCH (n) RETURN count(n)')[0][0]} | "
          f"relationships: {q(graph, 'MATCH ()-[r]->() RETURN count(r)')[0][0]}")
