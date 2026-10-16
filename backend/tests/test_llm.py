"""LLM plumbing and validation, with Ollama replaced by a fake HTTP server (no model needed)."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from app.agent import llm
from app.graph.ingest import keyword_intent

REPLIES = {
    "intent": {"intent": "reproduces"},
    "claims": {"claims": [
        {"text": "GraphWalker-QA's 3-hop advantage depends on gold entity links; with predicted links it falls below HopRank.",
         "type": "comparative", "about": ["GraphWalker-QA", "HopRank", "Made-Up"]},
        {"text": "This sentence is not in the paper.", "type": "causal", "about": ["HopRank"]}]},
    "relation": {"relation": "CONTRADICTS", "basis": "predicted vs gold entity links"},
    "answer": {"answer": "GraphFuse leads with 46.3 [1]; HopLens follows [2]."},
}


class FakeOllama(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        assert self.path == "/api/chat" and body["stream"] is False and body["options"]["temperature"] == 0
        key = next(k for k in REPLIES if k in body["format"]["properties"])
        out = json.dumps({"message": {"role": "assistant", "content": json.dumps(REPLIES[key])}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)


@pytest.fixture
def fake(monkeypatch):
    srv = HTTPServer(("127.0.0.1", 0), FakeOllama)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setattr(llm, "OLLAMA_URL", f"http://127.0.0.1:{srv.server_port}")
    yield
    srv.shutdown()


def test_intent(fake):
    assert llm.classify_intent("Revisiting", "GraphWalker-QA", ["We reproduce GraphWalker-QA [1]."], keyword_intent) == ("reproduces", "llm")


def test_claims_are_validated(fake):
    abstract = "We reproduce GraphWalker-QA. GraphWalker-QA's 3-hop advantage depends on gold entity links; with predicted links it falls below HopRank."
    claims = llm.extract_claims("Revisiting", abstract, "", ["GraphWalker-QA", "HopRank", "KaveriHop"])
    assert len(claims) == 1 and claims[0]["about"] == ["GraphWalker-QA", "HopRank"]   # invented sentence and unknown entity dropped


def test_relation_and_answer_leak_check(fake):
    assert llm.judge_claims({"text": "b", "paper_title": "B", "context": ""}, {"text": "a", "paper_title": "A", "context": ""})["relation"] == "CONTRADICTS"
    assert llm.write_answer("Who leads?", ["GraphFuse 46.3", "HopLens 44.8"], {"GraphFuse", "HopLens"}, {"GraphFuse", "HopLens", "HopRank"})
    assert llm.write_answer("Who leads?", ["GraphFuse 46.3"], {"GraphFuse"}, {"GraphFuse", "HopLens"}) == ""   # names HopLens -> rejected


def test_fallback_when_ollama_is_down(monkeypatch):
    monkeypatch.setattr(llm, "OLLAMA_URL", "http://127.0.0.1:1")
    assert llm.classify_intent("A", "B", ["We compare against HopRank [3]."], keyword_intent) == ("compares_against", "keywords")
    assert llm.extract_claims("A", "x", "y", ["HopRank"]) == []


def test_claim_text_is_snapped_to_the_papers_sentence():
    source = ("We re-run GraphWalker-QA with predicted entity links. "
              "GraphWalker-QA's 3-hop advantage depends on gold entity links; with predicted links it falls below HopRank.")
    copied = "GraphWalker-QA 3-hop advantage depends on gold entity links, with predicted links it falls below HopRank"
    assert llm.snap_to_source(copied, source) == source.split(". ", 1)[1]          # small edits: snapped to the real sentence
    assert llm.snap_to_source("Graph retrieval is always better on every dataset.", source) is None   # not in the paper
