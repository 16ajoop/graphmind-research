// Research gaps: what nobody in the library has tried yet, read from missing edges in the graph.
import { api } from '../api'
import { shortTitle } from '../intents'
import { Chips, Empty, Loaded, Page, PaperRef, Section } from '../ui'
import { useData, useWorkspace } from '../workspace'

export default function Gaps() {
  const { ws, titles } = useWorkspace()
  const state = useData(ws ? () => api.gaps(ws) : null, [ws])
  return (
    <Page title="Research gaps" intro="Each gap is a missing edge: a method with no result on a dataset, a metric no one reports, a result no one has re-run.">
      <Loaded state={state} what="Looking for gaps">
        {(g) => {
          const untested = g.gap_method_dataset.filter((m) => m.never_evaluated_on.length)
          const metrics = g.gap_metric_coverage.filter((m) => m.never_reported_on.length)
          return (
            <>
              <Section title="Methods never tested on a dataset" count={untested.length}>
                {untested.length ? (
                  <table className="w-full text-left">
                    <thead className="text-sm text-graphite">
                      <tr><th className="w-1/4 py-1.5 font-normal">Method</th><th className="font-normal">Never evaluated on</th><th className="hidden font-normal md:table-cell">Tested on</th></tr>
                    </thead>
                    <tbody className="divide-y divide-rule">
                      {untested.map((m) => (
                        <tr key={m.method} className="align-top">
                          <td className="py-2.5 pr-4 font-serif font-semibold">{m.method}</td>
                          <td className="py-2.5 pr-4"><Chips items={m.never_evaluated_on} /></td>
                          <td className="hidden py-2.5 text-sm text-graphite md:table-cell">{m.evaluated_on.join(', ')}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : <Empty>Every method has been tested on every dataset.</Empty>}
              </Section>

              <Section title="Results nobody has reproduced" count={g.gap_unreproduced.length}>
                {g.gap_unreproduced.length ? (
                  <ul className="flex flex-wrap gap-x-6 gap-y-2">
                    {g.gap_unreproduced.map((u) => (
                      <li key={u.method} className="font-serif">
                        {u.method === shortTitle(titles[u.paper]) ? <PaperRef id={u.paper} />
                          : <>{u.method} <span className="font-sans text-sm text-graphite">from</span> <PaperRef id={u.paper} /></>}
                      </li>
                    ))}
                  </ul>
                ) : <Empty>Every proposed method has been reproduced at least once.</Empty>}
              </Section>

              <Section title="Metrics missing on some datasets" count={metrics.length}>
                {metrics.length ? (
                  <ul className="space-y-2">
                    {metrics.map((m) => (
                      <li key={m.metric}><span className="font-semibold">{m.metric}</span> <span className="text-graphite">is never reported on</span> <Chips items={m.never_reported_on} /></li>
                    ))}
                  </ul>
                ) : <Empty>Every metric is reported on every dataset.</Empty>}
              </Section>

              <Section title="Datasets and their splits" count={g.gap_dataset_depth.length} note="Few splits or a single language means few kinds of question are covered.">
                <ul className="space-y-2">
                  {g.gap_dataset_depth.map((d) => (
                    <li key={d.dataset}>
                      <span className="font-serif font-semibold">{d.dataset}</span>
                      <span className="text-graphite">{d.language ? `, ${d.language}` : ''}: </span>
                      <Chips items={d.splits} empty="no splits recorded" />
                    </li>
                  ))}
                </ul>
              </Section>

              {g.gap_task_without_method.length > 0 && (
                <Section title="Tasks claims talk about but no paper here tackles" count={g.gap_task_without_method.length}>
                  <ul className="space-y-2">
                    {g.gap_task_without_method.map((t) => (
                      <li key={t.task}>
                        <span className="font-serif font-semibold">{t.task}</span>
                        <span className="text-graphite">: only outside methods ({t.external_methods.join(', ')}), mentioned in {t.claims.length} claim{t.claims.length === 1 ? '' : 's'}</span>
                      </li>
                    ))}
                  </ul>
                </Section>
              )}
            </>
          )
        }}
      </Loaded>
    </Page>
  )
}
