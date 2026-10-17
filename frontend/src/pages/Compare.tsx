// Compare: everything the graph knows that connects two papers, path by path.
import { useState } from 'react'
import { api } from '../api'
import { shortTitle } from '../intents'
import { Chips, Empty, IntentTag, Loaded, Page, PaperRef, Quote, Relation, Section } from '../ui'
import { useData, useWorkspace } from '../workspace'

function Picker({ label, value, onChange, options }: {
  label: string; value: string; onChange: (v: string) => void; options: { id: string; title: string }[]
}) {
  return (
    <label className="flex min-w-[260px] flex-1 flex-col gap-1 text-sm text-graphite">
      {label}
      <select value={value} onChange={(e) => onChange(e.target.value)}
              className="rounded-md border border-rule bg-sheet px-3 py-2 font-serif text-[16px] text-ink">
        {options.map((o) => <option key={o.id} value={o.id}>{o.title}</option>)}
      </select>
    </label>
  )
}

export default function Compare() {
  const { ws } = useWorkspace()
  const papers = useData(ws ? () => api.papers(ws) : null, [ws])
  const [chosenA, setA] = useState('')
  const [chosenB, setB] = useState('')

  // Until the reader picks, start on the pair the demo is about if it is here, else the first two papers.
  const list = papers.data ?? []
  const find = (name: string) => list.find((p) => p.title.startsWith(name))?.id
  const a = chosenA || find('GraphWalker-QA') || list[0]?.id || ''
  const b = chosenB || find('Revisiting Graph Gains') || list[1]?.id || ''

  const pair = useData(a && b && a !== b ? () => api.pair(ws, a, b) : null, [ws, a, b])
  const options = (papers.data ?? []).map((p) => ({ id: p.id, title: `${shortTitle(p.title)} (${p.year})` }))

  return (
    <Page title="Compare two papers" intro="Citations between them, the people and datasets they share, method lineage, claims that agree or clash, and results one re-ran from the other.">
      <Loaded state={papers} what="Loading papers">
        {() => (
          <div className="mb-8 flex flex-wrap gap-4">
            <Picker label="First paper" value={a} onChange={setA} options={options} />
            <Picker label="Second paper" value={b} onChange={setB} options={options} />
          </div>
        )}
      </Loaded>
      {a && a === b && <Empty>Pick two different papers.</Empty>}
      {a && b && a !== b && (
        <Loaded state={pair} what="Following the paths between them">
          {(r) => {
            const shared = [
              ['Shared authors', r.shared_authors?.authors],
              ['Datasets both evaluate on', r.shared_datasets?.datasets],
              ['Methods both use or propose', r.shared_methods?.methods],
            ] as const
            const nothing = !r.citations.length && !r.lineage.length && !r.claims.length && !r.result_links.length
              && !r.quotes.length && shared.every(([, x]) => !x?.length)
            if (nothing) return <Empty>The graph has no path between these two papers.</Empty>
            return (
              <>
                <Section title="Citations between them" count={r.citations.length}>
                  {r.citations.length ? r.citations.map((c, i) => (
                    <div key={i} className="mb-4">
                      <p><PaperRef id={c.citing} /> cites <PaperRef id={c.cited} />, as <IntentTag intent={c.intent} /></p>
                      <div className="mt-2 space-y-1.5">{c.contexts?.map((t, j) => <Quote key={j} text={t} />)}</div>
                    </div>
                  )) : <p className="text-graphite">Neither cites the other.</p>}
                </Section>

                <Section title="What they share">
                  <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-[220px_1fr]">
                    {shared.map(([label, items]) => (
                      <div key={label} className="contents">
                        <dt className="text-graphite">{label}</dt>
                        <dd><Chips items={items ? [...items] : []} /></dd>
                      </div>
                    ))}
                  </dl>
                </Section>

                {r.lineage.length > 0 && (
                  <Section title="Method lineage">
                    {r.lineage.map((l, i) => (
                      <p key={i} className="mb-2 font-serif text-[17px]">
                        {l.chain.map((m, j) => (
                          <span key={j}>{j > 0 && <span className="px-1.5 font-sans text-sm text-graphite">extends</span>}{m}</span>
                        ))}
                      </p>
                    ))}
                  </Section>
                )}

                {r.claims.length > 0 && (
                  <Section title="Their claims" count={r.claims.length}>
                    {r.claims.map((c, i) => (
                      <div key={i} className="mb-5 grid gap-3 md:grid-cols-[1fr_auto_1fr] md:items-start">
                        <p className="font-serif leading-relaxed">{c.claim_a}</p>
                        <div className="md:pt-0.5"><Relation name={c.relation} /></div>
                        <p className="font-serif leading-relaxed">{c.claim_b}</p>
                        <p className="text-sm text-graphite md:col-span-3">Why: {c.basis}</p>
                      </div>
                    ))}
                  </Section>
                )}

                {r.result_links.length > 0 && (
                  <Section title="Results re-run" count={r.result_links.length}>
                    <table className="w-full text-left">
                      <thead className="text-sm text-graphite">
                        <tr><th className="py-1.5 font-normal">Method</th><th className="font-normal">Split</th><th className="text-right font-normal">Original</th><th className="text-right font-normal">Re-run</th><th className="pl-4 font-normal">Outcome</th></tr>
                      </thead>
                      <tbody className="divide-y divide-rule">
                        {r.result_links.map((x, i) => (
                          <tr key={i}>
                            <td className="py-2">{x.method}</td>
                            <td>{x.split}{x.setting && <div className="text-[13px] text-graphite">{x.setting}</div>}</td>
                            <td className="text-right tabular-nums">{x.original_value}</td>
                            <td className="text-right tabular-nums">{x.new_value}</td>
                            <td className="pl-4"><Relation name={x.relation} /></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </Section>
                )}

                {r.quotes.length > 0 && (
                  <Section title="Numbers one quotes from the other" count={r.quotes.length}>
                    <ul className="space-y-1">
                      {r.quotes.map((x, i) => <li key={i}>{x.method} on {x.dataset} {x.split}: <span className="tabular-nums">{x.value}</span></li>)}
                    </ul>
                  </Section>
                )}
              </>
            )
          }}
        </Loaded>
      )}
    </Page>
  )
}
