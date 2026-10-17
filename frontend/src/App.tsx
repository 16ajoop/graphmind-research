
 // The app frame: sidebar, workspace, service status, pages, theme toggle, and paper panel.
import { useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react'
import { NavLink, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import {
  BookOpen, CircleAlert, GitCompareArrows, History, Lightbulb, MessageSquare,
  Moon, Network, Plus, Quote, Sun, Trophy, Users,
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

const PAGE_TITLES: Record<string, string> = Object.fromEntries(
  PAGES.map(({ path, label }) => [`/${path}`, label]),
)

type Theme = 'light' | 'dark'

function getInitialTheme(): Theme {
  try {
    const saved = localStorage.getItem('graphmind-theme')
    if (saved === 'light' || saved === 'dark') return saved
  } catch {
    // Continue with the system preference if local storage is unavailable.
  }

  return typeof window !== 'undefined' &&
    window.matchMedia('(prefers-color-scheme: dark)').matches
    ? 'dark'
    : 'light'
}

function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(getInitialTheme)

  useEffect(() => {
    document.documentElement.dataset.theme = theme

    try {
      localStorage.setItem('graphmind-theme', theme)
    } catch {
      // The theme still works for this session if storage is unavailable.
    }
  }, [theme])

  const toggleTheme = () => {
    setTheme((current) => current === 'dark' ? 'light' : 'dark')
  }

  return (
    <button
      type="button"
      onClick={toggleTheme}
      aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
      title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
      className="inline-flex shrink-0 items-center gap-2 rounded-lg border border-rule bg-sheet px-3 py-2 text-sm font-medium text-ink shadow-sm transition hover:border-pen"
    >
      {theme === 'dark' ? <Sun size={17} /> : <Moon size={17} />}
      <span>{theme === 'dark' ? 'Light mode' : 'Dark mode'}</span>
    </button>
  )
}

/** Polls /api/health and tracks FalkorDB reconnections. */
function useHealth(): [Health | null, number] {
  const [health, setHealth] = useState<Health | null>(null)
  const [reconnects, setReconnects] = useState(0)
  const wasDown = useRef(false)

  useEffect(() => {
    let live = true

    const check = () => {
      api.health()
        .then((h) => {
          if (!live) return
          if (h.falkordb && wasDown.current) {
            setReconnects((n) => n + 1)
          }
          wasDown.current = !h.falkordb
          setHealth(h)
        })
        .catch(() => {
          if (!live) return
          wasDown.current = true
        })
    }

    check()
    const timer = setInterval(check, 4000)

    return () => {
      live = false
      clearInterval(timer)
    }
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
      <label htmlFor="workspace" className="text-[13px] text-graphite">
        Workspace
      </label>

      <div className="mt-1 flex gap-1.5">
        <select
          id="workspace"
          value={ws}
          onChange={(e) => setWs(e.target.value)}
          className="min-w-0 flex-1 rounded-md border border-rule bg-sheet px-2 py-1.5 text-ink"
        >
          {!workspaces.includes(ws) && (
            <option value={ws}>{ws || 'none yet'}</option>
          )}
          {workspaces.map((w) => (
            <option key={w} value={w}>{w}</option>
          ))}
        </select>

        <button
          type="button"
          onClick={() => setAdding(!adding)}
          aria-label="New workspace"
          aria-expanded={adding}
          className="rounded-md border border-rule bg-sheet px-2 text-ink hover:border-graphite"
        >
          <Plus size={16} />
        </button>
      </div>

      {adding && (
        <form onSubmit={add} className="mt-2">
          <label htmlFor="new-ws" className="text-[13px] text-graphite">
            Name: a to z, 0 to 9 and _
          </label>

          <div className="mt-1 flex gap-1.5">
            <input
              id="new-ws"
              value={name}
              onChange={(e) => setName(e.target.value.toLowerCase())}
              pattern="[a-z0-9_]{1,32}"
              required
              className="min-w-0 flex-1 rounded-md border border-rule bg-sheet px-2 py-1.5 text-ink"
            />
            <button className="rounded-md bg-pen px-2.5 text-sm text-white">
              Create
            </button>
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

  const line = (state: 'ok' | 'down' | 'off', text: string) => (
    <li className="flex items-center gap-2">
      <span
        className={`h-2 w-2 shrink-0 rounded-full ${
          state === 'ok'
            ? 'bg-[#3f8a3a]'
            : state === 'down'
              ? 'bg-proof'
              : 'border border-graphite'
        }`}
        aria-hidden="true"
      />
      {text}
    </li>
  )

  return (
    <ul className="space-y-1 border-t border-rule px-4 py-3 text-[13px] text-graphite">
      {line(
        health.falkordb ? 'ok' : 'down',
        health.falkordb ? 'FalkorDB connected' : 'FalkorDB not reachable',
      )}
      {line(
        health.ollama ? 'ok' : 'off',
        health.ollama ? 'Ollama connected' : 'Ollama off: template answers',
      )}
      {health.agents.includes(ws) && line('ok', 'Pipeline agents running here')}
    </ul>
  )
}

export default function App() {
  const [health, reconnects] = useHealth()
  const down = health !== null && !health.falkordb
  const location = useLocation()
  const pageTitle = PAGE_TITLES[location.pathname] ?? 'GraphMind Research'

  return (
    <div className="flex min-h-screen flex-col bg-vellum text-ink md:h-screen md:flex-row">
      <aside className="flex shrink-0 flex-col border-b border-rule bg-vellum md:w-60 md:border-b-0 md:border-r">
        <div className="flex items-center gap-2.5 px-4 py-5">
          <Network size={22} className="text-pen" aria-hidden="true" />
          <div>
            <div className="font-serif text-lg font-semibold leading-none">
              GraphMind
            </div>
            <div className="mt-1 text-[13px] text-graphite">
              Papers as a graph
            </div>
          </div>
        </div>

        <WorkspacePicker />

        <nav
          className="mt-5 flex gap-1 overflow-x-auto px-2 pb-2 md:flex-1 md:flex-col md:overflow-visible md:pb-0"
          aria-label="Pages"
        >
          {PAGES.map(({ path, label, icon: Icon }) => (
            <NavLink
              key={path}
              to={`/${path}`}
              className={({ isActive }) =>
                `flex shrink-0 items-center gap-2.5 rounded-lg px-3 py-2 transition ${
                  isActive
                    ? 'bg-sheet font-semibold text-ink ring-1 ring-rule'
                    : 'text-graphite hover:bg-sheet/60 hover:text-ink'
                }`
              }
            >
              <Icon size={17} aria-hidden="true" />
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="hidden md:block">
          <Status health={health} />
        </div>
      </aside>

      <main
        className="relative flex-1 overflow-x-hidden bg-vellum md:overflow-y-auto"
        key={reconnects}
      >
        <header className="sticky top-0 z-20 flex items-center justify-between gap-3 border-b border-rule bg-vellum/95 px-5 py-3 backdrop-blur md:px-8">
          <div className="min-w-0">
            <h1 className="truncate font-serif text-xl font-semibold text-ink">
              {pageTitle}
            </h1>
            <p className="mt-0.5 text-xs text-graphite">
              GraphMind Research Workspace
            </p>
          </div>
          <ThemeToggle />
        </header>

        {down && (
          <div
            className="sticky top-[65px] z-30 border-b border-proof/30 bg-proof-soft px-5 py-3 md:px-10"
            role="alert"
          >
            <p className="font-semibold text-proof">
              FalkorDB is not reachable
            </p>
            <p className="text-sm">
              Every page reads the knowledge graph, so the API answers 503 until
              it is back. Start it with{' '}
              <code className="font-mono">docker start &lt;name&gt;</code>;
              this page reconnects by itself.
            </p>
          </div>
        )}

        <Routes>
          <Route path="/" element={<Navigate to="/library" replace />} />
          {PAGES.map(({ path, element }) => (
            <Route key={path} path={`/${path}`} element={element} />
          ))}
          <Route path="*" element={<Navigate to="/library" replace />} />
        </Routes>
      </main>

      <PaperPanel />
    </div>
  )
}
