# GraphMind Research --- Build and Technical Guide

**Graph Hacks · FalkorDB × WeMakeDevs · October 2026**

GraphMind Research is a research-paper exploration tool. It turns a
collection of papers into a connected graph so users can investigate
citations, methods, datasets, reported results, and relationships
between findings. It combines graph queries with semantic retrieval to
help users explore a question and trace the supporting evidence.

This guide explains the problem, design choices, data model, local
setup, and checks used to validate the project. It is written as a
practical guide to the implementation---not as a prompt log or a list of
AI-generated code fragments.

## 1. The problem

A folder of research PDFs is useful for reading individual papers, but
it is difficult to answer questions that span a whole collection:

-   Which papers build on the same method?
-   Which papers evaluate methods on the same dataset and metric?
-   Do later papers reproduce, correct, or challenge earlier results?
-   Is a reported number outdated because a correction was published?
-   Which relevant papers might deserve a closer look?
-   What evidence supports an answer?

A conventional document chatbot usually retrieves passages that resemble
the question. That can be useful, but it does not automatically
represent relationships across several papers or make numerical
comparisons consistent.

GraphMind Research represents the entities and their connections
explicitly. This lets the application query the relationships and then
use relevant passages as evidence.

## 2. What the application does

The project is designed around four main tasks:

1.  **Build a paper library.** Read PDFs and identify paper metadata,
    authors, references, methods, datasets, and reported results.
2.  **Represent relationships.** Store papers and related research
    entities in FalkorDB, connected by typed relationships.
3.  **Retrieve supporting passages.** Index selected paper text in
    ChromaDB so relevant evidence can be retrieved for a question.
4.  **Explore the library through an API and UI.** The FastAPI backend
    exposes workspace and research endpoints, while the React frontend
    provides the user-facing interface.

The current demo corpus contains 12 synthetic research papers. The
papers, authors, institutions, datasets, and reported numbers are
fictional. The fixtures under `ground_truth/` are reference data for
evaluation; they must not be described as facts extracted from the PDFs.

### Example questions

-   How are two papers connected?
-   Which methods are compared on a given dataset and split?
-   What is the lineage of a method?
-   Which results have a correction?
-   What evidence in the papers is relevant to a research question?

The answers depend on what is present in the selected workspace and what
the implemented queries can retrieve. A result from the synthetic corpus
is a demonstration of the workflow, not evidence about real-world
research.

## 3. Architecture

``` mermaid
flowchart TD
    A[Research paper PDFs] --> B[FastAPI ingestion pipeline]
    B --> C[Parse and normalise paper information]
    C --> D[(FalkorDB)]
    A --> E[Extract useful text passages]
    E --> F[Ollama embeddings]
    F --> G[(ChromaDB)]
    H[User question] --> I[React frontend]
    I --> J[FastAPI research API]
    J --> D
    J --> G
    D --> K[Graph facts and relationships]
    G --> L[Relevant text evidence]
    K --> M[Combine retrieved context]
    L --> M
    M --> N[Local Ollama language model]
    N --> O[Answer and supporting evidence]
    O --> I
```

The diagram shows the intended data flow at a high level. The code in
`backend/app/` is the source of truth for the exact behaviour of each
endpoint and pipeline stage.

### Why use both a graph and a vector store?

**FalkorDB** stores the structured research entities and their
relationships. It supports queries such as finding connected papers,
tracing method lineage, or joining results through methods, datasets,
and metrics.

**ChromaDB** stores vector representations of text chunks. It helps
locate passages that are semantically relevant to a question.

These components solve different problems: graph traversal finds
explicit connections, while semantic retrieval helps find supporting
text. The project uses Ollama locally for the configured language and
embedding models, avoiding a required paid model API for local use.

## 4. Graph model

The model separates entities that have different meanings and
relationships.

### Main node labels

      -----------------------------------------------------------------------
      Node                                Purpose
      ----------------------------------- -----------------------------------
      `Paper`                             A research paper, including its
                                          metadata and library status
    
      `Author`                            A paper author
    
      `Institution`                       An affiliation
    
      `Venue`                             A publication venue
    
      `Method`                            A method or approach proposed or
                                          used by a paper
    
      `Dataset`                           A dataset used or introduced in the
                                          research
    
      `Task` / `Metric`                   The task being studied and the
                                          metric used to evaluate it
    
      `Result`                            A reported value with its method,
                                          dataset, metric, split, and origin
    
      `Claim`                             A finding or statement associated
                                          with a paper
    
      `Job`                               The state of a pipeline task, where
                                          used by the running implementation
    
      `ResearchSession` / `Question` /    Research-session and saved-insight
      `Insight`                           data, where used by the running
                                          implementation
      -----------------------------------------------------------------------

### Important relationships

      -----------------------------------------------------------------------
      Relationship                        Meaning
      ----------------------------------- -----------------------------------
      `WROTE`                             Connects an author to a paper
    
      `CITES`                             Connects a citing paper to the
                                          paper it references
    
      `PROPOSES` / `USES`                 Records a paper's relationship to a
                                          method
    
      `INTRODUCES` / `EVALUATES_ON`       Connects papers to datasets
    
      `REPORTS`                           Connects a paper to a reported
                                          result
    
      `OF_METHOD` / `ON_DATASET` /        Describes the method, dataset, and
      `MEASURED_BY`                       metric associated with a result
    
      `EXTENDS`                           Represents a method lineage
                                          relationship
    
      `CORRECTS` / `REPRODUCES`           Represents a correction or
                                          reproduction relationship
    
      `MAKES` / `ABOUT`                   Connects a paper to a claim and the
                                          entity it concerns
    
      `SUPPORTS` / `CONTRADICTS` /        Represents a relationship between
      `QUALIFIES`                         claims, when established by the
                                          pipeline
      -----------------------------------------------------------------------

The exact properties and direction conventions are documented in
`docs/DATA_MODEL.md` and `docs/CYPHER.md`. Check those files alongside
the query definitions in `backend/app/graph/analysis.py`.

### Why is `Result` a node?

A reported number is connected to more than one thing. For example, a
result can be associated with a method, dataset, metric, source paper,
and correction. Making `Result` a node allows those connections to be
queried directly. It also supports comparisons across papers without
treating every number as an isolated property of a paper.

## 5. Ingestion and retrieval

At a high level, the ingestion workflow is:

1.  Read the PDF and extract text and paper information.
2.  Normalise paper identifiers and resolve references where possible.
3.  Write the extracted entities and relationships to the selected
    FalkorDB workspace.
4.  When indexing is enabled, split relevant paper text into passages,
    create embeddings through Ollama, and store the passages in the
    workspace's ChromaDB collection.
5.  Use graph queries and passage retrieval to support later questions.

Paper parsing is imperfect, especially when PDFs have unusual layouts,
tables, or reference formats. The synthetic corpus is deliberately
controlled for the demo. Results on this corpus should not be
interpreted as proof that the parser handles every real-world paper
correctly.

### Workspace separation

The application maps a workspace name to a FalkorDB graph such as
`ws_demo`; the document index uses a corresponding collection such as
`papers_demo`. Use separate workspace names when testing different
ingestions.

**Important:** the oracle/gold loader clears the graph it loads into. Do
not run it against a workspace containing data you want to keep. Treat
`ground_truth/` as evaluation fixtures, not as extracted output.

## 6. Technology choices

      Component                 Role
      ------------------------- ---------------------------------------------------------
      Python                    Ingestion and backend logic
      FastAPI                   HTTP API and health endpoint
      FalkorDB                  Primary graph database
      ChromaDB                  Semantic passage index
      Ollama                    Local language model and embedding model runtime
      LangGraph                 Workflow orchestration where used by the research agent
      React, Vite, TypeScript   Frontend
      Docker Compose            Local FalkorDB service
      PyMuPDF                   PDF text extraction

The configured local models are `llama3.2:latest` and
`nomic-embed-text`. The application requires the models to be available
in Ollama for the configured LLM and embedding features.

## 7. Run locally on Windows

These steps are for a local development setup. They do not mean the
application is publicly deployed.

### Prerequisites

Install:

-   Git
-   Python 3.12.x
-   Node.js LTS and npm
-   Docker Desktop
-   Ollama

Make sure Docker Desktop and Ollama are running before starting the
backend.

### 7.1 Clone the repository

Open PowerShell:

``` powershell
git clone https://github.com/16ajoop/graphmind-research.git
cd graphmind-research
```

### 7.2 Start FalkorDB

From the repository root:

``` powershell
docker compose up -d falkordb
docker ps
```

The local service uses port `6379` for the database and port `3000` for
the browser interface. Keep the database port private; do not expose it
publicly for a demo.

### 7.3 Prepare Ollama models

``` powershell
ollama pull llama3.2:latest
ollama pull nomic-embed-text
ollama list
```

The model downloads are required only if the models are not already
present on the machine.

### 7.4 Configure and install the backend

``` powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

If PowerShell blocks virtual-environment activation, use the Python
executable directly from `.venv\Scripts\python.exe` or follow the local
PowerShell execution-policy guidance for your machine.

Check `backend/.env.example` for supported configuration names. Keep
real secrets and machine-specific `.env` values out of Git.

### 7.5 Ingest the demo corpus

Run from the `backend` directory:

``` powershell
python -m app.graph.ingest --workspace demo --index --keyword-intents ..\corpus\pdf
```

This command creates or updates the `demo` workspace and indexes text
passages. Use a different workspace name if you want to preserve an
existing demo graph.

The number of nodes, relationships, parsed fields, and indexed passages
can differ if the code or corpus changes. Record the output from your
own run instead of copying counts from `ground_truth/gold_graph.json`.

### 7.6 Start the backend API

Still inside `backend`, run:

``` powershell
python -m uvicorn app.api.main:app --host 127.0.0.1 --port 8000
```

Leave this terminal running. In a second PowerShell window, check the
health endpoint:

``` powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health |
    ConvertTo-Json -Depth 5
```

The local verification run returned `falkordb: true` and `ollama: true`.
Your own result may differ if either service is stopped or a model is
missing.

You can inspect the API routes at:

`http://127.0.0.1:8000/docs`

### 7.7 Start the frontend

Open another PowerShell window at the repository root:

``` powershell
cd frontend
npm install
npm run dev
```

Open the local URL printed by Vite. Keep the backend, FalkorDB, and
Ollama running while testing the frontend.

## 8. Validation and testing

Use the checks below to verify the parts that are running on your
machine.

### Service health

``` powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health |
    ConvertTo-Json -Depth 5
```

### Workspaces

``` powershell
Invoke-RestMethod http://127.0.0.1:8000/api/workspaces |
    ConvertTo-Json -Depth 4
```

### Frontend production build

From `frontend/`:

``` powershell
npm run build
```

A successful build verifies that Vite can compile the frontend. It does
not, by itself, verify that every backend endpoint or user flow works.

### Tests

Run the tests available in the repository from the backend environment:

``` powershell
pytest -v
```

Report the actual test result from the current repository state. Do not
describe planned tests, mocked tests, oracle-mode checks, or
synthetic-corpus checks as proof of accuracy on real research papers.

### Keep evidence of your own run

For a reliable demo, keep a short record of:

-   the command used for ingestion;
-   the workspace name;
-   the counts printed by the ingestion run;
-   the health endpoint output;
-   the tests actually run and their result;
-   one or two questions tested in the UI, with the evidence returned.

This makes it easier to reproduce the demo and answer technical
questions accurately.

## 9. Example Cypher patterns

The repository's canonical queries are in
`backend/app/graph/analysis.py` and are documented in `docs/CYPHER.md`.
These small examples illustrate the graph model; they are not a
substitute for checking the production query definitions.

### Follow a paper's outgoing citations

``` cypher
MATCH (p:Paper {id: $paper_id})-[c:CITES]->(cited:Paper)
RETURN p.title AS citing_paper,
       cited.title AS cited_paper,
       c.intent AS citation_intent
```

### Find a method's extension lineage

``` cypher
MATCH path =
  (m:Method {name: $method_name})-[:EXTENDS*1..5]->(parent:Method)
RETURN [node IN nodes(path) | node.name] AS lineage
```

### Compare results by dataset and metric

A leaderboard query needs to connect `Result` to its method, dataset,
metric, and source paper. It should also account for corrections when
the data model contains them. Use the parameterised `leaderboard` query
in `analysis.py` for the application's actual behaviour.

Always parameterise user-supplied values. Do not build Cypher by
concatenating a user's question into the query text.

## 10. Demo walkthrough

A short judge walkthrough should show a real, reproducible flow:

1.  Show the application and explain the problem in one sentence.
2.  Show the selected workspace and the papers available in it.
3.  Ask one question that the current implementation can answer.
4.  Open the returned graph relationship or evidence passage, and
    explain why it supports the answer.
5.  Show the health endpoint or a relevant query only if it helps
    demonstrate the role of FalkorDB.
6.  Briefly state the limitations of the synthetic corpus and what would
    be needed for use with a broader collection of real papers.

Do not use the gold/oracle graph as if it had been built from PDF
extraction. If you demonstrate oracle mode, label it clearly as a test
fixture.

## 11. Known limitations and next steps

-   The included research corpus is synthetic and small.
-   PDF parsing can miss metadata or misread tables and references.
-   Semantic retrieval quality depends on the indexed passages and the
    embedding model.
-   Language-model output should be checked against retrieved facts and
    source passages.
-   A successful local run does not imply a public deployment; the local
    services need a deployment plan before they can be accessed from the
    internet.
-   Real-world use would require broader evaluation on permitted
    research papers, better handling of varied PDF layouts, and a
    documented process for checking extraction errors.

## 12. AI assistance and project responsibility

AI tools were used during development to assist with parts of the
synthetic test corpus and reference fixtures, implementation work,
debugging, and documentation. I reviewed and ran the project locally,
checked the ingestion output and API health, and am responsible for
understanding the code and explaining the design decisions and
limitations.

The AI disclosure does not replace a technical explanation. During
judging, I should be able to explain the graph schema, why FalkorDB is
central, how the ingestion pipeline works, how graph queries differ from
vector retrieval, and what I personally verified.

## 13. Useful project files

      -----------------------------------------------------------------------
      File or directory                   What to look at
      ----------------------------------- -----------------------------------
      `backend/app/api/main.py`           API setup and routes
    
      `backend/app/graph/ingest.py`       PDF ingestion workflow and CLI
    
      `backend/app/graph/analysis.py`     Parameterised graph analysis
                                          queries
    
      `backend/app/graph/client.py`       FalkorDB connection and workspace
                                          naming
    
      `backend/app/config.py`             Environment configuration
    
      `backend/.env.example`              Local configuration template
    
      `docs/DATA_MODEL.md`                Graph labels, properties, and
                                          relationships
    
      `docs/CYPHER.md`                    Documented graph queries
    
      `docs/EVALUATION.md`                Evaluation notes available in the
                                          repository
    
      `ground_truth/`                     Synthetic-corpus reference
                                          fixtures; not extracted output
    
      `corpus/pdf/`                       Demo PDF collection
      -----------------------------------------------------------------------
    
    ------------------------------------------------------------------------


**Project:** GraphMind Research\
**Repository:** https://github.com/16ajoop/graphmind-research
