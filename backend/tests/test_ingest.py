"""PDF -> graph without any LLM: exact on the synthetic corpus, whatever the upload order. Run: pytest tests/test_ingest.py -v"""
import json
import os
import random
from pathlib import Path

import pytest
from falkordb import FalkorDB

from app.eval_extraction import score
from app.graph.ingest import ingest_pdf
from app.graph.pdf_parser import parse_pdf

ROOT = Path(__file__).resolve().parents[2]
PDFS = sorted((ROOT / "corpus" / "pdf").glob("*.pdf"))
ONTOLOGY = json.loads((ROOT / "ontology.json").read_text(encoding="utf-8"))


def test_parser_reads_every_pdf():
    for f in PDFS:
        p = parse_pdf(f)
        assert p.title and p.authors and p.year and p.abstract and p.sections and p.references and p.tables, f.name
        assert all(r["title"] and r["year"] for r in p.references), f.name


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_upload_order_does_not_matter(seed):
    db = FalkorDB(host=os.getenv("FALKORDB_HOST", "localhost"), port=int(os.getenv("FALKORDB_PORT", "6379")))
    g = db.select_graph(f"ingest_test_{seed}")
    try:
        g.delete()
    except Exception:
        pass
    g = db.select_graph(f"ingest_test_{seed}")
    files = PDFS[:]
    random.Random(seed).shuffle(files)
    for f in files:
        ingest_pdf(g, f, ONTOLOGY)
    rep = score(g)
    counts = dict(g.query("MATCH (p:Paper) RETURN p.in_library, count(p)").result_set)
    coauthor = g.query("MATCH (:Author)-[c:COAUTHOR]->(:Author) RETURN count(c)").result_set[0][0]
    one_way = g.query("""MATCH (a:Author)-[:COAUTHOR]->(b:Author)
                         WHERE NOT (b)-[:COAUTHOR]->(a) RETURN count(*)""").result_set[0][0]
    stored = [f for (f,) in g.query("MATCH (p:Paper {in_library: true}) RETURN p.file").result_set]
    g.delete()
    assert counts == {True: 12, False: 4}
    assert coauthor == 46 and one_way == 0           # 23 author pairs, each stored both ways (as in the gold loader)
    assert len(stored) == 12 and all("/" not in f and "\\" not in f for f in stored)   # file name only, on Windows too
    assert rep["CITES"] == {"precision": 1.0, "recall": 1.0, "got": 49, "want": 49}
    assert rep["Result"]["precision"] == rep["Result"]["recall"] == 1.0
    assert rep["CORRECTS"]["recall"] == 1.0 and rep["unmapped"] == []
