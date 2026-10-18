// Every call the UI makes to the FastAPI backend (backend/app/api/main.py). Vite forwards /api to :8000.

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}


const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ''
const apiUrl = (path: string) => `${API_BASE}/api${path}`
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let r: Response
  try {
    r = await fetch(apiUrl(path), init)
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
    const r = await fetch(apiUrl('/health')).catch(() => null)
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
    r = await fetch(apiUrl(`${ws(w)}/sessions/${sid}/ask`), { ...json({ question }), signal })
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
