# GraphMind Research — project context for Claude

## What we are building
A research-paper relationship agent. Users upload PDFs; we build a knowledge graph in FalkorDB
(papers, authors, citations with intent, methods, datasets, results, claims and how claims relate),
store passages in ChromaDB, and answer questions with graph paths plus source passages. Pipeline
agents coordinate through Job nodes in the graph; research sessions and insights are saved as memory.
Hackathon: Graph Hacks (WeMakeDevs × FalkorDB), 15–18 Oct 2026. Tracks: Agents That Act on Connected
Data; Agent Memory and Coordination.

## Non-negotiable rules
1. FalkorDB is the source of truth. PDFs are read only by backend/app/graph/pdf_parser.py, whose
   output is written to the graph by ingest.py. Every API answer comes from Cypher. If FalkorDB is
   unreachable, return HTTP 503 — never fall back to files or memory.
2. All Cypher lives in named, parameterised queries (Q dicts in analysis.py and memory.py, plus
   ingest.py). Never format user input into Cypher. The LLM never writes Cypher.
3. The LLM (Ollama llama3.2) is used only in backend/app/agent/llm.py: citation intent, claim
   extraction, claim-pair relation, and the final short answer. Closed JSON schemas, temperature 0,
   validated outputs, deterministic fallbacks.
4. Direction conventions: (newer Claim)-[:SUPPORTS|CONTRADICTS|QUALIFIES]->(older Claim);
   (Method)-[:EXTENDS]->(parent Method); (Result)-[:REPRODUCES|CORRECTS]->(original Result).
5. Upload order must not change the final graph. reconcile() runs after every upload.
6. Each workspace = one FalkorDB graph "ws_<name>" + one ChromaDB collection "papers_<name>".
7. Data is synthetic (corpus/) or open-access papers the user is allowed to use.
8. No SQLite or other database. Run logs, questions, answers (as a JSON string property on the
   Question node) and insights are stored in FalkorDB. Where docs/BUILD_GUIDE.md mentions SQLite,
   use FalkorDB instead.

## Stack
Python 3.11+, FastAPI, LangGraph >= 1.0, falkordb (Python client), chromadb >= 1.0 (PersistentClient),
pymupdf, rapidfuzz, httpx, pydantic v2, sse-starlette, pytest. FalkorDB in Docker on 6379 (browser 3000).
Ollama at localhost:11434 with llama3.2:latest and nomic-embed-text. Frontend: React + Vite + TypeScript,
Tailwind v4 (@tailwindcss/vite), @xyflow/react with @dagrejs/dagre, lucide-react.

## Repo layout
backend/app/graph/   client.py, gold_loader.py, analysis.py, pdf_parser.py, ingest.py
backend/app/docs/    docstore.py
backend/app/agent/   llm.py, memory.py, enrich.py, pipeline.py (agents), workflow.py (research agent)
backend/app/api/     main.py, schemas.py
backend/app/eval_extraction.py
backend/tests/       test_analysis.py, test_ingest.py, test_enrich.py, test_pipeline.py, test_agent.py, test_api.py
frontend/src/        pages and components
corpus/ ground_truth/ ontology.json docs/

## Ground truth
ground_truth/gold_graph.json (oracle mode and scoring) and ground_truth/expected_answers.json.
Tests must pass before moving to the next phase.

## How to work with me
I am an AI/ML trainer and must explain every part to judges. After each task explain what you built,
WHY it is built that way (with the theory), and how to verify it. Work in small steps, run tests after
each change, show the commands you ran. Ask before adding dependencies. If the data looks wrong, tell me.

## Working mode
- Create only the file or folder I ask for in each request. Never create extra files.
- After creating it: explain what it does, why it is built that way (with the theory), and give me
  the exact command to verify it. Then stop and wait for my next request.
- Commit only when I say "commit", using a short conventional message (feat:, chore:, test:, docs:).

## FalkorDB 6.0.1 notes
- After a WHERE that contains a pattern predicate, add WITH before the next MATCH.
- Don't chain several OPTIONAL MATCH ... collect() stages; use one query per signal and combine in Python.
- Algorithms follow edge direction: store undirected relations (COAUTHOR) in both directions.
