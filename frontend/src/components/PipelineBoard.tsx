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
