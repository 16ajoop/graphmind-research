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
        {"sentence": 1, "type": "comparative", "about": ["GraphWalker-QA", "HopRank", "Made-Up"]},
        {"sentence": 9, "type": "causal", "about": ["HopRank"]}]},
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
    abstract = ("We reproduce GraphWalker-QA on KaveriHop. "
                "GraphWalker-QA's 3-hop advantage depends on gold entity links; with predicted links it falls below HopRank.")
    claims = llm.extract_claims("Revisiting", abstract, "", ["GraphWalker-QA", "HopRank", "KaveriHop"])
    assert len(claims) == 1 and claims[0]["about"] == ["GraphWalker-QA", "HopRank"]   # bad number and unknown entity dropped
    assert claims[0]["text"] == abstract.split(". ", 1)[1]                             # the paper's own sentence


def test_relation_and_answer_leak_check(fake):
    assert llm.judge_claims({"text": "b", "paper_title": "B", "context": ""}, {"text": "a", "paper_title": "A", "context": ""})["relation"] == "CONTRADICTS"
    assert llm.write_answer("Who leads?", ["GraphFuse 46.3", "HopLens 44.8"], {"GraphFuse", "HopLens"}, {"GraphFuse", "HopLens", "HopRank"})
    assert llm.write_answer("Who leads?", ["GraphFuse 46.3"], {"GraphFuse"}, {"GraphFuse", "HopLens"}) == ""   # names HopLens -> rejected


def test_fallback_when_ollama_is_down(monkeypatch):
    monkeypatch.setattr(llm, "OLLAMA_URL", "http://127.0.0.1:1")
    assert llm.classify_intent("A", "B", ["We compare against HopRank [3]."], keyword_intent) == ("compares_against", "keywords")
    assert llm.extract_claims("A", "x", "y", ["HopRank"]) == []


def test_only_findings_are_offered_to_the_model():
    text = ("We propose HopLens, a path scorer for long chains. In this paper we study long reasoning chains. "
            "HopLens achieves state-of-the-art exact match on 3-hop questions in both KaveriHop and TriHop-Bench.")
    assert llm.candidate_sentences(text, "") == [text.split(". ")[2]]     # 'we propose' / 'in this paper' removed
    assert llm.candidate_sentences("GraphWalker-QA [3] gains most on 3-hop questions, as earlier work showed.", "") == []


def test_intent_must_be_one_the_graph_allows(fake):
    # the fake model answers 'reproduces', which the graph did not allow here: fall back inside the allowed list
    assert llm.classify_intent("A", "B", ["We compare against HopRank [3]."], keyword_intent,
                               ["background", "uses_method"]) == ("background", "keywords")
