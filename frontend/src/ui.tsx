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
