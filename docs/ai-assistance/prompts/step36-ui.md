# Step 36: the web UI (React)

Save as `docs/prompts/step36.md` and tell Claude Code: "Do docs/prompts/step36.md".
Tested against the real Step 35 API on FalkorDB 6.0.1, with the `gold` workspace and a workspace filled live by uploading
the 12 PDFs. The checks were `npm run build` (clean), `npm run lint` (0 errors), headless-browser runs of every page, and
stopping and starting FalkorDB during a run. Backend `pytest -q`: still 58 passed.

## What you get

| Page | What it shows | API |
|---|---|---|
| Library | Drop PDFs; a live board of the four agents working on each paper; the citation map (papers in year rows, citations coloured by intent); the list of papers | `POST papers`, `GET jobs` (every second while busy), `GET graph/library`, `GET papers` |
| Ask | Chat with the research agent. Each step streams in while it runs; numbered facts link to their graph query and the Cypher behind it; highlighted passages from the PDFs; "Save as insight" | `POST sessions/{sid}/ask` (server-sent events), `POST insights` |
| Compare papers | Everything connecting two papers: citation and intent, shared authors/datasets/methods, lineage, claim relations, re-runs | `GET pair` |
| Leaderboards | One number per method; erratum corrections, reproductions and quotes beside it | `GET leaderboard/options`, `GET leaderboard` |
| Disagreements | State-of-the-art claims the numbers contradict; claims that contradict, qualify or support each other | `GET claims` |
| Citation check | Probably missing citations (with the score's reasons), citations of corrected papers, much-cited outside papers | `GET citations` |
| Research gaps | Methods never tested on a dataset, results nobody reproduced, missing metrics, shallow datasets | `GET gaps` |
| People | PageRank, betweenness and connected components, computed inside FalkorDB | `GET people` |
| Sessions | Past questions and answers, saved insights, "new since you asked" | `GET sessions`, `GET sessions/{sid}`, `GET whats-new` |

Shared by every page:
- a workspace switcher (with "new workspace");
- service status (FalkorDB, Ollama, agents);
- a red banner whenever FalkorDB is down;
- a paper panel that opens from any paper name anywhere.

## How it looks, and why

The subject is research papers, so the UI looks like a marked-up paper rather than a dark analytics dashboard.

| Token | Hex | Used for |
|---|---|---|
| Vellum | `#f4f6f3` | page background (a cool off-white, not cream) |
| Sheet | `#ffffff` | panels, cards on the map |
| Ink | `#1d2b3a` | text |
| Graphite | `#5b6875` | secondary text |
| Fountain pen | `#2c4bb5` | actions, links, done steps, fact numbers |
| Proofreader red | `#b8322a` | problems only: FalkorDB down, failed jobs, contradicted claims, missing-citation scores |
| Highlighter | `#f6e85c` | the passage from a PDF that backs a fact |

- **Type.** Source Serif 4 is the papers' voice: titles, answers, claims and quotes. Hanken Grotesk is the interface.
  Both are self-hosted from npm (`@fontsource-variable/...`), so the demo needs no font CDN.
- **The two memorable things.**
  - The citation map in year rows, oldest at the top, so every arrow points back in time. Its intent legend doubles
    as a filter.
  - The highlighter on evidence passages. That is where "the graph decides, the LLM judges, the vector store
    explains" becomes visible. Everything else stays quiet.
- **Copy and accessibility.** Sentence case, no all-caps labels, real words for errors ("Waiting for FalkorDB", plus
  what to do). There is a visible keyboard focus, reduced motion is respected, and the layout works at phone width
  (the sidebar becomes a top bar).

## How it works

- **`api.ts`** is every call to the backend, plus the response types.
  - `askStream()` POSTs the question and reads the response body as a stream. It splits the stream on blank lines and
    parses each `data:` line as one event.
  - This replaces `EventSource`, which can only send GET without a body.
  - Each event is one LangGraph node finishing: understand, plan, run_tools, gather_evidence, verify, answer,
    remember. The last event is always `final`.
- **The pipeline board** polls `GET jobs` once a second while any job is unfinished, then stops.
  - Polling fits because the agents coordinate only through Job nodes in FalkorDB. The UI reads those same nodes, so
    no websocket or message bus is needed.
  - Each cell shows the agent that did that stage (from the job's `history`). The running cell is the solid one, and
    "waiting" means the stage waits for the earlier stages of every paper, the wave barrier from Step 33.
  - Each time a paper passes a stage, the map and the list reload.
- **The map** (`LibraryMap.tsx`):
  - dagre lays the graph out top-to-bottom only to get the left-to-right order inside each row, which keeps edge
    crossings low. The publication year then decides the row.
  - Papers that are cited but whose PDF is not added (stubs) share the first row, drawn dashed.
  - Clicking a card opens the paper panel and dims everything not connected to it.
- **Answers** (`AnswerView.tsx`):
  - The API appends "Facts from the graph:" to the answer text, so the UI cuts that part off and shows the facts as
    a list instead.
  - The `[n]` markers become links to fact n. Each fact names the graph query (tool) it came from.
  - The timeline (`StepTimeline.tsx`) lists every query with its rows, time and Cypher.
- **FalkorDB down.**
  - The app polls `/api/health` every 4 seconds. When FalkorDB is down, a banner explains how to start it, and each
    page shows "Waiting for FalkorDB".
  - When it comes back, the page remounts and reloads by itself. This is the "remove FalkorDB" moment for the video.
- **What the browser remembers.** It keeps only the last workspace and session id (`localStorage`), as a per-viewer
  convenience. The real memory (questions, answers, insights) lives in FalkorDB as ResearchSession, Question and
  Insight nodes.

## Three small backend fixes found while testing the UI

1. **`main.py` `falkordb_up()`.**
   - redis-py retries a refused connection with backoff, so every 503 took about 4 seconds.
   - The fix is `retry=Retry(NoBackoff(), 0)`, and now the UI hears "down" at once.
2. **`memory.py` `recall_insights`.**
   - "What did I save earlier?" names no paper, so the query ran with `ids = []` and found nothing. An insight saved
     from an answer without papers (the people question) could never be recalled.
   - Now no ids means every saved insight.
3. **`workflow.py`.** A recalled insight ending in "." was printed with "..".

A test line covers fix 2.

## The prompt for Claude Code

Build the UI in `frontend/` with EXACTLY the code below, and make the three backend edits. Then:

1. In `frontend/`:
   - Run `npm install @fontsource-variable/source-serif-4@5.3.1 @fontsource-variable/hanken-grotesk@5.3.0`.
   - Check that `@xyflow/react`, `@dagrejs/dagre`, `lucide-react` and `react-router-dom` are already in
     package.json (they were added with the scaffold). If one is missing, install it.
2. Create or replace every file listed under "Frontend files". If `src/App.css` or `src/assets/` from the Vite
   template still exist and nothing imports them, delete them.
3. Make the backend edits under "Backend edits" (exact find and replace).
4. Checks:
   - In `frontend/`: `npx tsc -b` (no errors), `npm run build` (succeeds), `npm run lint` (0 errors; a few
     react warnings are fine).
   - In `backend/`: `pytest -q` (58 passed).
5. README: under the run commands, add:
   "UI: in a second terminal, `cd frontend` then `npm run dev`, and open http://localhost:5173 (the API must be
   running on port 8000)."
6. Explain in a few lines:
   - how the Ask page reads the server-sent events with fetch;
   - why the pipeline board polls instead of using a websocket;
   - how the map decides each card's row and position.
7. Do not commit.

## Backend edits

### backend/app/api/main.py: imports

Find:
````python
import httpx
import redis
from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
````
Replace with:
````python
import httpx
import redis
from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from redis.backoff import NoBackoff
from redis.retry import Retry
````

### backend/app/api/main.py: falkordb_up

Find:
````python
def falkordb_up() -> bool:
    try:
        return bool(redis.Redis(host=FALKOR_HOST, port=FALKOR_PORT, socket_connect_timeout=1, socket_timeout=2).ping())
    except redis.exceptions.RedisError:
        return False
````
Replace with:
````python
def falkordb_up() -> bool:
    # No retries: redis-py retries a refused connection with backoff (about 4 s), and the UI should hear "down" at once.
    try:
        return bool(redis.Redis(host=FALKOR_HOST, port=FALKOR_PORT, socket_connect_timeout=1, socket_timeout=2,
                                retry=Retry(NoBackoff(), 0)).ping())
    except redis.exceptions.RedisError:
        return False
````

### backend/app/agent/memory.py: recall_insights

Find the `"recall_insights"` entry in `MEM_Q`:
````python
    "recall_insights": """
        MATCH (i:Insight)-[:ABOUT]->(x) WHERE x.id IN $ids
        MATCH (s:ResearchSession)-[:SAVED]->(i)
        RETURN i.text AS insight, collect(DISTINCT x.id) AS about, s.title AS session, i.saved_at AS saved_at
        ORDER BY saved_at DESC""",
````
Replace with:
````python
    # Insights about any of $ids; with no ids (e.g. "What did I save earlier?") every saved insight.
    "recall_insights": """
        MATCH (s:ResearchSession)-[:SAVED]->(i:Insight)
        OPTIONAL MATCH (i)-[:ABOUT]->(x)
        WITH s, i, collect(DISTINCT x.id) AS about
        WHERE size($ids) = 0 OR any(a IN about WHERE a IN $ids)
        RETURN i.text AS insight, about, s.title AS session, i.saved_at AS saved_at
        ORDER BY saved_at DESC""",
````

### backend/app/agent/workflow.py: in facts_from

Find:
````python
            add(f"Saved insight ({r['session']}): {r['insight']}.")
````
Replace with:
````python
            add(f"Saved insight ({r['session']}): {r['insight'].rstrip('.')}.")
````

### backend/tests/test_workflow.py: at the end of test_every_query_is_logged_with_its_cypher_and_questions_are_remembered

Find:
````python
    s = workflow.ask(g, "What did I save earlier about HopLens?", session_id=session, use_llm=False)
    assert s["intent"] == "recall" and any("HopLens missed GraphFuse" in f for f in facts(s))
````
Replace with:
````python
    s = workflow.ask(g, "What did I save earlier about HopLens?", session_id=session, use_llm=False)
    assert s["intent"] == "recall" and any("HopLens missed GraphFuse" in f for f in facts(s))
    s = workflow.ask(g, "What did I save earlier?", session_id=session, use_llm=False)   # no names: every insight
    assert any("HopLens missed GraphFuse" in f for f in facts(s))
````

## Frontend files

| File | |
|---|---|
| `frontend/vite.config.ts` | replace |
| `frontend/src/main.tsx` | replace |
| `frontend/src/index.css` | replace |
| `frontend/src/api.ts` | new |
| `frontend/src/intents.ts` | new |
| `frontend/src/format.ts` | new |
| `frontend/src/workspace.tsx` | new |
| `frontend/src/ui.tsx` | new |
| `frontend/src/App.tsx` | replace |
| `frontend/src/components/PaperPanel.tsx` | new |
| `frontend/src/components/LibraryMap.tsx` | new |
| `frontend/src/components/PipelineBoard.tsx` | new |
| `frontend/src/components/StepTimeline.tsx` | new |
| `frontend/src/components/AnswerView.tsx` | new |
| `frontend/src/pages/Library.tsx` | new |
| `frontend/src/pages/Ask.tsx` | new |
| `frontend/src/pages/Compare.tsx` | new |
| `frontend/src/pages/Leaderboards.tsx` | new |
| `frontend/src/pages/Disagreements.tsx` | new |
| `frontend/src/pages/CitationCheck.tsx` | new |
| `frontend/src/pages/Gaps.tsx` | new |
| `frontend/src/pages/People.tsx` | new |
| `frontend/src/pages/Sessions.tsx` | new |

### frontend/vite.config.ts

````ts
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The UI only talks to "/api/...". In development Vite forwards those requests to FastAPI on :8000,
// so the browser sees one origin and no CORS setup is needed. 127.0.0.1, not localhost: on Windows
// localhost can resolve to IPv6 (::1) while uvicorn listens on IPv4 only.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: { chunkSizeWarningLimit: 900 },     // one bundle with React Flow is ~560 kB; fine for a local app
  server: {
    port: 5173,
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
})
````

### frontend/src/main.tsx

````tsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import './index.css'
import App from './App.tsx'
import { WorkspaceProvider } from './workspace.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <WorkspaceProvider>
        <App />
      </WorkspaceProvider>
    </BrowserRouter>
  </StrictMode>,
)
````

### frontend/src/index.css

````css
@import "tailwindcss";
@import "@fontsource-variable/source-serif-4/opsz.css";
@import "@fontsource-variable/hanken-grotesk/index.css";
@import "@xyflow/react/dist/style.css";

/* GraphMind's palette: a marked-up paper. Ink on vellum, a fountain pen for actions,
   a proofreader's red for problems, a highlighter for the passages that back an answer. */
@theme {
  --color-vellum: #f4f6f3;
  --color-sheet: #ffffff;
  --color-ink: #1d2b3a;
  --color-graphite: #5b6875;
  --color-rule: #d9ded8;
  --color-pen: #2c4bb5;
  --color-pen-soft: #e6eafa;
  --color-proof: #b8322a;
  --color-proof-soft: #f8e5e3;
  --color-highlight: #f6e85c;

  --font-serif: "Source Serif 4 Variable", Georgia, serif;
  --font-sans: "Hanken Grotesk Variable", "Segoe UI", system-ui, sans-serif;
  --font-mono: "Cascadia Code", Consolas, ui-monospace, monospace;
}

@layer base {
  html {
    font-family: var(--font-sans);
    font-size: 15px;
    color: var(--color-ink);
    background: var(--color-vellum);
  }
  h1, h2, h3 {
    font-family: var(--font-serif);
    font-weight: 600;
    letter-spacing: -0.01em;
  }
  :focus-visible {
    outline: 2px solid var(--color-pen);
    outline-offset: 2px;
  }
  button:not(:disabled), [role="button"] {
    cursor: pointer;
  }
}

/* An evidence passage: the words a fact rests on, marked as if with a highlighter. */
.highlighted {
  background: linear-gradient(transparent 12%, color-mix(in srgb, var(--color-highlight) 70%, transparent) 12%,
    color-mix(in srgb, var(--color-highlight) 70%, transparent) 88%, transparent 88%);
  box-decoration-break: clone;
  -webkit-box-decoration-break: clone;
  padding: 0 0.15em;
}

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration: 0.01ms !important; transition-duration: 0.01ms !important; }
}
````

### frontend/src/api.ts

````ts
// Every call the UI makes to the FastAPI backend (backend/app/api/main.py). Vite forwards /api to :8000.

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let r: Response
  try {
    r = await fetch(`/api${path}`, init)
  } catch {
    throw new ApiError(0, 'The API is not running. Start it in backend/: uvicorn app.api.main:app --port 8000')
  }
  if (!r.ok) {
    let detail = r.statusText
    try {
      detail = (await r.json()).detail ?? detail
    } catch {
      /* the body was not JSON: keep the status text */
    }
    throw new ApiError(r.status, typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  return r.json() as Promise<T>
}

const json = (body: unknown): RequestInit => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

const q = (params: Record<string, string>) => new URLSearchParams(params).toString()

// ---------------------------------------------------------------- types (the shapes main.py returns)
export type Health = { falkordb: boolean; ollama: boolean; agents: string[] }

export type Job = {
  id: string; file: string; title: string | null; stage: string; status: 'ready' | 'running' | 'done' | 'failed'
  agent: string | null; attempts: number; history: string[]; error: string | null; created_at: number
}

export type PaperRow = { id: string; title: string; year: number; published: string; authors: string[] }

export type Citation = { id: string; title: string; in_library?: boolean; intent: string; contexts: string[] | null }
export type Claim = { id: string; text: string; type: string; about: string[] }
export type Result = {
  method: string; dataset: string; split: string; metric: string; value: number; origin: string; setting: string | null
}
export type PaperDetail = {
  id: string; title: string; year: number; published: string; abstract: string | null; in_library: boolean
  authors: string[]; cites: Citation[]; cited_by: Citation[]; claims: Claim[]; results: Result[]
}

export type LibraryGraph = {
  nodes: { id: string; title: string; year: number | null; in_library: boolean }[]
  edges: { source: string; target: string; intent: string }[]
}

export type Entity = { id: string; label: string; name: string }

export type BoardOption = {
  dataset: string; dataset_name: string; split: string; metric: string; metric_name: string; results: number
}
export type BoardRow = {
  method: string; value: number; paper: string; corrected: boolean; as_published: number; spread: number
  other_runs: { value: number; origin: string; setting: string | null; paper: string }[]
}

export type Pair = {
  citations: { citing: string; cited: string; intent: string; contexts: string[] | null }[]
  shared_authors: { authors: string[] } | null
  shared_datasets: { datasets: string[] } | null
  shared_methods: { methods: string[] } | null
  lineage: { chain: string[] }[]
  claims: { from_claim: string; relation: string; to_claim: string; basis: string; claim_a: string; claim_b: string }[]
  result_links: { relation: string; method: string; split: string; new_value: number; original_value: number; setting: string | null }[]
  quotes: { method: string; dataset: string; split: string; value: number }[]
}

export type Claims = {
  conflicts: { relation: string; claim: string; text: string; paper: string; other_claim: string; other_text: string; other_paper: string; basis: string }[]
  support: { claim: string; paper: string; supported_claim: string; supported_paper: string; basis: string }[]
  sota: { claim: string; paper: string; dataset: string; split: string; claimed_value: number; better_method: string; better_value: number; better_paper: string }[]
  conflicts_with_results: { claim: string; text: string; paper: string; method: string; dataset: string; split: string; value: number; basis: string }[]
}

export type Citations = {
  missing: { paper: string; title: string; shared_datasets: string[]; similar_methods: string[]; stronger_results: string[]; score: number; citing: string; citing_title: string }[]
  stale: { paper: string; cites: string; correction: string; contexts: string[] | null }[]
  external_hubs: { id: string; title: string; year: number | null; cited_by: string[] }[]
}

export type Gaps = {
  gap_method_dataset: { method: string; never_evaluated_on: string[]; evaluated_on: string[] }[]
  gap_metric_coverage: { metric: string; never_reported_on: string[] }[]
  gap_dataset_depth: { dataset: string; language: string | null; splits: string[] }[]
  gap_unreproduced: { method: string; paper: string }[]
  gap_task_without_method: { task: string; external_methods: string[]; claims: string[] }[]
}

export type People = {
  influential: { id: string; title: string; in_library: boolean; score: number }[]
  bridges: { author: string; score: number }[]
  groups: { componentId: number; authors: string[] }[]
}

export type Session = { id: string; title: string; started_at: number; questions: number }
export type Fact = { n: number; text: string; papers: string[]; tool: string }
export type Passage = { paper: string; section: string; excerpt: string }
export type Answer = { answer: string; source?: string; facts: Fact[]; evidence: Record<string, Passage[]> }
export type HistoryItem = { id: string; question: string; intent: string; asked_at: number; answer: Answer }
export type Insight = { id: string; text: string; saved_at: number; about: string[] }
export type WhatsNew = { paper_id: string; paper: string; relation: string; topic: string; earlier_question: string }

export type ToolCall = { tool: string; params: Record<string, unknown>; rows: number; ms: number; cypher: Record<string, string> }
export type StepEvent =
  | { step: 'understand'; intent: string; decided_by: string; entities: string[] }
  | { step: 'clarify'; [k: string]: unknown }
  | { step: 'plan'; tools: string[] }
  | { step: 'run_tools'; round: number; tool_log: ToolCall[] }
  | { step: 'gather_evidence'; facts: number; passages: number }
  | { step: 'verify'; gaps: string[]; notes: string[]; extra_tools: string[] }
  | { step: 'answer'; source: string }
  | { step: 'remember'; saved: boolean; question_id: string }
  | ({ step: 'final' } & Answer)
  | { step: 'error'; detail: string }

// ---------------------------------------------------------------- calls
const ws = (name: string) => `/workspaces/${encodeURIComponent(name)}`

export const api = {
  health: async (): Promise<Health> => {
    const r = await fetch('/api/health').catch(() => null)
    if (!r) return { falkordb: false, ollama: false, agents: [] }
    return r.json()
  },
  workspaces: () => request<string[]>('/workspaces'),
  createWorkspace: (name: string) => request<{ name: string }>('/workspaces', json({ name })),

  upload: (w: string, files: File[]) => {
    const form = new FormData()
    files.forEach((f) => form.append('files', f))
    return request<{ jobs: string[] }>(`${ws(w)}/papers`, { method: 'POST', body: form })
  },
  jobs: (w: string) => request<Job[]>(`${ws(w)}/jobs`),
  papers: (w: string) => request<PaperRow[]>(`${ws(w)}/papers`),
  paper: (w: string, id: string) => request<PaperDetail>(`${ws(w)}/papers/${encodeURIComponent(id)}`),
  libraryGraph: (w: string) => request<LibraryGraph>(`${ws(w)}/graph/library`),
  entities: (w: string) => request<Entity[]>(`${ws(w)}/entities`),

  boardOptions: (w: string) => request<BoardOption[]>(`${ws(w)}/leaderboard/options`),
  board: (w: string, dataset: string, split: string, metric: string) =>
    request<BoardRow[]>(`${ws(w)}/leaderboard?${q({ dataset, split, metric })}`),
  pair: (w: string, a: string, b: string) => request<Pair>(`${ws(w)}/pair?${q({ a, b })}`),
  claims: (w: string) => request<Claims>(`${ws(w)}/claims`),
  citations: (w: string) => request<Citations>(`${ws(w)}/citations`),
  gaps: (w: string) => request<Gaps>(`${ws(w)}/gaps`),
  people: (w: string) => request<People>(`${ws(w)}/people`),

  sessions: (w: string) => request<Session[]>(`${ws(w)}/sessions`),
  newSession: (w: string, title: string) => request<{ id: string }>(`${ws(w)}/sessions`, json({ title })),
  session: (w: string, sid: string) => request<{ history: HistoryItem[]; insights: Insight[] }>(`${ws(w)}/sessions/${sid}`),
  saveInsight: (w: string, sid: string, text: string, about: string[]) =>
    request<{ id: string }>(`${ws(w)}/sessions/${sid}/insights`, json({ text, about })),
  whatsNew: (w: string, sid: string) => request<WhatsNew[]>(`${ws(w)}/sessions/${sid}/whats-new`),
}

/** POST a question and call onEvent for every server-sent event, as each agent step finishes.
 *  EventSource only does GET, so this reads the response body stream and splits it on blank lines. */
export async function askStream(w: string, sid: string, question: string, onEvent: (e: StepEvent) => void,
                                signal?: AbortSignal): Promise<void> {
  let r: Response
  try {
    r = await fetch(`/api${ws(w)}/sessions/${sid}/ask`, { ...json({ question }), signal })
  } catch (e) {
    if ((e as Error).name === 'AbortError') return
    throw new ApiError(0, 'The API is not running. Start it in backend/: uvicorn app.api.main:app --port 8000')
  }
  if (!r.ok || !r.body) {
    let detail = r.statusText
    try { detail = (await r.json()).detail ?? detail } catch { /* not JSON */ }
    throw new ApiError(r.status, detail)
  }
  const reader = r.body.pipeThrough(new TextDecoderStream()).getReader()
  let buffer = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += value
    let cut: number
    while ((cut = buffer.indexOf('\n\n')) >= 0) {
      const block = buffer.slice(0, cut)
      buffer = buffer.slice(cut + 2)
      for (const line of block.split('\n')) {
        if (line.startsWith('data: ')) onEvent(JSON.parse(line.slice(6)) as StepEvent)
      }
    }
  }
}
````

### frontend/src/intents.ts

````ts
// Citation intents from ontology.json, each with its own ink colour on the map and in tags.
// The colours are chosen so that the two "something is wrong" intents (criticizes, corrects) are the warm ones.
export const INTENTS: Record<string, { label: string; color: string; meaning: string }> = {
  extends: { label: 'extends', color: '#2c4bb5', meaning: 'builds directly on the cited method' },
  reproduces: { label: 'reproduces', color: '#0f7f74', meaning: 're-runs the cited work to check its results' },
  compares_against: { label: 'compares against', color: '#b7791f', meaning: 'reports the cited work as a baseline' },
  uses_method: { label: 'uses method', color: '#5b8fd6', meaning: 'uses the cited method as a component' },
  uses_dataset: { label: 'uses dataset', color: '#7a5bc7', meaning: 'evaluates on a dataset the cited work introduced' },
  supports: { label: 'supports', color: '#3f8a3a', meaning: 'presents evidence agreeing with the cited work' },
  criticizes: { label: 'criticizes', color: '#b8322a', meaning: 'argues the cited work is wrong or limited' },
  corrects: { label: 'corrects', color: '#a8327e', meaning: 'erratum or correction of the cited work' },
  background: { label: 'background', color: '#9aa3ab', meaning: 'general context only' },
}

const UNKNOWN = { label: 'not labelled yet', color: '#c4c9cf', meaning: 'the extractor has not labelled this citation' }

export const intentOf = (name: string | null | undefined) => INTENTS[name ?? ''] ?? { ...UNKNOWN, label: name || UNKNOWN.label }

/** "GraphFuse: Fusing Dense and Graph Retrieval" -> "GraphFuse" */
export const shortTitle = (title: string | null | undefined, fallback = '') =>
  (title ?? fallback).split(':')[0].trim() || fallback
````

### frontend/src/format.ts

````ts
// Plain text helpers shared by several components.

export const sentence = (s: string) => s.charAt(0).toUpperCase() + s.slice(1)

export function when(ms: number | null | undefined): string {
  if (!ms) return ''
  return new Date(ms).toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
}

/** The API appends the facts, "Also checked" and "Not found" to the answer text; the UI shows those separately. */
export function splitAnswer(text: string) {
  const blocks = text.split('\n\n')
  return {
    prose: blocks.filter((b) => !/^(Facts from the graph:|Also checked:|Not found:)/.test(b)),
    notes: blocks.filter((b) => /^(Also checked:|Not found:)/.test(b)),
  }
}
````

### frontend/src/workspace.tsx

````tsx
// App-wide state: the current workspace, paper titles for showing ids as names, the open paper panel,
// the current research session, and a small data-loading hook every page uses.
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { api, ApiError } from './api'

function remembered(key: string): string | null {
  try { return localStorage.getItem(key) } catch { return null }
}
function remember(key: string, value: string | null) {
  try {
    if (value === null) localStorage.removeItem(key)
    else localStorage.setItem(key, value)
  } catch { /* private window: the choice just isn't remembered */ }
}

type Ctx = {
  ws: string
  setWs: (name: string) => void
  workspaces: string[]
  refreshWorkspaces: () => void
  titles: Record<string, string>          // paper id -> full title, for every paper node (cited-only ones too)
  refreshTitles: () => void
  paperId: string | null                  // the paper shown in the side panel
  openPaper: (id: string | null) => void
  sessionId: string | null                // the research session questions are asked in
  setSessionId: (id: string | null) => void
}

const WorkspaceContext = createContext<Ctx | null>(null)

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const [workspaces, setWorkspaces] = useState<string[]>([])
  const [ws, setWsState] = useState<string>(remembered('gm.workspace') ?? '')
  const [titles, setTitles] = useState<Record<string, string>>({})
  const [paperId, openPaper] = useState<string | null>(null)
  const [sessionId, setSessionState] = useState<string | null>(null)

  const refreshWorkspaces = useCallback(() => {
    api.workspaces().then((names) => {
      setWorkspaces(names)
      setWsState((cur) => (cur && names.includes(cur) ? cur : names.includes('demo') ? 'demo' : names[0] ?? cur))
    }).catch(() => { /* the health banner explains why */ })
  }, [])

  const refreshTitles = useCallback(() => {
    if (!ws) return
    api.libraryGraph(ws)
      .then((g) => setTitles(Object.fromEntries(g.nodes.map((n) => [n.id, n.title]))))
      .catch(() => setTitles({}))
  }, [ws])

  useEffect(refreshWorkspaces, [refreshWorkspaces])
  useEffect(() => {
    remember('gm.workspace', ws || null)
    setSessionState(ws ? remembered(`gm.session.${ws}`) : null)
    openPaper(null)
    refreshTitles()
  }, [ws, refreshTitles])

  const setSessionId = (id: string | null) => {
    setSessionState(id)
    remember(`gm.session.${ws}`, id)
  }

  return (
    <WorkspaceContext.Provider value={{
      ws, setWs: setWsState, workspaces, refreshWorkspaces, titles, refreshTitles,
      paperId, openPaper, sessionId, setSessionId,
    }}>
      {children}
    </WorkspaceContext.Provider>
  )
}

export function useWorkspace(): Ctx {
  const ctx = useContext(WorkspaceContext)
  if (!ctx) throw new Error('useWorkspace outside WorkspaceProvider')
  return ctx
}

type DataState<T> = { data?: T; error?: ApiError; loading: boolean }

/** Load data for a page and reload it when deps change. Pass null to load nothing (e.g. no workspace yet). */
export function useData<T>(load: (() => Promise<T>) | null, deps: unknown[]): DataState<T> & { reload: () => void } {
  const [state, setState] = useState<DataState<T>>({ loading: !!load })
  const [tick, setTick] = useState(0)
  useEffect(() => {
    if (!load) { setState({ loading: false }); return }
    let live = true
    setState((s) => ({ data: s.data, loading: true }))
    load()
      .then((data) => { if (live) setState({ data, loading: false }) })
      .catch((error: ApiError) => { if (live) setState({ error, loading: false }) })
    return () => { live = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick])
  return { ...state, reload: () => setTick((t) => t + 1) }
}
````

### frontend/src/ui.tsx

````tsx
// Small building blocks shared by every page.
import type { ReactNode } from 'react'
import { LoaderCircle, RotateCw } from 'lucide-react'
import { ApiError } from './api'
import { intentOf, shortTitle } from './intents'
import { useWorkspace } from './workspace'

export function Page({ title, intro, actions, children, wide = false }: {
  title: string; intro?: ReactNode; actions?: ReactNode; children: ReactNode; wide?: boolean
}) {
  return (
    <div className={`mx-auto px-5 py-7 md:px-10 md:py-9 ${wide ? 'max-w-[1400px]' : 'max-w-[1100px]'}`}>
      <header className="mb-7 flex flex-wrap items-end justify-between gap-4">
        <div className="max-w-[68ch]">
          <h1 className="text-[2rem] leading-tight">{title}</h1>
          {intro && <p className="mt-2 text-graphite">{intro}</p>}
        </div>
        {actions}
      </header>
      {children}
    </div>
  )
}

/** A titled part of a page. The count, when given, tells the reader how much is below before they read it. */
export function Section({ title, count, note, children }: {
  title: string; count?: number; note?: ReactNode; children: ReactNode
}) {
  return (
    <section className="mb-10">
      <h2 className="flex items-baseline gap-2 border-b border-rule pb-2 text-xl">
        {title}
        {count !== undefined && <span className="font-sans text-sm font-normal text-graphite">{count}</span>}
      </h2>
      {note && <p className="mt-2 max-w-[72ch] text-sm text-graphite">{note}</p>}
      <div className="mt-4">{children}</div>
    </section>
  )
}

export function Loading({ what = 'Loading' }: { what?: string }) {
  return (
    <p className="flex items-center gap-2 py-6 text-graphite" role="status">
      <LoaderCircle size={16} className="animate-spin" /> {what}…
    </p>
  )
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="rounded-md border border-dashed border-rule px-4 py-5 text-graphite">{children}</p>
}

/** Explains a failed request in terms of what to do next. */
export function Problem({ error, retry }: { error: ApiError | undefined; retry?: () => void }) {
  if (!error) return null
  const [title, body] =
    error.status === 503 ? ['Waiting for FalkorDB',
      'This view reads the knowledge graph, so it loads when FalkorDB is back (the banner above says how to start it).']
    : error.status === 0 ? ['The API is not running', 'Start it from the backend folder: uvicorn app.api.main:app --port 8000']
    : error.status === 404 ? ['Nothing here yet', 'This workspace has no graph. Upload papers on the Library page to create it.']
    : ['The request failed', error.message]
  return (
    <div className="rounded-md border border-proof/30 bg-proof-soft px-4 py-3" role="alert">
      <p className="font-semibold text-proof">{title}</p>
      <p className="mt-1 text-sm text-ink">{body}</p>
      {retry && (
        <button onClick={retry} className="mt-3 inline-flex items-center gap-1.5 rounded-md border border-rule bg-sheet px-3 py-1.5 text-sm hover:border-graphite">
          <RotateCw size={14} /> Try again
        </button>
      )}
    </div>
  )
}

/** Wraps a page body: shows loading, the problem, or the content once data is in. */
export function Loaded<T>({ state, children, what }: {
  state: { data?: T; error?: ApiError; loading: boolean; reload: () => void }
  children: (data: T) => ReactNode; what?: string
}) {
  if (state.error) return <Problem error={state.error} retry={state.reload} />
  if (state.data === undefined) return <Loading what={what} />
  return <>{children(state.data)}</>
}

export function IntentTag({ intent }: { intent: string | null | undefined }) {
  const it = intentOf(intent)
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap text-sm" title={it.meaning}>
      <span className="h-2.5 w-2.5 rounded-full" style={{ background: it.color }} aria-hidden />
      {it.label}
    </span>
  )
}

const RELATION_STYLE: Record<string, string> = {
  CONTRADICTS: 'bg-proof-soft text-proof',
  QUALIFIES: 'bg-[#f6eedc] text-[#8a5a12]',
  SUPPORTS: 'bg-[#e4f0e2] text-[#2f6b2b]',
  REPRODUCES: 'bg-[#dff0ee] text-[#0b5f57]',
  FAILS_TO_REPRODUCE: 'bg-proof-soft text-proof',
}

/** A claim relation (CONTRADICTS, QUALIFIES, ...) written in sentence case, coloured by what it means. */
export function Relation({ name }: { name: string }) {
  const words = name.toLowerCase().replaceAll('_', ' ')
  return (
    <span className={`inline-block rounded px-1.5 py-0.5 text-[13px] font-medium ${RELATION_STYLE[name] ?? 'bg-vellum text-graphite'}`}>
      {words.charAt(0).toUpperCase() + words.slice(1)}
    </span>
  )
}

/** A paper id shown as its short title; opens the paper panel. */
export function PaperRef({ id, full = false }: { id: string; full?: boolean }) {
  const { titles, openPaper } = useWorkspace()
  const title = titles[id]
  return (
    <button
      onClick={() => openPaper(id)}
      className="text-left text-pen underline decoration-pen/30 underline-offset-2 hover:decoration-pen"
      title={title ?? id}
    >
      {full ? title ?? id : shortTitle(title, id)}
    </button>
  )
}

export function Chips({ items, empty = 'none' }: { items: string[] | null | undefined; empty?: string }) {
  if (!items?.length) return <span className="text-graphite">{empty}</span>
  return (
    <span className="inline-flex flex-wrap gap-1.5">
      {items.map((x) => (
        <span key={x} className="rounded border border-rule bg-sheet px-1.5 py-0.5 text-[13px]">{x}</span>
      ))}
    </span>
  )
}

/** A quoted sentence from a paper, marked like a highlighter pass. */
export function Quote({ text, source }: { text: string; source?: ReactNode }) {
  return (
    <blockquote className="font-serif text-[15px] leading-relaxed">
      <span className="highlighted">{text}</span>
      {source && <span className="ml-1 font-sans text-sm text-graphite">({source})</span>}
    </blockquote>
  )
}
````

### frontend/src/App.tsx

````tsx
// The app frame: sidebar (workspace, pages, service status), the FalkorDB banner, the pages, and the paper panel.
import { useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react'
import { NavLink, Navigate, Route, Routes } from 'react-router-dom'
import {
  BookOpen, CircleAlert, GitCompareArrows, History, Lightbulb, MessageSquare, Network, Plus, Quote, Trophy, Users,
  type LucideIcon,
} from 'lucide-react'
import { api, type ApiError, type Health } from './api'
import PaperPanel from './components/PaperPanel'
import Ask from './pages/Ask'
import CitationCheck from './pages/CitationCheck'
import Compare from './pages/Compare'
import Disagreements from './pages/Disagreements'
import Gaps from './pages/Gaps'
import Leaderboards from './pages/Leaderboards'
import Library from './pages/Library'
import People from './pages/People'
import Sessions from './pages/Sessions'
import { useWorkspace } from './workspace'

const PAGES: { path: string; label: string; icon: LucideIcon; element: ReactNode }[] = [
  { path: 'library', label: 'Library', icon: BookOpen, element: <Library /> },
  { path: 'ask', label: 'Ask', icon: MessageSquare, element: <Ask /> },
  { path: 'compare', label: 'Compare papers', icon: GitCompareArrows, element: <Compare /> },
  { path: 'leaderboards', label: 'Leaderboards', icon: Trophy, element: <Leaderboards /> },
  { path: 'disagreements', label: 'Disagreements', icon: CircleAlert, element: <Disagreements /> },
  { path: 'citations', label: 'Citation check', icon: Quote, element: <CitationCheck /> },
  { path: 'gaps', label: 'Research gaps', icon: Lightbulb, element: <Gaps /> },
  { path: 'people', label: 'People', icon: Users, element: <People /> },
  { path: 'sessions', label: 'Sessions', icon: History, element: <Sessions /> },
]

/** Polls /api/health. Returns the status and a counter that goes up each time FalkorDB comes back. */
function useHealth(): [Health | null, number] {
  const [health, setHealth] = useState<Health | null>(null)
  const [reconnects, setReconnects] = useState(0)
  const wasDown = useRef(false)
  useEffect(() => {
    let live = true
    const check = () => api.health().then((h) => {
      if (!live) return
      if (h.falkordb && wasDown.current) setReconnects((n) => n + 1)
      wasDown.current = !h.falkordb
      setHealth(h)
    })
    check()
    const timer = setInterval(check, 4000)
    return () => { live = false; clearInterval(timer) }
  }, [])
  return [health, reconnects]
}

function WorkspacePicker() {
  const { ws, setWs, workspaces, refreshWorkspaces } = useWorkspace()
  const [adding, setAdding] = useState(false)
  const [name, setName] = useState('')
  const [error, setError] = useState('')
  const add = async (e: FormEvent) => {
    e.preventDefault()
    try {
      await api.createWorkspace(name.trim())
      refreshWorkspaces()
      setWs(name.trim())
      setAdding(false)
      setName('')
      setError('')
    } catch (err) {
      setError((err as ApiError).message)
    }
  }
  return (
    <div className="px-4">
      <label htmlFor="workspace" className="text-[13px] text-graphite">Workspace</label>
      <div className="mt-1 flex gap-1.5">
        <select id="workspace" value={ws} onChange={(e) => setWs(e.target.value)}
                className="min-w-0 flex-1 rounded-md border border-rule bg-sheet px-2 py-1.5">
          {!workspaces.includes(ws) && <option value={ws}>{ws || 'none yet'}</option>}
          {workspaces.map((w) => <option key={w} value={w}>{w}</option>)}
        </select>
        <button onClick={() => setAdding(!adding)} aria-label="New workspace" aria-expanded={adding}
                className="rounded-md border border-rule bg-sheet px-2 hover:border-graphite">
          <Plus size={16} />
        </button>
      </div>
      {adding && (
        <form onSubmit={add} className="mt-2">
          <label htmlFor="new-ws" className="text-[13px] text-graphite">Name: a to z, 0 to 9 and _</label>
          <div className="mt-1 flex gap-1.5">
            <input id="new-ws" value={name} onChange={(e) => setName(e.target.value.toLowerCase())} pattern="[a-z0-9_]{1,32}" required
                   className="min-w-0 flex-1 rounded-md border border-rule bg-sheet px-2 py-1.5" />
            <button className="rounded-md bg-pen px-2.5 text-sm text-white">Create</button>
          </div>
          {error && <p className="mt-1 text-[13px] text-proof">{error}</p>}
        </form>
      )}
    </div>
  )
}

function Status({ health }: { health: Health | null }) {
  const { ws } = useWorkspace()
  if (!health) return null
  // green: working; red: broken (nothing works without FalkorDB); hollow: optional and off
  const line = (state: 'ok' | 'down' | 'off', text: string) => (
    <li className="flex items-center gap-2">
      <span className={`h-2 w-2 shrink-0 rounded-full ${state === 'ok' ? 'bg-[#3f8a3a]' : state === 'down' ? 'bg-proof' : 'border border-graphite'}`} aria-hidden />{text}
    </li>
  )
  return (
    <ul className="space-y-1 border-t border-rule px-4 py-3 text-[13px] text-graphite">
      {line(health.falkordb ? 'ok' : 'down', health.falkordb ? 'FalkorDB connected' : 'FalkorDB not reachable')}
      {line(health.ollama ? 'ok' : 'off', health.ollama ? 'Ollama connected' : 'Ollama off: template answers')}
      {health.agents.includes(ws) && line('ok', 'Pipeline agents running here')}
    </ul>
  )
}

export default function App() {
  const [health, reconnects] = useHealth()
  const down = health !== null && !health.falkordb

  return (
    <div className="flex min-h-screen flex-col md:h-screen md:flex-row">
      <aside className="flex shrink-0 flex-col border-b border-rule bg-vellum md:w-60 md:border-b-0 md:border-r">
        <div className="flex items-center gap-2.5 px-4 py-5">
          <Network size={22} className="text-pen" aria-hidden />
          <div>
            <div className="font-serif text-lg font-semibold leading-none">GraphMind</div>
            <div className="mt-1 text-[13px] text-graphite">Papers as a graph</div>
          </div>
        </div>
        <WorkspacePicker />
        <nav className="mt-5 flex gap-1 overflow-x-auto px-2 pb-2 md:flex-1 md:flex-col md:overflow-visible md:pb-0" aria-label="Pages">
          {PAGES.map(({ path, label, icon: Icon }) => (
            <NavLink key={path} to={`/${path}`}
                     className={({ isActive }) => `flex shrink-0 items-center gap-2.5 rounded-md px-3 py-2 ${
                       isActive ? 'bg-sheet font-semibold text-ink ring-1 ring-rule' : 'text-graphite hover:bg-sheet/60 hover:text-ink'}`}>
              <Icon size={17} aria-hidden /> {label}
            </NavLink>
          ))}
        </nav>
        <div className="hidden md:block"><Status health={health} /></div>
      </aside>

      <main className="relative flex-1 bg-vellum md:overflow-y-auto" key={reconnects}>
        {down && (
          <div className="sticky top-0 z-30 border-b border-proof/30 bg-proof-soft px-5 py-3 md:px-10" role="alert">
            <p className="font-semibold text-proof">FalkorDB is not reachable</p>
            <p className="text-sm">Every page reads the knowledge graph, so the API answers 503 until it is back. Start it with <code className="font-mono">docker start &lt;name&gt;</code>; this page reconnects by itself.</p>
          </div>
        )}
        <Routes>
          <Route path="/" element={<Navigate to="/library" replace />} />
          {PAGES.map(({ path, element }) => <Route key={path} path={`/${path}`} element={element} />)}
          <Route path="*" element={<Navigate to="/library" replace />} />
        </Routes>
      </main>
      <PaperPanel />
    </div>
  )
}
````

### frontend/src/components/PaperPanel.tsx

````tsx
// The side panel for one paper: who wrote it, what it claims, whom it cites and why, and the numbers it reports.
// Any paper name in the app opens it.
import { useEffect, useState } from 'react'
import { X } from 'lucide-react'
import { api, type Citation } from '../api'
import { sentence } from '../format'
import { IntentTag, Loaded, PaperRef, Quote } from '../ui'
import { useData, useWorkspace } from '../workspace'

// result_origins in ontology.json, in words
const ORIGIN: Record<string, string> = {
  proposed: 'its own method', baseline_run: 'a baseline it ran', quoted: 'quoted from another paper',
  reproduced: 'a reproduction', corrected: 'corrected by an erratum',
}

function CitationList({ items, title }: { items: Citation[]; title: string }) {
  const [open, setOpen] = useState<string | null>(null)
  if (!items.length) return null
  return (
    <div className="mt-6">
      <h3 className="text-base">{title} <span className="font-sans text-sm font-normal text-graphite">{items.length}</span></h3>
      <ul className="mt-2 divide-y divide-rule">
        {items.map((c) => (
          <li key={c.id} className="py-2">
            <div className="flex items-baseline justify-between gap-3">
              <PaperRef id={c.id} />
              <IntentTag intent={c.intent} />
            </div>
            {c.contexts?.length ? (
              open === c.id ? (
                <div className="mt-2 space-y-2">{c.contexts.map((t, i) => <Quote key={i} text={t} />)}</div>
              ) : (
                <button className="mt-1 text-sm text-graphite underline-offset-2 hover:underline" onClick={() => setOpen(c.id)}>
                  Show the citing sentence
                </button>
              )
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  )
}

export default function PaperPanel() {
  const { ws, paperId, openPaper } = useWorkspace()
  const state = useData(paperId ? () => api.paper(ws, paperId) : null, [ws, paperId])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') openPaper(null) }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [openPaper])

  if (!paperId) return null
  return (
    <aside
      aria-label="Paper details"
      className="fixed inset-y-0 right-0 z-40 flex w-full max-w-[460px] flex-col border-l border-rule bg-sheet shadow-[-12px_0_32px_-16px_rgba(29,43,58,0.25)]"
    >
      <div className="flex items-center justify-between border-b border-rule px-5 py-3">
        <span className="text-sm text-graphite">Paper {paperId}</span>
        <button onClick={() => openPaper(null)} className="rounded p-1 hover:bg-vellum" aria-label="Close the paper panel">
          <X size={18} />
        </button>
      </div>
      <div className="flex-1 overflow-y-auto px-5 py-5">
        <Loaded state={state} what="Loading the paper">
          {(p) => (
            <>
              <h2 className="text-[1.45rem] leading-snug">{p.title}</h2>
              <p className="mt-2 text-sm text-graphite">
                {p.published || p.year}{p.authors.length ? `. ${p.authors.join(', ')}` : ''}
              </p>
              {!p.in_library && (
                <p className="mt-3 rounded-md bg-vellum px-3 py-2 text-sm text-graphite">
                  Cited by papers in the library, but its PDF has not been added, so only what others say about it is known.
                </p>
              )}
              {p.abstract && <p className="mt-4 font-serif leading-relaxed">{p.abstract}</p>}

              {p.claims.length > 0 && (
                <div className="mt-6">
                  <h3 className="text-base">What it claims</h3>
                  {p.claims.map((c) => (
                    <div key={c.id} className="mt-2 border-l-2 border-pen pl-3">
                      <p className="font-serif leading-relaxed">{c.text}</p>
                      <p className="mt-1 text-sm text-graphite">
                        {sentence(c.type)} claim{c.about.length ? `, about ${c.about.join(', ')}` : ''}
                      </p>
                    </div>
                  ))}
                </div>
              )}

              <CitationList title="Cites" items={p.cites} />
              <CitationList title="Cited by" items={p.cited_by} />

              {p.results.length > 0 && (
                <div className="mt-6">
                  <h3 className="text-base">Numbers it reports <span className="font-sans text-sm font-normal text-graphite">{p.results.length}</span></h3>
                  <table className="mt-2 w-full text-sm">
                    <thead className="text-left text-graphite">
                      <tr><th className="py-1 font-normal">Method</th><th className="font-normal">Dataset</th><th className="text-right font-normal">Value</th></tr>
                    </thead>
                    <tbody className="divide-y divide-rule">
                      {p.results.map((r, i) => (
                        <tr key={i} title={r.setting ?? ''}>
                          <td className="py-1.5">{r.method}</td>
                          <td>{r.dataset} {r.split}<div className="text-[13px] text-graphite">{r.metric}, {ORIGIN[r.origin] ?? r.origin}</div></td>
                          <td className="text-right tabular-nums">{r.value}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          )}
        </Loaded>
      </div>
    </aside>
  )
}
````

### frontend/src/components/LibraryMap.tsx

````tsx
// The library map: every paper as an index card in the row of its publication year (oldest at the top),
// every citation as an edge inked in its intent's colour. Papers that are cited but whose PDF is not added
// share the first row. The legend doubles as a filter. Clicking a card opens the paper panel.
import { useMemo, useState } from 'react'
import dagre from '@dagrejs/dagre'
import {
  Controls, Handle, MarkerType, Position, ReactFlow, type Edge, type Node, type NodeProps,
} from '@xyflow/react'
import type { LibraryGraph } from '../api'
import { INTENTS, intentOf, shortTitle } from '../intents'
import { useWorkspace } from '../workspace'

const CARD_W = 196
const CARD_H = 58
const SLOT_W = 226            // card plus the space beside it
const ROW_H = 128             // card plus the space below it, where the edges fan out
const LABEL_W = 120           // the year, left of each row
const OUTSIDE = -1            // the row for cited-only papers

type PaperData = { title: string; year: number | null; inLibrary: boolean; citedBy: number; dim: boolean }
type RowData = { label: string; width: number; shade: boolean }
type PaperNode = Node<PaperData, 'paper'>
type RowNode = Node<RowData, 'row'>

function PaperCard({ data, selected }: NodeProps<PaperNode>) {
  return (
    <div
      className={`rounded-md border px-3 py-2 transition-opacity ${data.inLibrary ? 'border-rule bg-sheet' : 'border-dashed border-[#b9c0c7] bg-vellum'}
        ${selected ? 'ring-2 ring-pen' : ''} ${data.dim ? 'opacity-35' : ''}`}
      style={{ width: CARD_W, height: CARD_H }}
      title={data.title}
    >
      {/* A citing (newer, lower) paper sends its edges from its top to the bottom of the older paper it cites. */}
      <Handle type="source" position={Position.Top} className="!opacity-0" isConnectable={false} />
      <Handle type="target" position={Position.Bottom} className="!opacity-0" isConnectable={false} />
      <div className={`truncate font-serif text-[16px] font-semibold leading-tight ${data.inLibrary ? '' : 'text-graphite'}`}>
        {shortTitle(data.title)}
      </div>
      <div className="mt-1 truncate text-[13px] text-graphite">
        {data.inLibrary ? `cited ${data.citedBy} time${data.citedBy === 1 ? '' : 's'} here` : `${data.year ?? 'no year'}, cited ${data.citedBy} times`}
      </div>
    </div>
  )
}

function YearRow({ data }: NodeProps<RowNode>) {
  return (
    <div className={`flex items-center rounded-lg ${data.shade ? 'bg-[#eceff0]/70' : ''}`} style={{ width: data.width, height: ROW_H - 24 }}>
      <div className={`px-4 font-serif font-semibold text-[#8f99a3] ${data.label.length > 4 ? 'w-[110px] text-[15px] leading-tight' : 'text-[26px]'}`}>
        {data.label}
      </div>
    </div>
  )
}

const nodeTypes = { paper: PaperCard, row: YearRow }

function layout(graph: LibraryGraph) {
  // dagre orders the cards so that edges cross as little as possible; the year then fixes each card's row.
  const g = new dagre.graphlib.Graph()
  g.setGraph({ rankdir: 'TB', nodesep: 24, ranksep: 60 })
  g.setDefaultEdgeLabel(() => ({}))
  graph.nodes.forEach((n) => g.setNode(n.id, { width: CARD_W, height: CARD_H }))
  graph.edges.forEach((e) => g.setEdge(e.target, e.source))     // older -> newer, so rank follows time
  dagre.layout(g)

  const rowOf = (n: LibraryGraph['nodes'][number]) => (n.in_library ? n.year ?? 0 : OUTSIDE)
  const rows = [...new Set(graph.nodes.map(rowOf))].sort((a, b) => a - b)
  const byRow = new Map<number, { id: string; x: number }[]>()
  graph.nodes.forEach((n) => byRow.set(rowOf(n), [...(byRow.get(rowOf(n)) ?? []), { id: n.id, x: g.node(n.id).x }]))
  const widest = Math.max(...[...byRow.values()].map((r) => r.length))

  // Each row is centred, in dagre's left-to-right order, so the map is only as wide as the busiest year.
  const pos: Record<string, { x: number; y: number }> = {}
  rows.forEach((row, i) => {
    const cards = (byRow.get(row) ?? []).sort((a, b) => a.x - b.x)
    const indent = LABEL_W + ((widest - cards.length) * SLOT_W) / 2
    cards.forEach((c, j) => { pos[c.id] = { x: indent + j * SLOT_W, y: i * ROW_H } })
  })
  return { pos, rows, width: LABEL_W + widest * SLOT_W, height: rows.length * ROW_H }
}

export default function LibraryMap({ graph }: { graph: LibraryGraph }) {
  const { openPaper, paperId } = useWorkspace()
  const [only, setOnly] = useState<string | null>(null)

  const { pos, rows, width, height } = useMemo(() => layout(graph), [graph])
  const counts = useMemo(() => {
    const c: Record<string, number> = {}
    graph.edges.forEach((e) => { c[e.intent ?? ''] = (c[e.intent ?? ''] ?? 0) + 1 })
    return c
  }, [graph])

  // When a paper is open, its own citations stay in full colour and everything else steps back.
  const touching = useMemo(() => new Set(
    paperId ? graph.edges.filter((e) => e.source === paperId || e.target === paperId).flatMap((e) => [e.source, e.target]) : [],
  ), [graph, paperId])

  const nodes: Node[] = [
    ...rows.map((y, i): RowNode => ({
      id: `row-${y}`, type: 'row', position: { x: 0, y: i * ROW_H - (ROW_H - 24 - CARD_H) / 2 }, draggable: false,
      selectable: false, zIndex: -1,
      data: { label: y === OUTSIDE ? 'Cited, PDF not added' : y ? String(y) : 'No year', width: width + 12, shade: i % 2 === 0 },
    })),
    ...graph.nodes.map((n): PaperNode => ({
      id: n.id, type: 'paper', position: pos[n.id], selected: n.id === paperId,
      data: {
        title: n.title, year: n.year, inLibrary: n.in_library,
        citedBy: graph.edges.filter((e) => e.target === n.id).length,
        dim: !!paperId && !touching.has(n.id),
      },
    })),
  ]

  const edges: Edge[] = graph.edges.map((e, i) => {
    const color = intentOf(e.intent).color
    const mine = !paperId || e.source === paperId || e.target === paperId
    return {
      id: `e${i}`, source: e.source, target: e.target,
      hidden: only !== null && (e.intent ?? '') !== only,
      style: { stroke: color, strokeWidth: mine && paperId ? 2.4 : 1.6, opacity: mine ? 0.95 : 0.12 },
      markerEnd: { type: MarkerType.ArrowClosed, color, width: 16, height: 16 },
    }
  })

  const legend = Object.keys(INTENTS).filter((k) => counts[k]).concat(Object.keys(counts).filter((k) => !INTENTS[k]))

  return (
    <div className="overflow-hidden rounded-lg border border-rule bg-sheet">
      <div className="flex flex-wrap items-center gap-x-1 gap-y-1 border-b border-rule px-3 py-2" role="group" aria-label="Show citations by intent">
        {legend.map((k) => {
          const it = intentOf(k)
          const on = only === k
          return (
            <button
              key={k || 'none'}
              aria-pressed={on}
              onClick={() => setOnly(on ? null : k)}
              title={it.meaning}
              className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-sm ${on ? 'bg-ink text-white' : 'hover:bg-vellum'} ${only && !on ? 'opacity-50' : ''}`}
            >
              <span className="h-2.5 w-2.5 rounded-full" style={{ background: it.color }} aria-hidden />
              {it.label} <span className={on ? 'text-white/70' : 'text-graphite'}>{counts[k]}</span>
            </button>
          )
        })}
        {only && <button className="ml-1 text-sm text-pen hover:underline" onClick={() => setOnly(null)}>Show every intent</button>}
      </div>
      {/* As tall as the map needs at full width, within limits. */}
      <div className="max-h-[780px] min-h-[420px] w-full" style={{ aspectRatio: `${width + 40} / ${height + 20}` }}>
        <ReactFlow
          key={graph.nodes.length}
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          fitView
          fitViewOptions={{ padding: 0.04 }}
          minZoom={0.2}
          nodesDraggable={false}
          nodesConnectable={false}
          onNodeClick={(_, n) => { if (n.type === 'paper') openPaper(n.id) }}
          onPaneClick={() => openPaper(null)}
        >
          <Controls showInteractive={false} position="bottom-right" />
        </ReactFlow>
      </div>
    </div>
  )
}
````

### frontend/src/components/PipelineBoard.tsx

````tsx
// The four agents' work, read from the Job nodes in the graph: one row per uploaded PDF, one cell per stage.
// A cell shows which agent did (or is doing) that stage. Nothing here talks to the agents: they only talk to the graph.
import { useState } from 'react'
import { Check, CircleAlert, LoaderCircle } from 'lucide-react'
import type { Job } from '../api'
import { shortTitle } from '../intents'

const STAGES = [
  { key: 'parse', label: 'Parse', does: 'reads the PDF: papers, authors, citations, result tables' },
  { key: 'extract', label: 'Extract', does: 'labels citation intents, picks each paper’s claim' },
  { key: 'link', label: 'Link', does: 'merges names for the same thing, links look-alike methods' },
  { key: 'critique', label: 'Critique', does: 'relates claims across papers, checks claims against numbers' },
]

function Cell({ job, stage, index }: { job: Job; stage: string; index: number }) {
  const at = STAGES.findIndex((s) => s.key === job.stage)
  const finished = job.stage === 'done' || index < at
  const doneBy = job.history.find((h) => h.endsWith(`:${stage}`))?.split(':')[0]
  if (finished) {
    return (
      <div className="flex h-9 items-center gap-1.5 rounded bg-pen-soft px-2 text-[13px] text-pen" title={`Done by ${doneBy}`}>
        <Check size={14} aria-hidden /> <span className="truncate">{doneBy}</span>
      </div>
    )
  }
  if (index === at && job.status === 'running') {
    return (
      <div className="flex h-9 items-center gap-1.5 rounded bg-pen px-2 text-[13px] font-semibold text-white" title={`${job.agent} is working`}>
        <LoaderCircle size={14} className="animate-spin" aria-hidden /> <span className="truncate">{job.agent}</span>
      </div>
    )
  }
  if (index === at && job.status === 'failed') {
    return (
      <div className="flex h-9 items-center gap-1.5 rounded bg-proof px-2 text-[13px] text-white" title={job.error ?? ''}>
        <CircleAlert size={14} aria-hidden /> failed
      </div>
    )
  }
  const waiting = index === at && job.status === 'ready'
  return (
    <div className={`flex h-9 items-center rounded border border-dashed px-2 text-[13px] ${waiting ? 'border-pen/50 text-pen' : 'border-rule text-graphite/70'}`}>
      {waiting ? (job.attempts ? `retry ${job.attempts + 1}` : 'waiting') : ''}
    </div>
  )
}

export default function PipelineBoard({ jobs }: { jobs: Job[] }) {
  const done = jobs.filter((j) => j.status === 'done').length
  const failed = jobs.filter((j) => j.status === 'failed')
  const busy = jobs.length - done - failed.length
  const [open, setOpen] = useState(busy > 0)
  const show = open || busy > 0

  return (
    <div className="rounded-lg border border-rule bg-sheet">
      <div className="flex flex-wrap items-center justify-between gap-2 px-4 py-3">
        <p>
          <span className="font-semibold">{busy ? `Agents are reading ${busy} of ${jobs.length} papers` : `${done} of ${jobs.length} papers read`}</span>
          {failed.length > 0 && <span className="text-proof">, {failed.length} failed</span>}
        </p>
        {!busy && (
          <button className="text-sm text-pen hover:underline" onClick={() => setOpen(!open)} aria-expanded={show}>
            {show ? 'Hide the pipeline' : 'Show the pipeline'}
          </button>
        )}
      </div>
      {show && (
        <div className="overflow-x-auto border-t border-rule px-4 pb-4">
          <table className="w-full min-w-[680px] table-fixed border-separate border-spacing-x-1.5 border-spacing-y-1.5 text-left">
            <thead>
              <tr className="text-sm text-graphite">
                <th className="w-[32%] py-2 font-normal">Paper</th>
                {STAGES.map((s) => <th key={s.key} className="font-normal" title={s.does}>{s.label}</th>)}
              </tr>
            </thead>
            <tbody>
              {jobs.map((j) => (
                <tr key={j.id}>
                  <td className="max-w-0 truncate pr-2 text-sm" title={j.error ?? j.title ?? j.file}>
                    <span className="font-serif text-[15px] font-semibold">{j.title ? shortTitle(j.title) : j.file}</span>
                    {j.error && j.status === 'failed' && <div className="truncate text-[13px] text-proof">{j.error}</div>}
                  </td>
                  {STAGES.map((s, i) => <td key={s.key}><Cell job={j} stage={s.key} index={i} /></td>)}
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-2 text-[13px] text-graphite">
            Each agent claims a job from the graph, does its stage, and hands the job on. A stage starts when every paper has finished the stages before it.
          </p>
        </div>
      )}
    </div>
  )
}
````

### frontend/src/components/StepTimeline.tsx

````tsx
// How the research agent reached an answer, step by step, as the server-sent events arrive.
// Every graph query it ran is listed with its Cypher, so the answer can be checked against the graph.
import { useState } from 'react'
import { Check, ChevronDown, ChevronRight, LoaderCircle } from 'lucide-react'
import type { StepEvent, ToolCall } from '../api'
import { Chips } from '../ui'

const STEP_NAMES: Record<string, string> = {
  understand: 'Understand the question',
  clarify: 'Ask which names are meant',
  plan: 'Choose graph queries',
  run_tools: 'Run the queries on FalkorDB',
  gather_evidence: 'Find the passages behind each fact',
  verify: 'Check the facts cover the question',
  answer: 'Write the answer',
  remember: 'Remember it in this session',
}

const INTENT_WORDS: Record<string, string> = {
  relate_papers: 'how two papers are related', sota: 'whether a state-of-the-art claim holds', lineage: 'where a method comes from',
  leaderboard: 'a leaderboard', disagreements: 'which claims disagree', missing_citations: 'missing citations',
  research_gaps: 'research gaps', people: 'authors and groups', literature_review: 'a literature review', recall: 'what was saved before',
}

/** The queries live indented inside Python strings; remove the common indent so they read as written. */
function dedent(text: string): string {
  const lines = text.trim().split('\n')
  const indents = lines.slice(1).filter((l) => l.trim()).map((l) => l.length - l.trimStart().length)
  const cut = indents.length ? Math.min(...indents) : 0
  return [lines[0], ...lines.slice(1).map((l) => l.slice(cut))].join('\n')
}

function ToolRow({ call }: { call: ToolCall }) {
  const [open, setOpen] = useState(false)
  const params = Object.entries(call.params).map(([k, v]) => `${k}: ${JSON.stringify(v)}`).join(', ')
  return (
    <li className="py-1.5">
      <button onClick={() => setOpen(!open)} aria-expanded={open} className="flex w-full items-start gap-1 text-left text-sm">
        {open ? <ChevronDown size={16} className="mt-0.5 shrink-0" /> : <ChevronRight size={16} className="mt-0.5 shrink-0" />}
        <span className="flex-1">
          <span className="font-semibold">{call.tool}</span>
          {params && <span className="text-graphite"> ({params})</span>}
          <span className="block text-[13px] text-graphite">{call.rows} row{call.rows === 1 ? '' : 's'} in {call.ms} ms</span>
        </span>
      </button>
      {open && (
        <div className="mt-2 space-y-2 pl-5">
          {Object.entries(call.cypher).map(([name, text]) => (
            <figure key={name}>
              <figcaption className="text-[13px] text-graphite">{name}</figcaption>
              <pre className="mt-1 overflow-x-auto rounded-md bg-ink px-3 py-2 font-mono text-[12px] leading-relaxed text-[#e8edf2]">
                {dedent(text)}
              </pre>
            </figure>
          ))}
        </div>
      )}
    </li>
  )
}

function Detail({ e }: { e: StepEvent }) {
  switch (e.step) {
    case 'understand':
      return (
        <>
          <p>About {INTENT_WORDS[e.intent] ?? e.intent}, decided by {e.decided_by === 'rules' ? 'keyword rules' : e.decided_by}.</p>
          {e.entities.length > 0 && <div className="mt-1.5"><Chips items={e.entities} /></div>}
        </>
      )
    case 'clarify':
      return <p>The question names nothing the graph knows, so the agent asks instead of guessing.</p>
    case 'plan':
      return <ul className="list-inside list-disc">{e.tools.map((t) => <li key={t}>{t}</li>)}</ul>
    case 'run_tools':
      return <ul className="divide-y divide-rule">{e.tool_log.map((c, i) => <ToolRow key={i} call={c} />)}</ul>
    case 'gather_evidence':
      return (
        <p>
          {e.facts} fact{e.facts === 1 ? '' : 's'} from the graph;{' '}
          {e.passages ? `a passage from the papers found for ${e.passages} of them.` : 'no passage from the papers to quote.'}
        </p>
      )
    case 'verify':
      return e.gaps.length || e.notes.length || e.extra_tools.length ? (
        <>
          {e.gaps.map((g) => <p key={g}>Missing: {g}</p>)}
          {e.notes.map((n) => <p key={n}>{n}</p>)}
          {e.extra_tools.length > 0 && <p>Running more: {e.extra_tools.join(', ')}</p>}
        </>
      ) : <p>Nothing missing.</p>
    case 'answer':
      return <p>{e.source === 'llm' ? 'Written by the local model from the facts only.' : 'Built from the facts by a template.'}</p>
    case 'remember':
      return <p>{e.saved ? 'Saved as a Question node linked to the papers it is about.' : 'Not saved.'}</p>
    default:
      return null
  }
}

export default function StepTimeline({ events, running }: { events: StepEvent[]; running: boolean }) {
  const steps = events.filter((e) => e.step !== 'final' && e.step !== 'error')
  if (!steps.length && !running) {
    return <p className="text-sm text-graphite">The steps are shown for questions asked during this visit.</p>
  }
  return (
    <ol className="space-y-4">
      {steps.map((e, i) => (
        <li key={i} className="flex gap-3">
          <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-pen text-white"><Check size={13} aria-hidden /></span>
          <div className="min-w-0 flex-1 text-sm">
            <p className="font-semibold">
              {STEP_NAMES[e.step] ?? e.step}{e.step === 'run_tools' && e.round > 1 ? `, round ${e.round}` : ''}
            </p>
            <div className="mt-0.5 text-graphite [&_.font-semibold]:text-ink"><Detail e={e} /></div>
          </div>
        </li>
      ))}
      {running && (
        <li className="flex items-center gap-3 text-sm text-pen" role="status">
          <LoaderCircle size={20} className="animate-spin" aria-hidden /> Working…
        </li>
      )}
    </ol>
  )
}
````

### frontend/src/components/AnswerView.tsx

````tsx
// One answer: the prose, then the numbered facts it was built from, each with the passage that backs it.
import type { ReactNode } from 'react'
import type { Answer } from '../api'
import { splitAnswer } from '../format'
import { PaperRef, Quote } from '../ui'

/** "... higher [1][2]." -> text with clickable fact numbers. */
function withFactLinks(text: string, prefix: string): ReactNode[] {
  return text.split(/(\[\d+\])/g).map((part, i) => {
    const m = part.match(/^\[(\d+)\]$/)
    if (!m) return part
    return (
      <a key={i} href={`#${prefix}-${m[1]}`} className="mx-px align-super font-sans text-[11px] font-semibold text-pen no-underline hover:underline"
         aria-label={`fact ${m[1]}`}>
        {m[1]}
      </a>
    )
  })
}

export default function AnswerView({ answer, source, id }: { answer: Answer; source?: string; id: string }) {
  const { prose, notes } = splitAnswer(answer.answer)
  const prefix = `fact-${id}`
  const kind = source ?? answer.source
  return (
    <div>
      <div className="max-w-[68ch] space-y-3 font-serif text-[17px] leading-[1.65]">
        {prose.map((p, i) => <p key={i} className="whitespace-pre-line">{withFactLinks(p, prefix)}</p>)}
      </div>
      {notes.map((n, i) => <p key={i} className="mt-2 max-w-[68ch] text-sm text-graphite">{n}</p>)}

      {answer.facts.length > 0 && (
        <div className="mt-5">
          <p className="text-sm text-graphite">
            {kind === 'llm' ? 'The local model wrote this from these facts, and was checked to name nothing outside them.'
              : kind === 'clarify' ? '' : 'Built from these facts, read from the graph.'}
          </p>
          <ol className="mt-2 space-y-3">
            {answer.facts.map((f) => (
              <li key={f.n} id={`${prefix}-${f.n}`} className="flex scroll-mt-24 gap-3 target:rounded-md target:bg-pen-soft target:p-2">
                <span className="w-5 shrink-0 text-right font-semibold tabular-nums text-pen">{f.n}</span>
                <div className="min-w-0 flex-1">
                  <p>{f.text}</p>
                  <p className="mt-0.5 text-[13px] text-graphite">
                    From {f.tool}
                    {f.papers.length > 0 && <>, about </>}
                    {f.papers.map((p, i) => <span key={p}>{i > 0 && ', '}<PaperRef id={p} /></span>)}
                  </p>
                  {(answer.evidence[String(f.n)] ?? []).map((e, i) => (
                    <div key={i} className="mt-2"><Quote text={e.excerpt} source={`${e.paper}, ${e.section}`} /></div>
                  ))}
                </div>
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  )
}
````

### frontend/src/pages/Library.tsx

````tsx
// Library: drop PDFs in, watch the four agents read them, and see the papers appear on the citation map.
import { useEffect, useRef, useState } from 'react'
import { FileUp } from 'lucide-react'
import { api, type ApiError, type Job } from '../api'
import LibraryMap from '../components/LibraryMap'
import PipelineBoard from '../components/PipelineBoard'
import { Empty, Loaded, Page, PaperRef, Problem, Section } from '../ui'
import { useData, useWorkspace } from '../workspace'

function DropZone({ onFiles, busy }: { onFiles: (files: File[]) => void; busy: boolean }) {
  const [over, setOver] = useState(false)
  const input = useRef<HTMLInputElement>(null)
  const take = (list: FileList | null) => {
    const pdfs = [...(list ?? [])].filter((f) => f.name.toLowerCase().endsWith('.pdf'))
    if (pdfs.length) onFiles(pdfs)
  }
  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setOver(true) }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => { e.preventDefault(); setOver(false); take(e.dataTransfer.files) }}
      className={`flex flex-wrap items-center gap-4 rounded-lg border-2 border-dashed px-5 py-4 ${over ? 'border-pen bg-pen-soft' : 'border-rule bg-sheet'}`}
    >
      <FileUp size={22} className="text-pen" aria-hidden />
      <p className="flex-1">
        <span className="font-semibold">Drop research papers here</span>
        <span className="text-graphite"> (PDF). The agents read them and add them to this workspace’s graph.</span>
      </p>
      <input ref={input} type="file" accept="application/pdf" multiple hidden onChange={(e) => { take(e.target.files); e.target.value = '' }} />
      <button
        onClick={() => input.current?.click()}
        disabled={busy}
        className="rounded-md bg-pen px-4 py-2 text-white hover:bg-[#233d96] disabled:opacity-60"
      >
        {busy ? 'Uploading…' : 'Choose PDFs'}
      </button>
    </div>
  )
}

export default function Library() {
  const { ws, refreshTitles, refreshWorkspaces } = useWorkspace()
  const [jobs, setJobs] = useState<Job[]>([])
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState<ApiError>()
  // Poll the job board while any job is unfinished. Each time a paper gets past a stage, reload the map and the list.
  const progress = jobs.reduce((n, j) => n + j.history.length, 0)
  const graph = useData(ws ? () => api.libraryGraph(ws) : null, [ws, progress])
  const papers = useData(ws ? () => api.papers(ws) : null, [ws, progress])
  const unfinished = jobs.some((j) => j.status === 'ready' || j.status === 'running')
  useEffect(() => {
    if (!ws) return
    let live = true
    const tick = () => api.jobs(ws).then((j) => { if (live) setJobs(j) }).catch(() => { if (live) setJobs([]) })
    tick()
    if (!unfinished) return () => { live = false }
    const timer = setInterval(tick, 1000)
    return () => { live = false; clearInterval(timer) }
  }, [ws, unfinished])
  useEffect(() => { if (progress) refreshTitles() }, [progress, refreshTitles])

  const upload = async (files: File[]) => {
    setUploading(true)
    setUploadError(undefined)
    try {
      await api.upload(ws, files)
      refreshWorkspaces()
      setJobs(await api.jobs(ws))
    } catch (e) {
      setUploadError(e as ApiError)
    } finally {
      setUploading(false)
    }
  }

  return (
    <Page
      wide
      title="Library"
      intro="Every paper in this workspace and how they cite each other. Each citation is coloured by why it was made, which the graph works out from the citing sentence."
    >
      <div className="space-y-4">
        <DropZone onFiles={upload} busy={uploading} />
        <Problem error={uploadError} />
        {jobs.length > 0 && <PipelineBoard jobs={jobs} />}
      </div>

      <div className="mt-8">
        <Loaded state={graph} what="Drawing the map">
          {(g) => g.nodes.length ? <LibraryMap graph={g} /> : <Empty>No papers yet. Drop a few PDFs above to start the graph.</Empty>}
        </Loaded>
      </div>

      {papers.data && papers.data.length > 0 && (
        <div className="mt-10">
          <Section title="Papers in the library" count={papers.data.length}>
            <table className="w-full text-left">
              <thead className="text-sm text-graphite">
                <tr><th className="py-1.5 font-normal">Title</th><th className="font-normal">Published</th><th className="hidden font-normal md:table-cell">Authors</th></tr>
              </thead>
              <tbody className="divide-y divide-rule">
                {papers.data.map((p) => (
                  <tr key={p.id}>
                    <td className="py-2 pr-4 font-serif"><PaperRef id={p.id} full /></td>
                    <td className="whitespace-nowrap pr-4 text-sm tabular-nums text-graphite">{p.published ?? p.year}</td>
                    <td className="hidden text-sm text-graphite md:table-cell">{p.authors.join(', ')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Section>
        </div>
      )}
    </Page>
  )
}
````

### frontend/src/pages/Ask.tsx

````tsx
// Ask: questions to the research agent. The answer streams in step by step; every fact comes from a graph query
// and the query's Cypher is one click away. Questions and saved insights are remembered in the session's graph.
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { BookmarkPlus, Plus, SendHorizontal } from 'lucide-react'
import { api, askStream, type Answer, type ApiError, type StepEvent } from '../api'
import AnswerView from '../components/AnswerView'
import { splitAnswer } from '../format'
import StepTimeline from '../components/StepTimeline'
import { Page, Problem } from '../ui'
import { useWorkspace } from '../workspace'

type Turn = { key: string; question: string; events: StepEvent[]; answer?: Answer; running: boolean; error?: string }

const EXAMPLES = [
  'How are GraphWalker-QA and Revisiting Graph Gains related?',
  'Is HopLens really state of the art?',
  'What is the leaderboard on KaveriHop 3-hop?',
  'Where does LiteGraphFuse come from?',
  'Which claims contradict each other?',
  'Which authors bridge the groups?',
]

function SaveInsight({ turn }: { turn: Turn }) {
  const { ws, sessionId } = useWorkspace()
  const [open, setOpen] = useState(false)
  const [text, setText] = useState('')
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<ApiError>()
  if (!turn.answer || !sessionId) return null
  const about = [...new Set(turn.answer.facts.flatMap((f) => f.papers))]

  if (saved) return <p className="text-sm text-pen">Saved to this session. Ask “What did I save earlier?” to recall it.</p>
  if (!open) {
    return (
      <button
        onClick={() => { setText(splitAnswer(turn.answer!.answer).prose[0] ?? ''); setOpen(true) }}
        className="inline-flex items-center gap-1.5 rounded-md border border-rule bg-sheet px-3 py-1.5 text-sm hover:border-graphite"
      >
        <BookmarkPlus size={15} aria-hidden /> Save as insight
      </button>
    )
  }
  const save = async () => {
    try {
      await api.saveInsight(ws, sessionId, text.trim(), about)
      setSaved(true)
    } catch (e) {
      setError(e as ApiError)
    }
  }
  return (
    <div className="max-w-[68ch] space-y-2">
      <label className="block text-sm text-graphite" htmlFor={`insight-${turn.key}`}>
        Your note, linked to {about.length} paper{about.length === 1 ? '' : 's'} in the graph
      </label>
      <textarea id={`insight-${turn.key}`} value={text} onChange={(e) => setText(e.target.value)} rows={3}
                className="w-full rounded-md border border-rule bg-sheet px-3 py-2 font-serif" />
      <div className="flex gap-2">
        <button onClick={save} disabled={!text.trim()} className="rounded-md bg-pen px-3 py-1.5 text-sm text-white disabled:opacity-60">Save insight</button>
        <button onClick={() => setOpen(false)} className="rounded-md px-3 py-1.5 text-sm text-graphite hover:bg-vellum">Cancel</button>
      </div>
      <Problem error={error} />
    </div>
  )
}

export default function Ask() {
  const { ws, sessionId, setSessionId } = useWorkspace()
  const [turns, setTurns] = useState<Turn[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [question, setQuestion] = useState('')
  const [title, setTitle] = useState('')
  const [error, setError] = useState<ApiError>()
  const justCreated = useRef<string | null>(null)
  const asked = useRef(0)                      // numbers the questions asked on this page, for their keys
  const running = turns.some((t) => t.running)

  // Load the session's earlier questions (unless this page just created the session itself).
  useEffect(() => {
    if (!ws || !sessionId) { setTurns([]); setTitle(''); return }
    if (justCreated.current === sessionId) return
    let live = true
    Promise.all([api.session(ws, sessionId), api.sessions(ws)]).then(([s, all]) => {
      if (!live) return
      setTurns(s.history.map((h) => ({ key: h.id, question: h.question, events: [], answer: h.answer, running: false })))
      setTitle(all.find((x) => x.id === sessionId)?.title ?? '')
    }).catch(() => { if (live) setSessionId(null) })       // the session is gone (another workspace, or reset)
    return () => { live = false }
  }, [ws, sessionId, setSessionId])

  const update = (key: string, change: (t: Turn) => Turn) =>
    setTurns((all) => all.map((t) => (t.key === key ? change(t) : t)))

  const ask = async (text: string) => {
    const q = text.trim()
    if (!q || running) return
    setError(undefined)
    let sid = sessionId
    try {
      if (!sid) {
        sid = (await api.newSession(ws, q.slice(0, 60))).id
        justCreated.current = sid
        setSessionId(sid)
        setTitle(q.slice(0, 60))
      }
    } catch (e) {
      setError(e as ApiError)
      return
    }
    const key = `asked-${++asked.current}`
    setTurns((all) => [...all, { key, question: q, events: [], running: true }])
    setSelected(key)
    setQuestion('')
    setTimeout(() => document.getElementById(`turn-${key}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 50)
    try {
      await askStream(ws, sid, q, (e) => {
        update(key, (t) => ({
          ...t,
          events: [...t.events, e],
          answer: e.step === 'final' ? { answer: e.answer, source: e.source, facts: e.facts, evidence: e.evidence } : t.answer,
          error: e.step === 'error' ? e.detail : t.error,
        }))
        if (e.step === 'final') {      // now the answer is long enough to scroll the question to the top
          setTimeout(() => document.getElementById(`turn-${key}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 60)
        }
      })
    } catch (e) {
      update(key, (t) => ({ ...t, error: (e as ApiError).message }))
    }
    update(key, (t) => ({ ...t, running: false }))
  }

  const submit = (e: FormEvent) => { e.preventDefault(); ask(question) }
  const newSession = () => { justCreated.current = null; setSessionId(null); setTurns([]); setSelected(null) }
  const shown = turns.find((t) => t.key === selected) ?? turns[turns.length - 1]

  return (
    <Page
      wide
      title="Ask the library"
      intro="The agent answers from graph queries, not from memory. Each fact below an answer names the query it came from."
      actions={
        <div className="flex items-center gap-3 text-sm">
          {title && <span className="max-w-[28ch] truncate text-graphite" title={title}>Session: {title}</span>}
          <button onClick={newSession} className="inline-flex items-center gap-1.5 rounded-md border border-rule bg-sheet px-3 py-1.5 hover:border-graphite">
            <Plus size={15} aria-hidden /> New session
          </button>
        </div>
      }
    >
      <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_380px]">
        <div className="min-w-0">
          {turns.length === 0 && (
            <div className="mb-8">
              <p className="text-graphite">Try one of these on the demo corpus:</p>
              <div className="mt-3 flex flex-wrap gap-2">
                {EXAMPLES.map((x) => (
                  <button key={x} onClick={() => ask(x)} className="rounded-full border border-rule bg-sheet px-3 py-1.5 text-left font-serif hover:border-pen hover:text-pen">
                    {x}
                  </button>
                ))}
              </div>
            </div>
          )}

          <div className="space-y-10">
            {turns.map((t) => (
              <article key={t.key} id={`turn-${t.key}`} onClick={() => setSelected(t.key)}
                       className={`scroll-mt-6 border-l-2 pl-5 ${shown?.key === t.key ? 'border-pen' : 'border-transparent'}`}>
                <h2 className="font-sans text-[17px] font-semibold">{t.question}</h2>
                <div className="mt-3">
                  {t.answer ? <AnswerView answer={t.answer} id={t.key} />
                    : t.running ? <p className="text-graphite">Working through the graph…</p> : null}
                  {t.error && <p className="mt-2 text-proof">{t.error}</p>}
                </div>
                {!t.running && t.answer && t.answer.source !== 'clarify' && <div className="mt-4"><SaveInsight turn={t} /></div>}
              </article>
            ))}
          </div>

          <form onSubmit={submit} className="sticky bottom-0 mt-8 bg-gradient-to-t from-vellum from-70% to-transparent pb-5 pt-6">
            <Problem error={error} />
            <div className="flex items-end gap-2 rounded-lg border border-rule bg-sheet p-2 focus-within:border-pen">
              <label htmlFor="question" className="sr-only">Your question</label>
              <textarea
                id="question" rows={2} value={question} onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); ask(question) } }}
                placeholder="Ask how papers relate, what is state of the art, who works with whom…"
                className="flex-1 resize-none bg-transparent px-2 py-1.5 font-serif text-[17px] outline-none"
              />
              <button type="submit" disabled={running || !question.trim()}
                      className="inline-flex items-center gap-1.5 rounded-md bg-pen px-4 py-2 text-white disabled:opacity-50">
                <SendHorizontal size={16} aria-hidden /> Ask
              </button>
            </div>
          </form>
        </div>

        <aside className="lg:sticky lg:top-6 lg:max-h-[calc(100vh-3rem)] lg:self-start lg:overflow-y-auto">
          <div className="rounded-lg border border-rule bg-sheet p-5">
            <h2 className="text-lg">How the agent answered</h2>
            {shown && <p className="mt-1 truncate text-sm text-graphite" title={shown.question}>{shown.question}</p>}
            <div className="mt-4">
              {shown ? <StepTimeline events={shown.events} running={shown.running} />
                : <p className="text-sm text-graphite">Ask a question to see each step: what the agent understood, which graph queries it ran, and what it checked.</p>}
            </div>
          </div>
        </aside>
      </div>
    </Page>
  )
}
````

### frontend/src/pages/Compare.tsx

````tsx
// Compare: everything the graph knows that connects two papers, path by path.
import { useState } from 'react'
import { api } from '../api'
import { shortTitle } from '../intents'
import { Chips, Empty, IntentTag, Loaded, Page, PaperRef, Quote, Relation, Section } from '../ui'
import { useData, useWorkspace } from '../workspace'

function Picker({ label, value, onChange, options }: {
  label: string; value: string; onChange: (v: string) => void; options: { id: string; title: string }[]
}) {
  return (
    <label className="flex min-w-[260px] flex-1 flex-col gap-1 text-sm text-graphite">
      {label}
      <select value={value} onChange={(e) => onChange(e.target.value)}
              className="rounded-md border border-rule bg-sheet px-3 py-2 font-serif text-[16px] text-ink">
        {options.map((o) => <option key={o.id} value={o.id}>{o.title}</option>)}
      </select>
    </label>
  )
}

export default function Compare() {
  const { ws } = useWorkspace()
  const papers = useData(ws ? () => api.papers(ws) : null, [ws])
  const [chosenA, setA] = useState('')
  const [chosenB, setB] = useState('')

  // Until the reader picks, start on the pair the demo is about if it is here, else the first two papers.
  const list = papers.data ?? []
  const find = (name: string) => list.find((p) => p.title.startsWith(name))?.id
  const a = chosenA || find('GraphWalker-QA') || list[0]?.id || ''
  const b = chosenB || find('Revisiting Graph Gains') || list[1]?.id || ''

  const pair = useData(a && b && a !== b ? () => api.pair(ws, a, b) : null, [ws, a, b])
  const options = (papers.data ?? []).map((p) => ({ id: p.id, title: `${shortTitle(p.title)} (${p.year})` }))

  return (
    <Page title="Compare two papers" intro="Citations between them, the people and datasets they share, method lineage, claims that agree or clash, and results one re-ran from the other.">
      <Loaded state={papers} what="Loading papers">
        {() => (
          <div className="mb-8 flex flex-wrap gap-4">
            <Picker label="First paper" value={a} onChange={setA} options={options} />
            <Picker label="Second paper" value={b} onChange={setB} options={options} />
          </div>
        )}
      </Loaded>
      {a && a === b && <Empty>Pick two different papers.</Empty>}
      {a && b && a !== b && (
        <Loaded state={pair} what="Following the paths between them">
          {(r) => {
            const shared = [
              ['Shared authors', r.shared_authors?.authors],
              ['Datasets both evaluate on', r.shared_datasets?.datasets],
              ['Methods both use or propose', r.shared_methods?.methods],
            ] as const
            const nothing = !r.citations.length && !r.lineage.length && !r.claims.length && !r.result_links.length
              && !r.quotes.length && shared.every(([, x]) => !x?.length)
            if (nothing) return <Empty>The graph has no path between these two papers.</Empty>
            return (
              <>
                <Section title="Citations between them" count={r.citations.length}>
                  {r.citations.length ? r.citations.map((c, i) => (
                    <div key={i} className="mb-4">
                      <p><PaperRef id={c.citing} /> cites <PaperRef id={c.cited} />, as <IntentTag intent={c.intent} /></p>
                      <div className="mt-2 space-y-1.5">{c.contexts?.map((t, j) => <Quote key={j} text={t} />)}</div>
                    </div>
                  )) : <p className="text-graphite">Neither cites the other.</p>}
                </Section>

                <Section title="What they share">
                  <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-[220px_1fr]">
                    {shared.map(([label, items]) => (
                      <div key={label} className="contents">
                        <dt className="text-graphite">{label}</dt>
                        <dd><Chips items={items ? [...items] : []} /></dd>
                      </div>
                    ))}
                  </dl>
                </Section>

                {r.lineage.length > 0 && (
                  <Section title="Method lineage">
                    {r.lineage.map((l, i) => (
                      <p key={i} className="mb-2 font-serif text-[17px]">
                        {l.chain.map((m, j) => (
                          <span key={j}>{j > 0 && <span className="px-1.5 font-sans text-sm text-graphite">extends</span>}{m}</span>
                        ))}
                      </p>
                    ))}
                  </Section>
                )}

                {r.claims.length > 0 && (
                  <Section title="Their claims" count={r.claims.length}>
                    {r.claims.map((c, i) => (
                      <div key={i} className="mb-5 grid gap-3 md:grid-cols-[1fr_auto_1fr] md:items-start">
                        <p className="font-serif leading-relaxed">{c.claim_a}</p>
                        <div className="md:pt-0.5"><Relation name={c.relation} /></div>
                        <p className="font-serif leading-relaxed">{c.claim_b}</p>
                        <p className="text-sm text-graphite md:col-span-3">Why: {c.basis}</p>
                      </div>
                    ))}
                  </Section>
                )}

                {r.result_links.length > 0 && (
                  <Section title="Results re-run" count={r.result_links.length}>
                    <table className="w-full text-left">
                      <thead className="text-sm text-graphite">
                        <tr><th className="py-1.5 font-normal">Method</th><th className="font-normal">Split</th><th className="text-right font-normal">Original</th><th className="text-right font-normal">Re-run</th><th className="pl-4 font-normal">Outcome</th></tr>
                      </thead>
                      <tbody className="divide-y divide-rule">
                        {r.result_links.map((x, i) => (
                          <tr key={i}>
                            <td className="py-2">{x.method}</td>
                            <td>{x.split}{x.setting && <div className="text-[13px] text-graphite">{x.setting}</div>}</td>
                            <td className="text-right tabular-nums">{x.original_value}</td>
                            <td className="text-right tabular-nums">{x.new_value}</td>
                            <td className="pl-4"><Relation name={x.relation} /></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </Section>
                )}

                {r.quotes.length > 0 && (
                  <Section title="Numbers one quotes from the other" count={r.quotes.length}>
                    <ul className="space-y-1">
                      {r.quotes.map((x, i) => <li key={i}>{x.method} on {x.dataset} {x.split}: <span className="tabular-nums">{x.value}</span></li>)}
                    </ul>
                  </Section>
                )}
              </>
            )
          }}
        </Loaded>
      )}
    </Page>
  )
}
````

### frontend/src/pages/Leaderboards.tsx

````tsx
// Leaderboards: one number per method on a dataset split, with errata applied and every other run of it shown.
import { useMemo, useState } from 'react'
import { api } from '../api'
import { Empty, Loaded, Page, PaperRef } from '../ui'
import { useData, useWorkspace } from '../workspace'

const ORIGIN: Record<string, string> = {
  proposed: 'own run', baseline_run: 'run as a baseline', quoted: 'quoted', reproduced: 'reproduced', corrected: 'corrected',
}

export default function Leaderboards() {
  const { ws } = useWorkspace()
  const options = useData(ws ? () => api.boardOptions(ws) : null, [ws])
  const [chosenDataset, setDataset] = useState('')
  const [chosenPick, setPick] = useState('')      // "split|metric"

  const datasets = useMemo(() => {
    const m = new Map<string, string>()
    ;(options.data ?? []).forEach((o) => m.set(o.dataset, o.dataset_name))
    return [...m]
  }, [options.data])
  // Until the reader picks, show KaveriHop (the demo's dataset) 3-hop if it is here, else the first board.
  const dataset = datasets.some(([id]) => id === chosenDataset) ? chosenDataset
    : datasets.find(([id]) => id === 'ds-kaveri')?.[0] ?? datasets[0]?.[0] ?? ''
  const choices = (options.data ?? []).filter((o) => o.dataset === dataset)
  const fallback = choices.find((c) => c.split === '3-hop') ?? choices[0]
  const pick = choices.some((c) => `${c.split}|${c.metric}` === chosenPick) ? chosenPick
    : fallback ? `${fallback.split}|${fallback.metric}` : ''

  const [split, metric] = pick.split('|')
  const board = useData(dataset && split && metric ? () => api.board(ws, dataset, split, metric) : null, [ws, dataset, split, metric])
  const metricName = choices.find((c) => c.split === split && c.metric === metric)?.metric_name ?? ''

  return (
    <Page title="Leaderboards" intro="One authoritative number per method. When an erratum corrects a paper, the corrected number counts; reproductions and quotes are listed beside it.">
      <Loaded state={options} what="Finding the datasets">
        {(opts) => opts.length === 0 ? <Empty>No result tables in this workspace yet.</Empty> : (
          <>
            <div className="mb-3 flex flex-wrap gap-2" role="group" aria-label="Dataset">
              {datasets.map(([id, name]) => (
                <button key={id} aria-pressed={id === dataset} onClick={() => setDataset(id)}
                        className={`rounded-md px-3 py-1.5 font-serif text-[16px] ${id === dataset ? 'bg-ink text-white' : 'border border-rule bg-sheet hover:border-graphite'}`}>
                  {name}
                </button>
              ))}
            </div>
            <div className="mb-8 flex flex-wrap gap-1.5" role="group" aria-label="Split and metric">
              {choices.map((c) => {
                const key = `${c.split}|${c.metric}`
                return (
                  <button key={key} aria-pressed={key === pick} onClick={() => setPick(key)}
                          className={`rounded-full px-3 py-1 text-sm ${key === pick ? 'bg-pen text-white' : 'text-graphite hover:bg-sheet'}`}>
                    {c.split === 'all' ? 'all splits' : c.split}, {c.metric_name} <span className="opacity-70">({c.results})</span>
                  </button>
                )
              })}
            </div>
          </>
        )}
      </Loaded>

      {dataset && split && (
        <Loaded state={board} what="Ranking">
          {(rows) => {
            const top = Math.max(...rows.map((r) => r.value), 1)
            return (
              <ol className="divide-y divide-rule border-y border-rule">
                {rows.map((r, i) => (
                  <li key={r.method} className="grid grid-cols-[2rem_minmax(0,1fr)_auto] items-start gap-x-4 py-3">
                    <span className="pt-1 text-right font-serif text-xl text-graphite tabular-nums">{i + 1}</span>
                    <div className="min-w-0">
                      <p className="font-serif text-[18px] font-semibold">{r.method}</p>
                      <p className="text-sm text-graphite">Reported in <PaperRef id={r.paper} /></p>
                      {r.corrected && (
                        <p className="mt-1 text-sm text-proof">Corrected by an erratum: the paper first published {r.as_published}.</p>
                      )}
                      {r.other_runs.length > 0 && (
                        <ul className="mt-1 text-sm text-graphite">
                          {r.other_runs.map((o, j) => (
                            <li key={j}>
                              {ORIGIN[o.origin] ?? o.origin} as <span className="tabular-nums text-ink">{o.value}</span> in <PaperRef id={o.paper} />
                              {o.setting && o.setting !== 'not reported' && `, with ${o.setting}`}
                            </li>
                          ))}
                          {r.spread > 0 && <li>Runs differ by up to {r.spread.toFixed(1)} points.</li>}
                        </ul>
                      )}
                      <div className="mt-2 h-1.5 rounded-full bg-vellum" aria-hidden>
                        <div className="h-1.5 rounded-full bg-pen/70" style={{ width: `${(r.value / top) * 100}%` }} />
                      </div>
                    </div>
                    <span className="pt-0.5 text-right">
                      <span className="font-serif text-2xl tabular-nums">{r.value}</span>
                      <span className="block text-[13px] text-graphite">{metricName}</span>
                    </span>
                  </li>
                ))}
              </ol>
            )
          }}
        </Loaded>
      )}
    </Page>
  )
}
````

### frontend/src/pages/Disagreements.tsx

````tsx
// Disagreements: claims the numbers do not back up, and claims that contradict, qualify or support each other.
import { api } from '../api'
import { Empty, Loaded, Page, PaperRef, Relation, Section } from '../ui'
import { useData, useWorkspace } from '../workspace'

export default function Disagreements() {
  const { ws } = useWorkspace()
  const state = useData(ws ? () => api.claims(ws) : null, [ws])
  return (
    <Page title="Disagreements" intro="Where papers disagree with each other, or with the numbers. Claim pairs are chosen by the graph (the newer paper cites the older one, about the same method); the local model only judges how they relate.">
      <Loaded state={state} what="Comparing claims">
        {(c) => (
          <>
            <Section title="State-of-the-art claims the numbers contradict" count={c.sota.length}
                     note="A paper claims to be best, but an earlier paper in the library reports a higher number on the same split.">
              {c.sota.length ? (
                <ul className="space-y-4">
                  {c.sota.map((s, i) => (
                    <li key={i} className="border-l-2 border-proof pl-4">
                      <p className="font-serif text-[17px] leading-relaxed">
                        <PaperRef id={s.paper} /> claims the best result on {s.dataset} {s.split} with{' '}
                        <span className="tabular-nums">{s.claimed_value}</span>, but {s.better_method} reports{' '}
                        <span className="font-semibold tabular-nums">{s.better_value}</span> in the <PaperRef id={s.better_paper} /> paper.
                      </p>
                    </li>
                  ))}
                </ul>
              ) : <Empty>Every state-of-the-art claim holds against the numbers in the library.</Empty>}
            </Section>

            <Section title="Claims that contradict or qualify each other" count={c.conflicts.length}>
              {c.conflicts.length ? c.conflicts.map((x, i) => (
                <div key={i} className="mb-6 grid gap-3 md:grid-cols-[1fr_auto_1fr] md:items-start">
                  <div>
                    <p className="font-serif leading-relaxed">{x.text}</p>
                    <p className="mt-1 text-sm"><PaperRef id={x.paper} /></p>
                  </div>
                  <div className="md:pt-0.5"><Relation name={x.relation} /></div>
                  <div>
                    <p className="font-serif leading-relaxed">{x.other_text}</p>
                    <p className="mt-1 text-sm"><PaperRef id={x.other_paper} /></p>
                  </div>
                  {x.basis && <p className="text-sm text-graphite md:col-span-3">Why: {x.basis}</p>}
                </div>
              )) : <Empty>No conflicting claims found.</Empty>}
            </Section>

            <Section title="Claims supported by later work" count={c.support.length}>
              {c.support.length ? (
                <ul className="divide-y divide-rule">
                  {c.support.map((s, i) => (
                    <li key={i} className="py-2.5">
                      <p><PaperRef id={s.paper} /> <Relation name="SUPPORTS" /> <PaperRef id={s.supported_paper} /></p>
                      {s.basis && <p className="mt-1 text-sm text-graphite">{s.basis}</p>}
                    </li>
                  ))}
                </ul>
              ) : <Empty>No supporting claims found yet.</Empty>}
            </Section>
          </>
        )}
      </Loaded>
    </Page>
  )
}
````

### frontend/src/pages/CitationCheck.tsx

````tsx
// Citation check: earlier papers a paper probably should cite, citations of corrected work, and much-cited outside papers.
import { api } from '../api'
import { Chips, Empty, Loaded, Page, PaperRef, Quote, Section } from '../ui'
import { useData, useWorkspace } from '../workspace'

export default function CitationCheck() {
  const { ws } = useWorkspace()
  const state = useData(ws ? () => api.citations(ws) : null, [ws])
  return (
    <Page title="Citation check" intro="Found by graph paths, not by text similarity: an earlier paper that evaluates on the same datasets, has a look-alike method, or beat the paper’s own numbers, but is not cited.">
      <Loaded state={state} what="Checking citations">
        {(c) => (
          <>
            <Section title="Probably missing citations" count={c.missing.length}
                     note="The score adds 2 per shared dataset, 3 per similar method and 2 per stronger result; 5 or more is listed.">
              {c.missing.length ? (
                <ul className="space-y-5">
                  {c.missing.map((m, i) => (
                    <li key={i} className="grid grid-cols-[3rem_1fr] gap-x-4">
                      <span className="text-right font-serif text-2xl tabular-nums text-proof" title="score">{m.score}</span>
                      <div>
                        <p className="font-serif text-[17px]"><PaperRef id={m.citing} /> does not cite <PaperRef id={m.paper} /></p>
                        <dl className="mt-1.5 grid gap-x-4 gap-y-1 text-sm sm:grid-cols-[150px_1fr]">
                          <dt className="text-graphite">Shared datasets</dt><dd><Chips items={m.shared_datasets} /></dd>
                          <dt className="text-graphite">Similar methods</dt><dd><Chips items={m.similar_methods} /></dd>
                          <dt className="text-graphite">Stronger results</dt><dd><Chips items={m.stronger_results} /></dd>
                        </dl>
                      </div>
                    </li>
                  ))}
                </ul>
              ) : <Empty>No missing citations found.</Empty>}
            </Section>

            <Section title="Citing a corrected paper" count={c.stale.length}
                     note="The cited paper has an erratum in the library, but the citing paper uses the original.">
              {c.stale.length ? c.stale.map((s, i) => (
                <div key={i} className="mb-4">
                  <p><PaperRef id={s.paper} /> cites <PaperRef id={s.cites} />, which a later erratum corrects: <PaperRef id={s.correction} full />.</p>
                  <div className="mt-2 space-y-1.5">{s.contexts?.map((t, j) => <Quote key={j} text={t} />)}</div>
                </div>
              )) : <Empty>No paper cites corrected work.</Empty>}
            </Section>

            <Section title="Outside papers cited often" count={c.external_hubs.length}
                     note="Cited by several papers here but not in the library. Adding their PDFs would fill in the graph.">
              {c.external_hubs.length ? (
                <ul className="divide-y divide-rule">
                  {c.external_hubs.map((h) => (
                    <li key={h.id} className="flex flex-wrap items-baseline justify-between gap-2 py-2">
                      <span className="font-serif"><PaperRef id={h.id} full />{h.year ? ` (${h.year})` : ''}</span>
                      <span className="text-sm text-graphite">cited by {h.cited_by.length}</span>
                    </li>
                  ))}
                </ul>
              ) : <Empty>No outside paper is cited three or more times.</Empty>}
            </Section>
          </>
        )}
      </Loaded>
    </Page>
  )
}
````

### frontend/src/pages/Gaps.tsx

````tsx
// Research gaps: what nobody in the library has tried yet, read from missing edges in the graph.
import { api } from '../api'
import { shortTitle } from '../intents'
import { Chips, Empty, Loaded, Page, PaperRef, Section } from '../ui'
import { useData, useWorkspace } from '../workspace'

export default function Gaps() {
  const { ws, titles } = useWorkspace()
  const state = useData(ws ? () => api.gaps(ws) : null, [ws])
  return (
    <Page title="Research gaps" intro="Each gap is a missing edge: a method with no result on a dataset, a metric no one reports, a result no one has re-run.">
      <Loaded state={state} what="Looking for gaps">
        {(g) => {
          const untested = g.gap_method_dataset.filter((m) => m.never_evaluated_on.length)
          const metrics = g.gap_metric_coverage.filter((m) => m.never_reported_on.length)
          return (
            <>
              <Section title="Methods never tested on a dataset" count={untested.length}>
                {untested.length ? (
                  <table className="w-full text-left">
                    <thead className="text-sm text-graphite">
                      <tr><th className="w-1/4 py-1.5 font-normal">Method</th><th className="font-normal">Never evaluated on</th><th className="hidden font-normal md:table-cell">Tested on</th></tr>
                    </thead>
                    <tbody className="divide-y divide-rule">
                      {untested.map((m) => (
                        <tr key={m.method} className="align-top">
                          <td className="py-2.5 pr-4 font-serif font-semibold">{m.method}</td>
                          <td className="py-2.5 pr-4"><Chips items={m.never_evaluated_on} /></td>
                          <td className="hidden py-2.5 text-sm text-graphite md:table-cell">{m.evaluated_on.join(', ')}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : <Empty>Every method has been tested on every dataset.</Empty>}
              </Section>

              <Section title="Results nobody has reproduced" count={g.gap_unreproduced.length}>
                {g.gap_unreproduced.length ? (
                  <ul className="flex flex-wrap gap-x-6 gap-y-2">
                    {g.gap_unreproduced.map((u) => (
                      <li key={u.method} className="font-serif">
                        {u.method === shortTitle(titles[u.paper]) ? <PaperRef id={u.paper} />
                          : <>{u.method} <span className="font-sans text-sm text-graphite">from</span> <PaperRef id={u.paper} /></>}
                      </li>
                    ))}
                  </ul>
                ) : <Empty>Every proposed method has been reproduced at least once.</Empty>}
              </Section>

              <Section title="Metrics missing on some datasets" count={metrics.length}>
                {metrics.length ? (
                  <ul className="space-y-2">
                    {metrics.map((m) => (
                      <li key={m.metric}><span className="font-semibold">{m.metric}</span> <span className="text-graphite">is never reported on</span> <Chips items={m.never_reported_on} /></li>
                    ))}
                  </ul>
                ) : <Empty>Every metric is reported on every dataset.</Empty>}
              </Section>

              <Section title="Datasets and their splits" count={g.gap_dataset_depth.length} note="Few splits or a single language means few kinds of question are covered.">
                <ul className="space-y-2">
                  {g.gap_dataset_depth.map((d) => (
                    <li key={d.dataset}>
                      <span className="font-serif font-semibold">{d.dataset}</span>
                      <span className="text-graphite">{d.language ? `, ${d.language}` : ''}: </span>
                      <Chips items={d.splits} empty="no splits recorded" />
                    </li>
                  ))}
                </ul>
              </Section>

              {g.gap_task_without_method.length > 0 && (
                <Section title="Tasks claims talk about but no paper here tackles" count={g.gap_task_without_method.length}>
                  <ul className="space-y-2">
                    {g.gap_task_without_method.map((t) => (
                      <li key={t.task}>
                        <span className="font-serif font-semibold">{t.task}</span>
                        <span className="text-graphite">: only outside methods ({t.external_methods.join(', ')}), mentioned in {t.claims.length} claim{t.claims.length === 1 ? '' : 's'}</span>
                      </li>
                    ))}
                  </ul>
                </Section>
              )}
            </>
          )
        }}
      </Loaded>
    </Page>
  )
}
````

### frontend/src/pages/People.tsx

````tsx
// People and influence: FalkorDB's graph algorithms (PageRank, betweenness, connected components) on the library.
import { api } from '../api'
import { Empty, Loaded, Page, PaperRef, Section } from '../ui'
import { useData, useWorkspace } from '../workspace'

export default function People() {
  const { ws } = useWorkspace()
  const state = useData(ws ? () => api.people(ws) : null, [ws])
  return (
    <Page title="People and influence" intro="Computed inside FalkorDB with its built-in graph algorithms, over the citation and co-author edges.">
      <Loaded state={state} what="Running the graph algorithms">
        {(p) => {
          const topPaper = Math.max(...p.influential.map((x) => x.score), 1e-9)
          const topBridge = Math.max(...p.bridges.map((x) => x.score), 1e-9)
          return (
            <>
              <Section title="Most influential papers" note="PageRank over citations: a paper ranks high when well-cited papers cite it. Papers outside the library count too.">
                <ol className="space-y-2.5">
                  {p.influential.map((x, i) => (
                    <li key={x.id} className="grid grid-cols-[1.5rem_minmax(0,1fr)_40%] items-center gap-3">
                      <span className="text-right text-graphite tabular-nums">{i + 1}</span>
                      <span className="min-w-0 font-serif"><PaperRef id={x.id} full />{!x.in_library && <span className="font-sans text-sm text-graphite"> (cited only)</span>}</span>
                      <span className="h-2 rounded-full bg-vellum" aria-hidden>
                        <span className="block h-2 rounded-full bg-pen/70" style={{ width: `${(x.score / topPaper) * 100}%` }} />
                      </span>
                    </li>
                  ))}
                </ol>
              </Section>

              <Section title="Authors who bridge groups" note="Betweenness over co-authorship: how often an author sits on the shortest path between two others.">
                {p.bridges.length ? (
                  <ol className="space-y-2.5">
                    {p.bridges.map((b, i) => (
                      <li key={b.author} className="grid grid-cols-[1.5rem_minmax(0,1fr)_40%] items-center gap-3">
                        <span className="text-right text-graphite tabular-nums">{i + 1}</span>
                        <span className="font-serif text-[17px]">{b.author}</span>
                        <span className="h-2 rounded-full bg-vellum" aria-hidden>
                          <span className="block h-2 rounded-full bg-pen/70" style={{ width: `${(b.score / topBridge) * 100}%` }} />
                        </span>
                      </li>
                    ))}
                  </ol>
                ) : <Empty>No co-author links yet.</Empty>}
              </Section>

              <Section title="Co-author groups" count={p.groups.length} note="Connected components: no chain of co-authors links one group to another.">
                <div className="grid gap-4 md:grid-cols-2">
                  {p.groups.map((g) => (
                    <div key={g.componentId} className="rounded-lg border border-rule bg-sheet p-4">
                      <p className="text-sm text-graphite">{g.authors.length} author{g.authors.length === 1 ? '' : 's'}</p>
                      <p className="mt-1 font-serif leading-relaxed">{g.authors.join(', ')}</p>
                    </div>
                  ))}
                </div>
              </Section>
            </>
          )
        }}
      </Loaded>
    </Page>
  )
}
````

### frontend/src/pages/Sessions.tsx

````tsx
// Sessions: what was asked and saved before, kept in the graph, and which new papers touch those topics since.
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import AnswerView from '../components/AnswerView'
import { when } from '../format'
import { Empty, Loaded, Page, PaperRef, Section } from '../ui'
import { useData, useWorkspace } from '../workspace'

function SessionDetail({ id }: { id: string }) {
  const { ws, setSessionId } = useWorkspace()
  const navigate = useNavigate()
  const detail = useData(() => api.session(ws, id), [ws, id])
  const news = useData(() => api.whatsNew(ws, id), [ws, id])
  const [open, setOpen] = useState<string | null>(null)

  return (
    <div>
      <button onClick={() => { setSessionId(id); navigate('/ask') }}
              className="mb-6 rounded-md bg-pen px-4 py-2 text-white hover:bg-[#233d96]">
        Continue this session
      </button>

      <Section title="New since you asked" count={news.data?.length}
               note="Papers added after a question, connected to something that question was about.">
        <Loaded state={news} what="Checking for new papers">
          {(rows) => rows.length ? (
            <ul className="space-y-2">
              {rows.map((r, i) => (
                <li key={i}>
                  <PaperRef id={r.paper_id} full /> <span className="text-graphite">{r.relation.toLowerCase().replaceAll('_', ' ')} {r.topic}, which you asked about in “{r.earlier_question}”</span>
                </li>
              ))}
            </ul>
          ) : <Empty>Nothing new touches this session’s topics.</Empty>}
        </Loaded>
      </Section>

      <Loaded state={detail} what="Loading the session">
        {(d) => (
          <>
            <Section title="Saved insights" count={d.insights.length}>
              {d.insights.length ? (
                <ul className="space-y-3">
                  {d.insights.map((x) => (
                    <li key={x.id} className="border-l-2 border-highlight pl-3">
                      <p className="font-serif leading-relaxed">{x.text}</p>
                      <p className="text-sm text-graphite">{when(x.saved_at)}{x.about.length ? `, about ${x.about.join(', ')}` : ''}</p>
                    </li>
                  ))}
                </ul>
              ) : <Empty>No insights saved. Use “Save as insight” under an answer on the Ask page.</Empty>}
            </Section>

            <Section title="Questions" count={d.history.length}>
              {d.history.length ? (
                <ul className="divide-y divide-rule">
                  {d.history.map((h) => (
                    <li key={h.id} className="py-3">
                      <button onClick={() => setOpen(open === h.id ? null : h.id)} aria-expanded={open === h.id}
                              className="w-full text-left">
                        <span className="font-semibold">{h.question}</span>
                        <span className="ml-2 text-sm text-graphite">{when(h.asked_at)}</span>
                      </button>
                      {open === h.id && <div className="mt-3"><AnswerView answer={h.answer} id={h.id} /></div>}
                    </li>
                  ))}
                </ul>
              ) : <Empty>No questions asked in this session.</Empty>}
            </Section>
          </>
        )}
      </Loaded>
    </div>
  )
}

export default function Sessions() {
  const { ws, sessionId } = useWorkspace()
  const list = useData(ws ? () => api.sessions(ws) : null, [ws])
  const [picked, setPicked] = useState<string | null>(null)
  const current = picked ?? sessionId ?? list.data?.[0]?.id ?? null

  return (
    <Page wide title="Research sessions" intro="Every question, its answer and your saved insights are nodes in this workspace’s graph, linked to the papers and methods they are about. So the agent can recall them, and can tell you what changed since.">
      <Loaded state={list} what="Loading sessions">
        {(sessions) => sessions.length === 0 ? <Empty>No sessions yet. Ask a question to start one.</Empty> : (
          <div className="grid gap-8 lg:grid-cols-[300px_minmax(0,1fr)]">
            <nav aria-label="Sessions">
              <ul className="space-y-1">
                {sessions.map((s) => (
                  <li key={s.id}>
                    <button onClick={() => setPicked(s.id)} aria-current={s.id === current}
                            className={`w-full rounded-md px-3 py-2 text-left ${s.id === current ? 'bg-sheet ring-1 ring-rule' : 'hover:bg-sheet/60'}`}>
                      <span className="block truncate font-serif text-[16px]">{s.title || 'Untitled session'}</span>
                      <span className="text-[13px] text-graphite">{when(s.started_at)}, {s.questions} question{s.questions === 1 ? '' : 's'}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </nav>
            {current && <SessionDetail key={current} id={current} />}
          </div>
        )}
      </Loaded>
    </Page>
  )
}
````

## Run it and check

You need two terminals, plus FalkorDB (Docker) and Ollama running.

```
:: terminal 1, in backend\ with the venv active
python -m uvicorn app.api.main:app --port 8000

:: terminal 2, in frontend\
npm run dev
```

Open http://localhost:5173 and pick the `demo` workspace (or `agents`) in the sidebar. You should see:

1. **Library.**
   - Year rows from 2021 to 2026, with the cited-only papers (HotpotQA, DPR, NarmadaQA, LinkLite) dashed in the
     first row.
   - Click **HopLens**: the panel opens and the map dims everything else. Click **reproduces** in the legend: one
     edge is left (Revisiting Graph Gains to GraphWalker-QA).
2. **Ask.**
   - Click "Is HopLens really state of the art?". The steps tick off on the right, and the answer starts "No".
   - Facts 1 and 2 are GraphFuse 46.3 and 41.2. Facts 3 and 4 are the missing citations (scores 10 and 5).
   - Open **sota_check** on the right to see its Cypher. With Ollama on, the answer is written by llama3.2 and the
     note under it says so.
   - On `demo` and `agents` the facts carry highlighted passages from the PDFs. `gold` has no PDFs indexed, so it
     shows none.
3. **Save as insight**, then ask "What did I save earlier?". The insight comes back as a fact.
4. **Compare papers.**
   - It opens on GraphWalker-QA and Revisiting Graph Gains: cites as *reproduces*, shared author Jonas Weber,
     dataset KaveriHop.
   - It also shows a *Contradicts* claim pair and four re-runs.
5. **Leaderboards.** Choose TriHop-Bench, then 4-hop: GraphFuse shows 19.4 with "Corrected by an erratum: the paper
   first published 22.7".
6. **Disagreements, Citation check, Research gaps, People, Sessions** each show their findings with plain-language
   notes.
7. **Live pipeline.**
   - Click **+** next to the workspace, name it `live`, then drop the 12 PDFs from `corpus\pdf`.
   - The board shows parser-1, extractor-1, linker-1 and critic-1 working in waves, and the map grows as papers are
     parsed. With Ollama this takes about 3 minutes, as in Step 33.
8. **FalkorDB down.** Run `docker stop <name>` and the red banner appears within 4 seconds. Run `docker start <name>`
   and the page reloads by itself.

## Troubleshooting

- **"The API is not running".** Start uvicorn (terminal 1). Vite forwards `/api` to `127.0.0.1:8000`.
- **Everything says "Waiting for FalkorDB".** Run `docker start <name>`, and check `docker ps`.
- **Upload to an existing workspace.** It adds the PDFs again to that graph. Use a new workspace for the live demo.
- **Fonts look like Georgia.** The two `@fontsource-variable` packages are not installed. Run the npm install from
  step 1 of the prompt again.
- **A blank page.** Open the browser console (F12). A TypeScript error would have shown in `npx tsc -b`, so rerun it.

Suggested commit message (only when you say "commit"):
`Stage 6: React UI - library map, live pipeline board, streamed agent with Cypher and evidence, analysis views`
