import { useEffect, useState } from 'react'
import { NavLink, Navigate, Route, Routes } from 'react-router-dom'
import {
  Activity, BookOpen, FlaskConical, GitCompareArrows, History, MessageSquare, Trophy, Users,
  type LucideIcon,
} from 'lucide-react'

// One entry per screen in the demo. Each page is a placeholder until Stage 6 fills it in.
const PAGES: { path: string; label: string; icon: LucideIcon; note: string }[] = [
  { path: 'library', label: 'Library', icon: BookOpen, note: 'Papers and the citation map, coloured by intent.' },
  { path: 'ask', label: 'Ask', icon: MessageSquare, note: 'Questions answered from graph paths, with passages.' },
  { path: 'leaderboards', label: 'Leaderboards', icon: Trophy, note: 'One authoritative number per method, errata applied.' },
  { path: 'disagreements', label: 'Disagreements', icon: GitCompareArrows, note: 'Claims that contradict or qualify each other.' },
  { path: 'gaps', label: 'Gaps', icon: FlaskConical, note: 'Methods never tested on a dataset, unreproduced results.' },
  { path: 'people', label: 'People', icon: Users, note: 'Influential papers, bridge authors, isolated groups.' },
  { path: 'pipeline', label: 'Pipeline', icon: Activity, note: 'Jobs moving through parse, extract, link, critique.' },
  { path: 'sessions', label: 'Sessions', icon: History, note: 'Saved insights and what is new since last time.' },
]

type ApiState = 'checking' | 'online' | 'offline'

function useApiStatus(): ApiState {
  const [state, setState] = useState<ApiState>('checking')
  useEffect(() => {
    // The backend API arrives in Stage 6; until then this shows "offline", which proves the proxy is wired.
    fetch('/api/health')
      .then((r) => setState(r.ok ? 'online' : 'offline'))
      .catch(() => setState('offline'))
  }, [])
  return state
}

function Placeholder({ label, note }: { label: string; note: string }) {
  return (
    <div className="p-8">
      <h1 className="text-2xl font-semibold text-slate-900">{label}</h1>
      <p className="mt-2 text-slate-600">{note}</p>
      <p className="mt-6 inline-block rounded border border-dashed border-slate-300 px-3 py-2 text-sm text-slate-500">
        Placeholder: built in Stage 6.
      </p>
    </div>
  )
}

export default function App() {
  const api = useApiStatus()
  const dot = { checking: 'bg-slate-400', online: 'bg-emerald-500', offline: 'bg-rose-500' }[api]
  return (
    <div className="flex h-screen bg-slate-50">
      <aside className="flex w-56 flex-col border-r border-slate-200 bg-white">
        <div className="px-4 py-5">
          <div className="text-lg font-semibold text-slate-900">GraphMind</div>
          <div className="text-xs text-slate-500">Research papers as a graph</div>
        </div>
        <nav className="flex-1 space-y-1 px-2">
          {PAGES.map(({ path, label, icon: Icon }) => (
            <NavLink
              key={path}
              to={`/${path}`}
              className={({ isActive }) =>
                `flex items-center gap-2 rounded px-3 py-2 text-sm ${
                  isActive ? 'bg-slate-900 text-white' : 'text-slate-700 hover:bg-slate-100'
                }`
              }
            >
              <Icon size={16} /> {label}
            </NavLink>
          ))}
        </nav>
        <div className="flex items-center gap-2 border-t border-slate-200 px-4 py-3 text-xs text-slate-600">
          <span className={`h-2 w-2 rounded-full ${dot}`} /> API {api}
        </div>
      </aside>
      <main className="flex-1 overflow-auto">
        <Routes>
          <Route path="/" element={<Navigate to="/library" replace />} />
          {PAGES.map(({ path, label, note }) => (
            <Route key={path} path={`/${path}`} element={<Placeholder label={label} note={note} />} />
          ))}
          <Route path="*" element={<Navigate to="/library" replace />} />
        </Routes>
      </main>
    </div>
  )
}
