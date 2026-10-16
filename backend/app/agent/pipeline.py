"""Four agents that turn uploaded PDFs into the knowledge graph, coordinating ONLY through the graph:
Job nodes carry the work from stage to stage, and one Lock node guards the steps that rewrite the whole graph.

    Parser    (stage 'parse')     PDF -> papers, authors, citations, results; passages -> ChromaDB      no LLM
    Extractor (stage 'extract')   citation intents (graph rules), claims (LLM picks a sentence)
    Linker    (stage 'link')      reconcile entities, SIMILAR_TO between look-alike methods (embeddings)
    Critic    (stage 'critique')  claim relations (LLM on graph-picked pairs), sota claims vs numbers

No agent calls another. Each one claims a job for its stage from the graph, does its work, and moves the job on.
Run on a folder (no API needed):  python -m app.agent.pipeline --workspace agents --workers 2 ../corpus/pdf
"""
import threading
import time
import traceback

from app.agent import enrich, memory


class Agent(threading.Thread):
    stage = ""

    def __init__(self, name: str, ctx: dict, stop: threading.Event, poll: float = 0.5):
        super().__init__(name=name, daemon=True)
        self.ctx, self.stop_event, self.poll = ctx, stop, poll

    def run(self):
        graph = self.ctx["graph"]
        while not self.stop_event.is_set():
            job = memory.claim(graph, self.stage, self.name)
            if job is None:
                self.stop_event.wait(self.poll)        # nothing for this stage yet: look again shortly
                continue
            try:
                self.work(job)
                memory.advance(graph, job["id"], self.stage, self.name)
            except Exception as exc:                   # the job goes back to 'ready' (or 'failed' after 3 tries)
                memory.fail(graph, job["id"], f"{self.name}: {exc.__class__.__name__}: {exc}")
                if self.ctx.get("verbose"):
                    traceback.print_exc()

    def paper_of(self, job: dict) -> str:
        rows = self.ctx["graph"].ro_query("MATCH (:Job {id: $id})-[:FOR_PAPER]->(p:Paper) RETURN p.id",
                                          {"id": job["id"]}).result_set
        if not rows:
            raise RuntimeError("job has no paper yet")
        return rows[0][0]

    def work(self, job: dict) -> None:
        raise NotImplementedError


class ParserAgent(Agent):
    stage = "parse"

    def work(self, job):
        from app.graph.ingest import ingest_pdf
        g = self.ctx["graph"]
        # Ingestion matches papers and merges entities across the whole graph: one parser at a time.
        with memory.graph_lock(g, "graph-write", self.name):
            pid = ingest_pdf(g, job["file"], self.ctx["ontology"], self.ctx["store"])
            memory.run(g, "job_link_paper", id=job["id"], paper=pid)
            # Citations INTO this paper were labelled while it was a stub: label them again now it is here.
            g.query("MATCH (:Paper)-[c:CITES]->(:Paper {id: $pid}) SET c.intent = 'unclassified'", {"pid": pid})


class ExtractorAgent(Agent):
    stage = "extract"

    def work(self, job):
        g, pid = self.ctx["graph"], self.paper_of(job)
        with memory.graph_lock(g, "graph-write", self.name):          # labels every unlabelled citation, then reconciles
            enrich.classify_citations(g, use_llm=self.ctx["intents_by"] == "llm")
        enrich.extract_claims(g, pid, self.ctx["ontology"])           # per paper: agents run this in parallel


class LinkerAgent(Agent):
    stage = "link"

    def work(self, job):
        from app.graph.ingest import reconcile
        g, pid = self.ctx["graph"], self.paper_of(job)
        with memory.graph_lock(g, "graph-write", self.name):
            reconcile(g)
        enrich.link_similar_methods(g, self.ctx["store"], self.ctx["threshold"], pid)


class CriticAgent(Agent):
    stage = "critique"

    def work(self, job):
        g, pid = self.ctx["graph"], self.paper_of(job)
        enrich.relate_claims(g, self.ctx["store"], pid)               # per paper, in parallel
        with memory.graph_lock(g, "graph-write", self.name):
            enrich.check_claims(g)


AGENTS = [ParserAgent, ExtractorAgent, LinkerAgent, CriticAgent]
SHORT = {"parse": "parser", "extract": "extractor", "link": "linker", "critique": "critic"}


def start_agents(ctx: dict, workers_per_stage: int = 1) -> tuple[threading.Event, list]:
    """Start N agents per stage. Returns the stop event and the threads (call stop.set() to end them)."""
    stop = threading.Event()
    threads = [cls(f"{SHORT[cls.stage]}-{i + 1}", ctx, stop) for cls in AGENTS for i in range(workers_per_stage)]
    for t in threads:
        t.start()
    return stop, threads


def finished(rows: list) -> bool:
    return bool(rows) and all(r["status"] in ("done", "failed") for r in rows)


if __name__ == "__main__":
    import argparse
    import json
    from pathlib import Path

    from app.config import settings
    from app.docs.docstore import DocStore
    from app.graph.client import graph_for
    from app.graph.ingest import _expand

    ap = argparse.ArgumentParser(description="Run the four pipeline agents on a folder of PDFs.")
    ap.add_argument("--workspace", required=True)
    ap.add_argument("--workers", type=int, default=1, help="agents per stage")
    ap.add_argument("--intents-by", choices=["llm", "keywords"], default="keywords")
    ap.add_argument("--threshold", type=float, default=0.85)
    ap.add_argument("--verbose", action="store_true", help="print the full traceback when an agent's work fails")
    ap.add_argument("pdfs", nargs="+")
    args = ap.parse_args()

    graph = graph_for(args.workspace)
    ctx = {"graph": graph, "store": DocStore(str(settings.chroma_path), args.workspace),
           "ontology": json.loads((Path(__file__).resolve().parents[3] / "ontology.json").read_text(encoding="utf-8")),
           "intents_by": args.intents_by, "threshold": args.threshold, "verbose": args.verbose}
    jobs = [memory.create_job(graph, str(f)) for f in _expand(args.pdfs)]
    print(f"{len(jobs)} jobs created; {args.workers} agent(s) per stage")
    stop, _ = start_agents(ctx, args.workers)
    t0, last = time.time(), None
    while True:
        rows = [r for r in memory.board(graph) if r["id"] in jobs]
        counts = {s: sum(r["stage"] == s for r in rows) for s in memory.STAGES}
        running = sorted(f"{r['agent']}" for r in rows if r["status"] == "running")
        line = "  ".join(f"{s}:{n}" for s, n in counts.items()) + f"   running: {', '.join(running) or '-'}"
        if line != last:
            print(f"{time.time() - t0:6.0f}s  {line}")
            last = line
        if finished(rows):
            break
        time.sleep(1)
    stop.set()
    failed = [r for r in rows if r["status"] == "failed"]
    for r in failed:
        print(f"FAILED {Path(r['file']).name}: {r['error']}")
    print(f"done in {time.time() - t0:.0f}s; history of the first job: {rows[0]['history']}")
