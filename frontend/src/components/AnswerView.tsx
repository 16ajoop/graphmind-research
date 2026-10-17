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
