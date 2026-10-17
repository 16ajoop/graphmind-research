# AI assistance

The Graph Hacks rules allow AI coding assistants when their use is disclosed (rule 11). This page says which
assistants were used, for what, and where to find every instruction they were given.

## Assistants used

- **Claude (Anthropic), in the Claude app.** Discussed the idea and the graph model; wrote the step-by-step
  instruction files, each with the full code and the reasoning behind it; tested that code against FalkorDB in its own
  sandbox before handing it over; generated the synthetic paper corpus and its ground-truth graph; drew the
  architecture diagram; drafted the README.
- **Claude Code.** Applied each instruction file to this repository on my machine, ran the tests and checks it asked
  for, explained what it changed, and made the commits I asked for.

## What I did

<!-- Edit this list so it says, in your own words, exactly what you did. -->

- Chose the problem (finding relationships between research papers, after first trying a company-knowledge agent on
  15 October) and the two tracks.
- Set the constraints the code had to follow: FalkorDB as the only database (no SQLite), no secrets in git, one step
  at a time, commit only after I had checked a step.
- Ran every step on my own machine (Windows, FalkorDB in Docker, Ollama), ran the measurements in `EVALUATION.md`, and
  reported failures and results back, which decided what was built or fixed next.
- Reviewed each step before committing it. I can explain the graph model, the queries, the agents and the technical
  decisions (rule 12).

## The instruction files

[`prompts/`](prompts/) holds the instruction files in the order they were used: `stepNN-<topic>.md` is exactly what
Claude Code was given for step NN, and the commit after it is the result. Each file explains why the step is built the way it
is, so it doubles as a design log.

## AI inside the product

Separate from the coding assistance, the running product uses two local models through Ollama:

- **llama3.2** picks each paper's main claim from its own sentences, judges how claim pairs the graph selected relate,
  can label citation intents (off by default: graph rules and cue words measured better), and writes the final answer
  from the numbered facts.
- **nomic-embed-text** embeds passages for ChromaDB and method sections for `SIMILAR_TO`.

Neither model writes Cypher or decides anything the graph can decide by itself.
