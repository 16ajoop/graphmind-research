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
