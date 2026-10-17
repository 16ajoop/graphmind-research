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
