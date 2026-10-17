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
