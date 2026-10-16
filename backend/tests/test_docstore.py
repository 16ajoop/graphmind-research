"""ChromaDB passage store. The fake embedder keeps these tests offline; the last test uses real Ollama and
skips when Ollama or nomic-embed-text is not available. Run: pytest tests/test_docstore.py -v"""
import hashlib
import math
import re

import httpx
import pytest

from app.docs.docstore import OLLAMA_URL, DocStore, chunk, ollama_embed

SECTIONS = [
    {"heading": "1 Introduction", "text": "GraphWalker-QA walks an entity graph. " * 30},
    {"heading": "3 Method", "text": "We link entities with the gold annotations of the dataset. " * 20},
]


def fake_embed(texts, kind):
    """Bag of words hashed into 64 dimensions: texts that share words get similar vectors."""
    out = []
    for t in texts:
        v = [0.0] * 64
        for w in re.findall(r"[a-z]+", t.lower()):
            v[int(hashlib.md5(w.encode()).hexdigest(), 16) % 64] += 1.0
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        out.append([x / n for x in v])
    return out


def test_chunk_keeps_all_text_and_size():
    text = " ".join(f"Sentence number {i} talks about multi-hop retrieval." for i in range(60))
    pieces = chunk(text, max_chars=700)
    assert len(pieces) > 1
    assert all(len(p) <= 700 + 80 for p in pieces)               # one sentence may run over the limit
    assert " ".join(pieces).count("Sentence number") == 60       # nothing lost, nothing doubled


def test_reupload_replaces_chunks(tmp_path):
    store = DocStore(str(tmp_path), "t", embed=fake_embed)
    n1 = store.add_paper("P03", "GraphWalker-QA", "We answer multi-hop questions.", SECTIONS)
    n2 = store.add_paper("P03", "GraphWalker-QA", "We answer multi-hop questions.", SECTIONS)
    assert n1 == n2 == store.col.count()                         # same chunks, not twice as many


def test_evidence_stays_inside_the_papers_the_graph_chose(tmp_path):
    store = DocStore(str(tmp_path), "t", embed=fake_embed)
    store.add_paper("P03", "GraphWalker-QA", "We answer multi-hop questions.", SECTIONS)
    store.add_paper("P08", "Revisiting", "We reproduce GraphWalker-QA and find it used gold entity links.", SECTIONS)
    store.add_paper("P12", "HopLens", "Path scoring for multi-hop retrieval.", SECTIONS)
    only = store.evidence("gold entity annotations", ["P08"], k=5)
    assert only and {e["paper_id"] for e in only} == {"P08"}
    two = store.evidence("gold entity annotations", ["P03", "P08"], k=10)
    assert {e["paper_id"] for e in two} <= {"P03", "P08"}
    assert store.section_vector("P03", "Method") is not None
    assert store.section_vector("P03", "Results") is None


def test_real_ollama_embeddings():
    try:
        vec = ollama_embed(["GraphWalker-QA took its entity links from the dataset annotations."], "query")[0]
    except (httpx.HTTPError, KeyError) as e:
        pytest.skip(f"Ollama / nomic-embed-text not available at {OLLAMA_URL}: {e}")
    assert len(vec) == 768                                       # nomic-embed-text vector size
