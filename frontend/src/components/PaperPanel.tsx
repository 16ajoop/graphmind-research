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
