"""The research agent (LangGraph). The graph decides, the LLM judges, the vector store explains.

understand -> plan -> run_tools -> gather_evidence -> verify -> answer -> remember
                         ^                              |
                         +---- one more round if a gap -+        (at most 2 rounds)
understand --(names not found)--> clarify

The LLM never writes Cypher: a question is mapped to an intent from a closed list, the intent to a fixed list of
named queries (CYPHER.md), and every sentence of the answer must come from a numbered fact with its graph path.

    python -m app.agent.workflow --workspace gold "Is HopLens really state of the art?"
"""
import json
import operator
import re
import time
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph

from app.agent import llm, memory
from app.graph.analysis import Q, Analysis
from app.graph.ingest import norm, words

PLAN_TEMPLATES = {
    "relate_papers":     ["relationship"],
    "sota":              ["sota_check", "missing_citations"],
    "lineage":           ["lineage_up", "lineage_down"],
    "leaderboard":       ["leaderboard"],
    "disagreements":     ["claim_conflicts", "claim_support", "sota_check"],
    "missing_citations": ["missing_citations", "stale_citations"],
    "research_gaps":     ["gap_method_dataset", "gap_unreproduced", "gap_dataset_depth", "gap_task_without_method"],
    "people":            ["influential_papers", "bridge_authors", "author_groups", "affiliation_history"],
    "literature_review": ["library_papers", "claim_conflicts", "sota_check", "gap_method_dataset"],
    "recall":            ["recall_insights", "whats_new_since"],
}
# Checked in order; the first rule that matches decides. The LLM is asked only when no rule matches.
INTENT_RULES = [
    ("recall",            r"\b(remember|earlier|last time|saved|insights?|what'?s new|new since)\b"),
    ("sota",              r"state[- ]of[- ]the[- ]art|\bsota\b|\breally (the )?best\b"),
    ("missing_citations", r"\bcit(e|es|ed|ing|ation|ations)\b|\breference"),
    ("disagreements",     r"contradict|disagree|conflict|support|qualif|replicat|reproduc|consistent"),
    ("lineage",           r"lineage|builds? on|built on|extends?|descend|ancestor|come from|comes from|origin|evolv"),
    ("leaderboard",       r"leaderboard|\bbest\b|\btop\b|\brank|highest|lowest|fastest|\bscores?\b"),
    ("research_gaps",     r"\bgaps?\b|unexplored|never (been )?(tested|evaluated)|thesis|open problem|future work"),
    ("people",            r"\bauthors?\b|\bwho\b|influential|bridge|collaborat|groups?\b|institution"),
    ("relate_papers",     r"relat|connect|compare|differ|between|\band\b.*\?"),
    ("literature_review", r"review|overview|summar|survey|what do (the )?papers"),
]


class State(TypedDict, total=False):
    question: str
    intent: str
    entities: list           # [{id, label, name}] in the order they appear in the question
    plan: list               # [{tool, params}]
    results: dict            # tool -> rows
    facts: list              # [{n, text, papers, tool}]
    evidence: dict           # fact number -> [passage]
    gaps: list
    notes: list
    rounds: int
    answer: str
    answer_source: str
    events: Annotated[list, operator.add]


# ---------------------------------------------------------------- names in the graph
def short_title(title: str) -> str:
    parts = [p.strip() for p in (title or "").split(":")]
    if len(parts) > 1 and parts[0].lower() in ("erratum", "corrigendum"):
        return f"{parts[0]} ({parts[1]})"
    return parts[0] if len(parts) > 1 and len(parts[0]) <= 40 else (title or "")[:60]


def catalogue(graph) -> list:
    """Everything a question can name: papers (by short title), methods and datasets (every alias), authors."""
    out = []
    for pid, title in graph.ro_query("MATCH (p:Paper {in_library: true}) RETURN p.id, p.title").result_set:
        out.append({"id": pid, "label": "Paper", "name": short_title(title), "aliases": [short_title(title)]})
    for label in ("Method", "Dataset"):
        for eid, name, aliases in graph.ro_query(f"MATCH (e:{label}) RETURN e.id, e.name, e.aliases").result_set:
            out.append({"id": eid, "label": label, "name": name, "aliases": list({name, *(aliases or [])})})
    for aid, name in graph.ro_query("MATCH (a:Author) RETURN a.id, a.name").result_set:
        out.append({"id": aid, "label": "Author", "name": name, "aliases": [name, name.split()[-1]]})
    return out


def find_entities(question: str, cat: list) -> list:
    """Entities whose name or alias appears in the question as whole words, in order of appearance."""
    q = f" {words(question)} "
    hits = {}
    for e in cat:
        for alias in e["aliases"]:
            w = words(alias)
            if len(norm(alias)) >= 4 and f" {w} " in q:
                pos = q.index(f" {w} ")
                if e["id"] not in hits or pos < hits[e["id"]][0]:
                    hits[e["id"]] = (pos, -len(w), e)
    return [{"id": e["id"], "label": e["label"], "name": e["name"]} for _, _, e in sorted(hits.values(), key=lambda h: h[:2])]


def classify_intent(question: str, use_llm: bool) -> tuple[str, str]:
    text = question.lower()
    for intent, pattern in INTENT_RULES:
        if re.search(pattern, text):
            return intent, "rules"
    if use_llm:
        schema = {"type": "object", "properties": {"intent": {"type": "string", "enum": list(PLAN_TEMPLATES)}},
                  "required": ["intent"]}
        try:
            out = llm.ollama_json("Classify the research question into one intent. Answer with JSON only.",
                                  question, schema)["intent"]
            if out in PLAN_TEMPLATES:
                return out, "llm"
        except Exception:
            pass
    return "literature_review", "default"


# ---------------------------------------------------------------- facts: rows -> numbered sentences
def facts_from(tool: str, rows: list, names: dict) -> list:
    """One fact per row (or per meaningful item). Every fact keeps the paper ids it rests on."""
    P = lambda pid: names.get(pid, pid)
    out = []
    add = lambda text, papers=(): out.append({"text": text, "papers": [p for p in papers if p]})
    for r in rows:
        if tool == "relationship":
            a, b = r["a"], r["b"]
            for c in r["citations"]:
                add(f"{P(c['citing'])} cites {P(c['cited'])} (intent: {c['intent']}).", [c["citing"], c["cited"]])
            if r["shared_authors"]["authors"]:
                add(f"Shared authors: {', '.join(r['shared_authors']['authors'])}.", [a, b])
            if r["shared_datasets"]["datasets"]:
                add(f"Both evaluate on {', '.join(r['shared_datasets']['datasets'])}.", [a, b])
            if r["shared_methods"]["methods"]:
                add(f"Both propose or use {', '.join(r['shared_methods']['methods'])}.", [a, b])
            for l in r["lineage"]:
                add(f"Method lineage: {' -> '.join(l['chain'])}.", [a, b])
            for c in r["claims"]:
                add(f"Claim relation {c['relation']}: \"{c['claim_a']}\" vs \"{c['claim_b']}\" ({c['basis']}).", [a, b])
            for x in r["result_links"]:
                setting = f", {x['setting']}" if x.get("setting") else ""
                add(f"{x['relation']}: {x['method']} {x['split']} {x['new_value']} vs {x['original_value']}{setting}.", [a, b])
            for x in r["quotes"]:
                add(f"Quoted number: {x['method']} {x['value']} on {x['dataset']} {x['split']}.", [a, b])
            if not r["citations"]:
                add(f"No citation between {P(a)} and {P(b)} in either direction.", [a, b])
        elif tool == "sota_check":
            add(f"{P(r['paper'])} claims state of the art, but {r['better_method']} reports {r['better_value']} on "
                f"{r['dataset']} {r['split']} (in the {P(r['better_paper'])} paper), above the claimed {r['claimed_value']}.",
                [r["paper"], r["better_paper"]])
        elif tool == "missing_citations":
            why = "; ".join(f"{k.replace('_', ' ')}: {', '.join(v)}" for k in ("shared_datasets", "similar_methods",
                            "stronger_results") if (v := r.get(k)))
            add(f"{P(r['citing'])} does not cite {P(r['paper'])} (score {r['score']}; {why}).", [r["citing"], r["paper"]])
        elif tool == "stale_citations":
            add(f"{P(r['paper'])} cites {P(r['cites'])} but not its correction {P(r['correction'])}, published earlier.",
                [r["paper"], r["cites"], r["correction"]])
        elif tool in ("lineage_up", "lineage_down"):
            add(f"Lineage: {' -> '.join(r['chain'])} (each one extends the next).")
        elif tool == "leaderboard":
            extra = f"; other runs: {', '.join(str(o['value']) for o in r['other_runs'])}" if r.get("other_runs") else ""
            fix = f" (corrected, published as {r['as_published']})" if r.get("corrected") else ""
            add(f"{r['rank']}. {r['method']}: {r['value']}{fix}, reported in the {P(r['paper'])} paper{extra}.", [r["paper"]])
        elif tool == "claim_conflicts":
            add(f"{P(r['paper'])} {r['relation']} {P(r['other_paper'])}: \"{r['text']}\" vs \"{r['other_text']}\" "
                f"({r['basis']}).", [r["paper"], r["other_paper"]])
        elif tool == "claim_support":
            add(f"{P(r['paper'])} supports a finding of {P(r['supported_paper'])} ({r['basis']}).",
                [r["paper"], r["supported_paper"]])
        elif tool == "gap_method_dataset" and r["never_evaluated_on"]:
            add(f"{r['method']} has never been evaluated on {', '.join(r['never_evaluated_on'])}.")
        elif tool == "gap_unreproduced":
            add(f"No one has reproduced {r['method']} ({P(r['paper'])}).", [r["paper"]])
        elif tool == "gap_dataset_depth":
            add(f"{r['dataset']} ({r['language'] or 'language not stated'}) has splits {', '.join(r['splits'] or [])}.")
        elif tool == "gap_task_without_method":
            add(f"Task '{r['task']}' has claims but no method proposed in the library (only {', '.join(r['external_methods'])}).")
        elif tool == "influential_papers":
            add(f"Influential (PageRank over citations): {r['title']} ({r['score']:.3f}).", [r["id"]])
        elif tool == "bridge_authors":
            add(f"Bridge author (betweenness over co-authorship): {r['author']} ({r['score']:.1f}).")
        elif tool == "author_groups":
            add(f"Co-author group: {', '.join(r['authors'])}.")
        elif tool == "affiliation_history":
            add(f"Affiliation: {r['institution']} ({r['first_year']}-{r['last_year']}).")
        elif tool == "library_papers":
            add(f"{r['year']}: {r['title']} by {', '.join(r['authors'])}.", [r["id"]])
        elif tool == "recall_insights":
            add(f"Saved insight ({r['session']}): {r['insight'].rstrip('.')}.")
        elif tool == "whats_new_since":
            add(f"New since you asked \"{r['earlier_question']}\": {r['paper']} ({r['relation']} {names.get(r['topic'], r['topic'])}).",
                [r["paper_id"]])
    return out


# ---------------------------------------------------------------- the agent
def build(graph, store=None, session_id: str | None = None, use_llm: bool = True):
    A = Analysis(graph)
    cat = catalogue(graph)
    names = {e["id"]: e["name"] for e in cat}
    published = dict(graph.ro_query("MATCH (p:Paper {in_library: true}) RETURN p.id, p.published").result_set)

    def papers_of(entities: list) -> list:
        """Papers named directly, plus the papers that propose or introduce named methods and datasets."""
        out = []
        for e in entities:
            if e["label"] == "Paper":
                out.append(e["id"])
            elif e["label"] in ("Method", "Dataset"):
                out += [r[0] for r in graph.ro_query(
                    f"MATCH (p:Paper {{in_library: true}})-[:PROPOSES|INTRODUCES]->(:{e['label']} {{id: $id}}) RETURN p.id",
                    {"id": e["id"]}).result_set]
        return list(dict.fromkeys(out))

    def first(entities, label):
        return next((e["id"] for e in entities if e["label"] == label), None)

    def understand(s: State):
        intent, how = classify_intent(s["question"], use_llm)
        entities = find_entities(s["question"], cat)
        return {"intent": intent, "entities": entities, "rounds": 0, "results": {}, "facts": [],
                "events": [{"step": "understand", "intent": intent, "decided_by": how,
                            "entities": [f"{e['name']} ({e['label']})" for e in entities]}]}

    def needs(s: State) -> str | None:
        """What the intent cannot do without: returns a question for the user, or None."""
        ents, intent = s["entities"], s["intent"]
        if intent == "relate_papers" and len(papers_of(ents)) < 2:
            return "Which two papers (or methods) should I compare?"
        if intent in ("lineage", "sota") and not first(ents, "Method"):
            return "Which method do you mean?"
        if intent == "leaderboard" and not first(ents, "Dataset"):
            return "Which dataset (and split, e.g. 3-hop) should the leaderboard use?"
        return None

    def after_understand(s: State) -> str:
        return "clarify" if needs(s) else "plan"

    def clarify(s: State):
        known = ", ".join(e["name"] for e in cat if e["label"] in ("Method", "Dataset"))
        text = f"{needs(s)} Names I know: {known}."
        return {"answer": text, "answer_source": "clarify", "events": [{"step": "clarify", "answer": text}]}

    def plan(s: State):
        ents, q = s["entities"], s["question"].lower()
        steps = []
        for tool in PLAN_TEMPLATES[s["intent"]]:
            params = {}
            if tool == "relationship":
                a, b = papers_of(ents)[:2]
                params = {"a": a, "b": b}
            elif tool in ("lineage_up", "lineage_down"):
                params = {"method": first(ents, "Method")}
            elif tool == "leaderboard":
                split = re.search(r"\b(\d)[- ]hop\b", q)
                metric = "metric-latency" if re.search(r"latency|fast|slow|speed", q) else "metric-em"
                params = {"dataset": first(ents, "Dataset"), "split": f"{split.group(1)}-hop" if split else "3-hop",
                          "metric": metric}
            elif tool == "missing_citations":
                if s["intent"] == "sota":
                    params = {"paper": papers_of([e for e in ents if e["label"] == "Method"])[:1] or [None]}
                    params = {"paper": params["paper"][0]}
                else:
                    params = {"paper": (papers_of(ents) or [None])[0]}
            elif tool == "affiliation_history":
                if not first(ents, "Author"):
                    continue
                params = {"author": first(ents, "Author")}
            elif tool in ("influential_papers",):
                params = {"k": 5}
            elif tool == "bridge_authors":
                params = {"k": 3}
            elif tool == "recall_insights":
                params = {"ids": [e["id"] for e in ents]}
            elif tool == "whats_new_since":
                if not session_id:
                    continue
                params = {"session": session_id}
            steps.append({"tool": tool, "params": params})
        return {"plan": steps, "events": [{"step": "plan", "tools": [f"{x['tool']}({x['params']})" for x in steps]}]}

    def call(tool: str, params: dict) -> list:
        if tool == "relationship":
            rel = A.relationship(params["a"], params["b"])
            return [{"a": params["a"], "b": params["b"], **rel}]
        if tool == "leaderboard":
            rows = A.leaderboard(params["dataset"], params["split"], params["metric"])
            return [{**r, "rank": i + 1} for i, r in enumerate(rows)]
        if tool == "missing_citations":
            papers = [params["paper"]] if params.get("paper") else list(published)
            rows = [{**r, "citing": p} for p in papers for r in A.missing_citations(p)]
            return [r for r in rows if r["paper"] == params["against"]] if params.get("against") else rows
        if tool in ("recall_insights", "whats_new_since"):
            return memory.run(graph, tool, **params)
        return A.run(tool, **params)

    def run_tools(s: State):
        results, log = dict(s.get("results", {})), []
        for step in s["plan"]:
            if step["tool"] in results:
                continue
            start, before = time.time(), len(A.log)
            rows = call(step["tool"], step["params"])
            if step["tool"] == "sota_check" and s["intent"] == "sota":
                mine = papers_of([e for e in s["entities"] if e["label"] == "Method"])
                rows = [r for r in rows if r["paper"] in mine]
            results[step["tool"]] = rows
            queries = [x["query"] for x in A.log[before:]] or [step["tool"]]
            log.append({"tool": step["tool"], "params": step["params"], "rows": len(rows),
                        "ms": round((time.time() - start) * 1000), "cypher": {q: Q[q].strip() for q in queries if q in Q}})
        return {"results": results, "rounds": s["rounds"] + 1, "events": [{"step": "run_tools", "round": s["rounds"] + 1,
                                                                          "tool_log": log}]}

    def gather_evidence(s: State):
        facts = []
        for tool, rows in s["results"].items():
            facts += [{**f, "tool": tool} for f in facts_from(tool, rows, names)]
        for i, f in enumerate(facts, 1):
            f["n"] = i
        evidence = {}
        if store is not None:
            for f in facts[:8]:                                # the passage behind the strongest facts
                if f["papers"]:
                    try:
                        hits = store.evidence(f["text"], f["papers"], k=1)
                    except Exception:
                        hits = []
                    if hits:
                        evidence[f["n"]] = [{"paper": names.get(h["paper_id"], h["paper_id"]), "section": h["section"],
                                             "excerpt": h["excerpt"]} for h in hits]
        return {"facts": facts, "evidence": evidence,
                "events": [{"step": "gather_evidence", "facts": len(facts), "passages": len(evidence)}]}

    def verify(s: State):
        """Gaps get one more round with a fallback tool; after two rounds the agent answers with what it has."""
        gaps, notes, extra = [], [], []
        res = s["results"]
        if s["intent"] == "relate_papers" and res.get("relationship") and not res["relationship"][0]["citations"]:
            a, b = s["plan"][0]["params"]["a"], s["plan"][0]["params"]["b"]
            newer = a if (published.get(a) or "") >= (published.get(b) or "") else b
            notes.append("no citation between the two papers, so the agent also checked whether the newer one should cite the older")
            extra.append({"tool": "missing_citations", "params": {"paper": newer, "against": b if newer == a else a}})
        if s["intent"] == "sota" and not res.get("sota_check"):
            gaps.append("no state-of-the-art claim found to check")
        if not s["facts"]:
            gaps.append("the graph returned nothing for this plan")
        extra = [x for x in extra if x["tool"] not in res]
        return {"gaps": gaps, "notes": notes, "plan": s["plan"] + extra,
                "events": [{"step": "verify", "gaps": gaps, "notes": notes, "extra_tools": [x["tool"] for x in extra]}]}

    def after_verify(s: State) -> str:
        pending = any(x["tool"] not in s["results"] for x in s["plan"])
        return "run_tools" if pending and s["rounds"] < 2 else "answer"

    def answer(s: State):
        facts = s["facts"]
        lines = [f"[{f['n']}] {f['text']}" for f in facts]
        text, source = "", "template"
        if use_llm and facts:
            mentioned = {e["name"] for e in cat if any(e["name"].lower() in f["text"].lower() for f in facts)}
            text = llm.write_answer(s["question"], [f["text"] for f in facts], mentioned, {e["name"] for e in cat})
            source = "llm" if text else "template"
        if not text:
            text = template_answer(s, facts)
        body = text + ("\n\nFacts from the graph:\n" + "\n".join(lines) if lines else "")
        if s.get("notes"):
            body += "\n\nAlso checked: " + "; ".join(s["notes"])
        if s.get("gaps"):
            body += "\n\nNot found: " + "; ".join(s["gaps"])
        return {"answer": body, "answer_source": source, "events": [{"step": "answer", "source": source}]}

    def remember(s: State):
        if not session_id:
            return {"events": [{"step": "remember", "saved": False}]}
        qid = memory.log_question(graph, session_id, s["question"], s["intent"],
                                  {"answer": s["answer"], "facts": s["facts"], "evidence": s.get("evidence", {})},
                                  [e["id"] for e in s["entities"]])
        return {"events": [{"step": "remember", "saved": True, "question_id": qid}]}

    b = StateGraph(State)
    for name, fn in [("understand", understand), ("clarify", clarify), ("plan", plan), ("run_tools", run_tools),
                     ("gather_evidence", gather_evidence), ("verify", verify), ("answer", answer), ("remember", remember)]:
        b.add_node(name, fn)
    b.add_edge(START, "understand")
    b.add_conditional_edges("understand", after_understand, ["plan", "clarify"])
    b.add_edge("clarify", END)
    b.add_edge("plan", "run_tools")
    b.add_edge("run_tools", "gather_evidence")
    b.add_edge("gather_evidence", "verify")
    b.add_conditional_edges("verify", after_verify, ["run_tools", "answer"])
    b.add_edge("answer", "remember")
    b.add_edge("remember", END)
    return b.compile()


def template_answer(s: State, facts: list) -> str:
    """A plain answer built only from the facts, used when the LLM is off or its answer fails the leak check."""
    if s["intent"] == "sota":
        method = next((e["name"] for e in s["entities"] if e["label"] == "Method"), "The method")
        beaten = [f for f in facts if f["tool"] == "sota_check"]
        missing = [f for f in facts if f["tool"] == "missing_citations"]
        if beaten:
            text = f"No. {method}'s state-of-the-art claim does not hold: {len(beaten)} earlier result(s) are higher (see facts)."
        else:
            text = f"The graph has no earlier result that beats {method}'s claim."
        if missing:
            text += f" It also leaves out {len(missing)} earlier paper(s) it should probably cite."
        return text
    if not facts:
        return "The graph has no facts for this question yet."
    names = ", ".join(dict.fromkeys(e["name"] for e in s["entities"])) or "the library"
    return f"Here is what the graph shows about {names} ({len(facts)} facts)."


def ask(graph, question: str, store=None, session_id: str | None = None, use_llm: bool = True) -> dict:
    return build(graph, store, session_id, use_llm).invoke({"question": question})


def stream(graph, question: str, store=None, session_id: str | None = None, use_llm: bool = True):
    """Yields each node's events as it finishes (the API sends these to the UI as server-sent events).
    The last event is always {"step": "final", ...} with the answer, the facts and their evidence."""
    final = {"step": "final", "answer": "", "source": "", "facts": [], "evidence": {}}
    for update in build(graph, store, session_id, use_llm).stream({"question": question}, stream_mode="updates"):
        for node, delta in update.items():
            delta = delta or {}
            for event in delta.get("events", []):
                yield event
            if "answer" in delta:
                final.update(answer=delta["answer"], source=delta.get("answer_source", ""))
            if "facts" in delta:
                final.update(facts=delta["facts"], evidence=delta.get("evidence", {}))
    yield final


if __name__ == "__main__":
    import argparse

    from app.graph.client import UnknownWorkspace, graph_for

    ap = argparse.ArgumentParser(description="Ask the research agent a question.")
    ap.add_argument("--workspace", required=True)
    ap.add_argument("--no-llm", action="store_true", help="template answer only (no Ollama)")
    ap.add_argument("--evidence", action="store_true", help="search ChromaDB for the passage behind each fact")
    ap.add_argument("question")
    args = ap.parse_args()
    try:
        g = graph_for(args.workspace, must_exist=True)
    except UnknownWorkspace as e:
        raise SystemExit(str(e))
    st = None
    if args.evidence:
        from app.config import settings
        from app.docs.docstore import DocStore
        st = DocStore(str(settings.chroma_path), args.workspace)
    for ev in stream(g, args.question, st, use_llm=not args.no_llm):
        if ev["step"] == "final":
            print("\n" + ev["answer"])
        else:
            print(json.dumps({k: v for k, v in ev.items() if k != "tool_log"}, ensure_ascii=False))
