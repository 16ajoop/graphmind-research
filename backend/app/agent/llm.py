"""The only places the LLM is used. Every call: closed JSON schema, temperature 0, validated, with a fallback.

llama3.2 (3B) is reliable at short classification and filling a small form from one paragraph.
It is NOT used for anything the graph or the parser can decide.
"""
import json
import os
import re

import httpx
from rapidfuzz import fuzz

from app.graph.ingest import norm, words

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
LLM_MODEL = os.getenv("LLM_MODEL", "llama3.2:latest")
INTENTS = ["extends", "compares_against", "uses_dataset", "uses_method", "reproduces",
           "supports", "criticizes", "corrects", "background"]
CLAIM_TYPES = ["comparative", "causal", "sota", "efficiency", "observational"]
RELATIONS = ["SUPPORTS", "CONTRADICTS", "QUALIFIES", "UNRELATED"]


def ollama_json(system: str, user: str, schema: dict, timeout: float = 120) -> dict:
    """Ollama structured output: 'format' takes a JSON schema; the reply content is a JSON string."""
    resp = httpx.post(f"{OLLAMA_URL}/api/chat", timeout=timeout, json={
        "model": LLM_MODEL, "stream": False, "format": schema, "options": {"temperature": 0},
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    })
    resp.raise_for_status()
    return json.loads(resp.json()["message"]["content"])


# ---------------------------------------------------------------- 1. citation intent
INTENT_SCHEMA = {"type": "object", "properties": {"intent": {"type": "string", "enum": INTENTS}}, "required": ["intent"]}
INTENT_SYSTEM = (
    "You classify why a research paper cites another paper. Read the sentences where the citation appears.\n"
    "extends: the citing paper's own method builds directly on the cited method.\n"
    "compares_against: the cited work is a baseline whose numbers are reported or quoted.\n"
    "uses_dataset: the citing paper evaluates on a dataset introduced by the cited work.\n"
    "uses_method: the cited method or tool is used as a component (encoder, linker, released code).\n"
    "reproduces: the citing paper re-runs the cited work to check its results.\n"
    "supports: the citing paper presents evidence agreeing with the cited work.\n"
    "criticizes: the citing paper argues the cited work is wrong or flawed.\n"
    "corrects: an erratum or correction of the cited work.\n"
    "background: general context only.\n"
    "Pick the single strongest intent. Answer with JSON only."
)


def classify_intent(citing_title: str, cited_title: str, contexts: list, fallback) -> tuple[str, str]:
    """Returns (intent, source) where source is 'llm' or 'keywords'."""
    if not contexts:
        return "background", "no-context"
    user = (f"Citing paper: {citing_title}\nCited paper: {cited_title}\n"
            "Sentences where the cited paper appears:\n" + "\n".join(f"- {c}" for c in contexts[:4]))
    try:
        intent = ollama_json(INTENT_SYSTEM, user, INTENT_SCHEMA)["intent"]
        if intent in INTENTS:
            return intent, "llm"
    except Exception:
        pass
    return fallback(contexts), "keywords"


# ---------------------------------------------------------------- 2. claims
CLAIM_SCHEMA = {
    "type": "object",
    "properties": {"claims": {"type": "array", "maxItems": 3, "items": {
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "type": {"type": "string", "enum": CLAIM_TYPES},
            "about": {"type": "array", "items": {"type": "string"}},
            "scope": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["text", "type", "about"]}}},
    "required": ["claims"],
}
CLAIM_SYSTEM = (
    "You extract the main findings a research paper states about methods and datasets.\n"
    "Copy each finding as one sentence from the text (do not invent numbers).\n"
    "type: comparative (A beats or differs from B), causal (X happens because Y), sota (claims best result),\n"
    "efficiency (speed or cost trade-off), observational (a measured trend).\n"
    "about: names from KNOWN ENTITIES that the finding is about, spelled exactly as listed. A general phrase\n"
    "such as 'graph-based retrieval' or 'dense retrieval' means the listed entity of that kind the text discusses.\n"
    "scope: only for sota claims, items like 'KaveriHop|3-hop|EM'.\n"
    "Return at most 3 claims. Answer with JSON only."
)


def _sentences(text: str) -> list:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text or "") if len(s.strip()) > 20]


def snap_to_source(text: str, source: str, min_score: int = 90) -> str | None:
    """Return the paper's own sentence that the model copied, or None if it is not really in the paper.
    A 3B model often changes a word or drops a clause, so exact matching would throw good claims away;
    fuzzy matching with a high bar keeps them, and storing the paper's sentence means nothing invented is saved."""
    best, best_score, w = None, 0.0, words(text)
    for sentence in _sentences(source):
        ws = words(sentence)
        score = fuzz.ratio(w, ws)
        if len(w) >= 0.6 * len(ws):                  # the model copied most of the sentence
            score = max(score, fuzz.partial_ratio(w, ws))
        if score > best_score:
            best, best_score = sentence, score
    return best if best_score >= min_score else None


def extract_claims(title: str, abstract: str, conclusion: str, known_entities: list, notes: list | None = None) -> list:
    """known_entities: canonical names; notes: one line per entity (aliases, the paper that introduced it)."""
    listing = "\n".join(f"- {n}" for n in (notes or known_entities))
    user = (f"Title: {title}\nKNOWN ENTITIES:\n{listing}\n\n"
            f"Abstract:\n{abstract}\n\nConclusion / discussion:\n{conclusion}")
    try:
        claims = ollama_json(CLAIM_SYSTEM, user, CLAIM_SCHEMA)["claims"]
    except Exception:
        return []
    canonical = {norm(n): n for n in known_entities}
    clean, seen = [], set()
    for c in claims:
        # Validation: the sentence must really be in the paper, entities must be known, the type must be valid.
        sentence = snap_to_source(c.get("text", ""), abstract + " " + conclusion)
        if sentence is None or sentence in seen or c.get("type") not in CLAIM_TYPES:
            continue
        seen.add(sentence)
        about = [canonical[norm(a)] for a in c.get("about", []) if norm(a) in canonical]
        clean.append({"text": sentence, "type": c["type"], "about": list(dict.fromkeys(about)),
                      "scope": c.get("scope", [])})
    return clean


# ---------------------------------------------------------------- 3. claim relations (only for graph-selected pairs)
REL_SCHEMA = {"type": "object", "properties": {
    "relation": {"type": "string", "enum": RELATIONS}, "basis": {"type": "string"}}, "required": ["relation", "basis"]}
REL_SYSTEM = (
    "You compare two findings from research papers about the same methods.\n"
    "SUPPORTS: B gives evidence for A. CONTRADICTS: B says A is false under the same conditions.\n"
    "QUALIFIES: B shows A only holds in a narrower setting (another language, dataset or condition).\n"
    "UNRELATED: they do not bear on each other.\n"
    "basis: one short sentence naming the condition or evidence. Answer with JSON only."
)


def judge_claims(newer: dict, older: dict) -> dict:
    """newer/older: {text, paper_title, context}. Direction: (newer)-[REL]->(older)."""
    user = (f"Finding A (older, from '{older['paper_title']}'): {older['text']}\nContext A: {older['context']}\n\n"
            f"Finding B (newer, from '{newer['paper_title']}'): {newer['text']}\nContext B: {newer['context']}\n\n"
            "How does B relate to A?")
    try:
        out = ollama_json(REL_SYSTEM, user, REL_SCHEMA)
        return out if out["relation"] in RELATIONS else {"relation": "UNRELATED", "basis": "invalid model output"}
    except Exception as exc:
        return {"relation": "UNRELATED", "basis": f"LLM unavailable: {exc.__class__.__name__}"}


# ---------------------------------------------------------------- 4. agent narrative from verified facts
def write_answer(question: str, facts: list, allowed_names: set, all_names: set) -> str:
    """Short answer using only the facts. Rejected if it names an entity that is not in the facts."""
    schema = {"type": "object", "properties": {"answer": {"type": "string"}}, "required": ["answer"]}
    system = ("Answer the question using ONLY the numbered facts. Cite facts like [3]. At most 6 sentences. "
              "If the facts do not answer the question, say what is missing. Answer with JSON only.")
    user = f"Question: {question}\nFacts:\n" + "\n".join(f"[{i + 1}] {f}" for i, f in enumerate(facts))
    try:
        text = ollama_json(system, user, schema)["answer"]
    except Exception:
        return ""
    leaked = [n for n in all_names - allowed_names if n.lower() in text.lower()]
    return "" if leaked else text
