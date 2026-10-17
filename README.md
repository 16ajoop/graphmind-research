# GraphMind Research

## Pitch
A short description of the problem (understanding how research papers relate) and how GraphMind solves it.

## Tracks entered
Agents That Act on Connected Data; Agent Memory and Coordination.

## Architecture
A diagram and walkthrough of the upload → parse → ingest → reconcile → answer pipeline and its agents.

## Graph data model
See [docs/DATA_MODEL.md](docs/DATA_MODEL.md): node labels, relationships and direction conventions, with counts
measured on the gold graph.

## Why FalkorDB is central
Why the graph is the single source of truth for answers, agent coordination (Job nodes) and memory.

## Cypher queries
See [docs/CYPHER.md](docs/CYPHER.md): every named, parameterised query the agent can run. It is generated from
`backend/app/graph/analysis.py` (`python -m app.graph.export_cypher`; `--check` fails if it is out of date).

## Evaluation
See [docs/EVALUATION.md](docs/EVALUATION.md): the extracted graph scored against `ground_truth/gold_graph.json`
(precision / recall per relationship, citation-intent accuracy), with measured numbers.

## Local setup
Needs Docker, Python 3.11+, Node 20+ and Ollama (`llama3.2`, `nomic-embed-text`).

```powershell
docker compose up -d                       # FalkorDB on 6379, browser UI on http://localhost:3000

cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m app.health                       # FalkorDB, Ollama and the Chroma path
python -m app.graph.gold_loader --workspace gold
python -m app.graph.analysis gold leaderboard dataset=ds-kaveri split=3-hop metric=metric-em
pytest tests/test_analysis.py -q
python -m app.graph.ingest --workspace demo ../corpus/pdf                          # PDFs -> graph, no LLM
python -m app.eval_extraction --workspace demo                                     # scorecard vs gold graph
python -m app.graph.ingest --workspace baseline --keyword-intents ../corpus/pdf    # + keyword intent baseline
python -m app.eval_extraction --workspace baseline
python -m uvicorn app.api.main:app --port 8000                                     # Run the API (from backend/)

cd ..\frontend
npm install
npm run dev                                # http://localhost:5173
```

UI: in a second terminal, `cd frontend` then `npm run dev`, and open http://localhost:5173 (the API must be
running on port 8000).

The analysis CLI takes the workspace name (`gold`), not the graph name (`ws_gold`); the `ws_` prefix is added for you.

## Demo questions
Example questions to ask, with the graph path and source passages each one returns.

## Dataset statement
Where the corpus comes from (synthetic or open-access) and the terms under which it is used.

## AI assistance
Disclosed under hackathon rule 11.

- The project was planned and built with Claude.
- The synthetic research corpus (papers, ground truth) was generated with Claude.
- The code was written with Claude Code.
- I reviewed every file and can explain how each part works and why it is built that way.
