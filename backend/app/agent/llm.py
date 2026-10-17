"""The only places the LLM is used. Every call: closed JSON schema, temperature 0, validated, with a fallback.

llama3.2 (3B) is reliable at short classification and at picking from a short numbered list.
It is NOT used for anything the graph or the parser can decide, and the graph narrows every choice first.
"""
import json
import os
import re

import httpx

from app.graph.ingest import norm
from app.config import settings

LLM_PROVIDER = settings.llm_provider.strip().lower()
OLLAMA_URL = settings.ollama_url
LLM_MODEL = settings.llm_model
GROQ_API_KEY = settings.groq_api_key
GROQ_MODEL = settings.groq_model

INTENTS = ["extends", "compares_against", "uses_dataset", "uses_method", "reproduces",
           "supports", "criticizes", "corrects", "background"]
CLAIM_TYPES = ["comparative", "causal", "sota", "efficiency", "observational"]
RELATIONS = ["UNRELATED", "SUPPORTS", "CONTRADICTS", "QUALIFIES"]


def provider_json(system: str, user: str, schema: dict, timeout: float = 120) -> dict:
    """Call the configured LLM provider and parse its JSON response."""
    if LLM_PROVIDER == "groq":
        if not GROQ_API_KEY:
            raise RuntimeError("GROQ_API_KEY is missing")

        system_with_schema = (
            system
            + "\nReturn a valid JSON object matching this JSON Schema:\n"
            + json.dumps(schema)
        )

        resp = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            timeout=timeout,
            json={
                "model": GROQ_MODEL,
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system_with_schema},
                    {"role": "user", "content": user},
                ],
            },
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        return json.loads(content)

    if LLM_PROVIDER == "ollama":
        resp = httpx.post(
            f"{OLLAMA_URL}/api/chat",
            timeout=timeout,
            json={
                "model": LLM_MODEL,
                "stream": False,
                "format": schema,
                "options": {"temperature": 0},
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
        )
        resp.raise_for_status()
        return json.loads(resp.json()["message"]["content"])

    raise ValueError(f"Unsupported LLM_PROVIDER: {LLM_PROVIDER}")


# ---------------------------------------------------------------- 1. citation intent
INTENT_MEANING = {
    "extends": "the citing paper's own method builds directly on the cited method",
    "compares_against": "the cited method is a baseline whose numbers the citing paper reports or quotes",
    "uses_dataset": "the citing paper evaluates on a dataset the cited work introduced",
    "uses_method": "the cited method or tool is used as a component (encoder, linker, released code)",
    "reproduces": "the citing paper re-runs the cited work to check whether its results hold",
    "supports": "the citing paper presents evidence that agrees with the cited work",
    "criticizes": "the citing paper argues the cited work is wrong or flawed",
    "corrects": "an erratum or correction of the cited work",
    "background": "general context only",
}


def classify_intent(citing_title: str, cited_title: str, contexts: list, fallback,
                    options: list | None = None, facts: list | None = None) -> tuple[str, str]:
    """Returns (intent, source). options: the intents the graph still allows for this citation;
    facts: what the graph already knows about the two papers (shown to the model as evidence)."""
    options = options or INTENTS
    if not contexts:
        return ("background" if "background" in options else options[0]), "no-context"
    system = ("You classify why a research paper cites another paper. Read the sentences where the citation appears.\n"
              + "\n".join(f"{i}: {INTENT_MEANING[i]}." for i in options)
              + "\nPick the single strongest intent. Answer with JSON only.")
    user = (f"Citing paper: {citing_title}\nCited paper: {cited_title}\n"
            + ("Facts from the knowledge graph:\n" + "\n".join(f"- {f}" for f in facts) + "\n" if facts else "")
            + "Sentences where the cited paper appears:\n" + "\n".join(f"- {c}" for c in contexts[:4]))
    schema = {"type": "object", "properties": {"intent": {"type": "string", "enum": options}}, "required": ["intent"]}
    try:
        intent = provider_json(system, user, schema)["intent"]
        if intent in options:
            return intent, "llm"
    except Exception:
        pass
    guess = fallback(contexts)
    return (guess if guess in options else options[0]), "keywords"


# ---------------------------------------------------------------- 2. claims: pick findings from numbered sentences
CLAIM_SCHEMA = {
    "type": "object",
    "properties": {"claims": {"type": "array", "maxItems": 2, "items": {
        "type": "object",
        "properties": {
            "sentence": {"type": "integer"},
            "type": {"type": "string", "enum": CLAIM_TYPES},
            "about": {"type": "array", "items": {"type": "string"}},
            "scope": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["sentence", "type", "about"]}}},
    "required": ["claims"],
}
CLAIM_SYSTEM = (
    "You find the main FINDINGS among numbered sentences from a research paper.\n"
    "A finding states a result, a comparison, a cause, a trade-off or a trend, for example\n"
    "'X outperforms Y on 3-hop questions' or 'accuracy drops because entity linking fails'.\n"
    "Pick at most 2 sentence numbers, the most important finding first.\n"
    "type: comparative (A beats or differs from B), causal (X happens because Y), sota (claims the best result),\n"
    "efficiency (speed or cost trade-off), observational (a measured trend).\n"
    "about: names from KNOWN ENTITIES that the finding is about, spelled exactly as listed. A general phrase\n"
    "such as 'graph-based retrieval' or 'dense retrieval' means the listed entity of that kind the paper discusses.\n"
    "scope: only for sota claims, items like 'KaveriHop|3-hop|EM'.\n"
    "Answer with JSON only."
)
# Sentences that only say what the paper does are never findings; dropping them shortens the list the model reads.
NOT_A_FINDING = re.compile(r"^(in )?(this|our) (paper|work)\b|^we (propose|introduce|present|release|describe|build|"
                           r"construct|collect|train|evaluate|re-run|rerun|reproduce|report|study)\b", re.I)


CITATION = re.compile(r"\[\d")      # a sentence citing [n] reports someone else's work, not this paper's finding


def _sentences(text: str) -> list:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text or "") if len(s.strip()) > 20]


def candidate_sentences(abstract: str, conclusion: str) -> list:
    seen, out = set(), []
    for s in _sentences(abstract) + _sentences(conclusion):
        if s not in seen and not NOT_A_FINDING.search(s) and not CITATION.search(s):
            seen.add(s)
            out.append(s)
    return out


def extract_claims(title: str, abstract: str, conclusion: str, known_entities: list, notes: list | None = None) -> list:
    """The model picks sentence NUMBERS, so a stored claim is always the paper's own sentence, never model text.
    known_entities: canonical names; notes: one line per entity (aliases, the paper that introduced it)."""
    sentences = candidate_sentences(abstract, conclusion)
    if not sentences:
        return []
    listing = "\n".join(f"- {n}" for n in (notes or known_entities))
    numbered = "\n".join(f"{i}. {s}" for i, s in enumerate(sentences, 1))
    user = f"Title: {title}\nKNOWN ENTITIES:\n{listing}\n\nSentences:\n{numbered}"
    try:
        picked = provider_json(CLAIM_SYSTEM, user, CLAIM_SCHEMA)["claims"]
    except Exception:
        return []
    canonical = {norm(n): n for n in known_entities}
    clean, used = [], set()
    for c in picked:
        n = c.get("sentence")
        if not isinstance(n, int) or not 1 <= n <= len(sentences) or n in used or c.get("type") not in CLAIM_TYPES:
            continue
        used.add(n)
        about = [canonical[norm(a)] for a in c.get("about", []) if norm(a) in canonical]
        clean.append({"text": sentences[n - 1], "type": c["type"], "about": list(dict.fromkeys(about)),
                      "scope": c.get("scope", [])})
    return clean


# ---------------------------------------------------------------- 3. claim relations (only for graph-selected pairs)
REL_SCHEMA = {"type": "object", "properties": {
    "relation": {"type": "string", "enum": RELATIONS}, "basis": {"type": "string"}}, "required": ["relation", "basis"]}
REL_SYSTEM = (
    "You compare two findings from research papers about the same methods. B is newer than A.\n"
    "SUPPORTS: B reports evidence that agrees with A.\n"
    "CONTRADICTS: B reports that A does not hold in the setting A describes.\n"
    "QUALIFIES: B reports that A holds in some settings but fails in another named setting\n"
    "(another language, dataset or condition).\n"
    "UNRELATED: B does not test or discuss what A states. If unsure, answer UNRELATED.\n"
    "basis: one short sentence naming the evidence or the condition. Answer with JSON only."
)


def judge_claims(newer: dict, older: dict, facts: list | None = None) -> dict:
    """newer/older: {text, paper_title, context}. Direction: (newer)-[REL]->(older)."""
    user = (f"Finding A (older, from '{older['paper_title']}'): {older['text']}\nContext A: {older['context']}\n\n"
            f"Finding B (newer, from '{newer['paper_title']}'): {newer['text']}\nContext B: {newer['context']}\n\n"
            + ("Facts from the knowledge graph:\n" + "\n".join(f"- {f}" for f in facts) + "\n\n" if facts else "")
            + "How does B relate to A?")
    try:
        out = provider_json(REL_SYSTEM, user, REL_SCHEMA)
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
        text = provider_json(system, user, schema)["answer"]
    except Exception:
        return ""
    leaked = [n for n in all_names - allowed_names if n.lower() in text.lower()]
    return "" if leaked else text
