// Citation check: earlier papers a paper probably should cite, citations of corrected work, and much-cited outside papers.
import { api } from '../api'
import { Chips, Empty, Loaded, Page, PaperRef, Quote, Section } from '../ui'
import { useData, useWorkspace } from '../workspace'

export default function CitationCheck() {
  const { ws } = useWorkspace()
  const state = useData(ws ? () => api.citations(ws) : null, [ws])
  return (
    <Page title="Citation check" intro="Found by graph paths, not by text similarity: an earlier paper that evaluates on the same datasets, has a look-alike method, or beat the paper’s own numbers, but is not cited.">
      <Loaded state={state} what="Checking citations">
        {(c) => (
          <>
            <Section title="Probably missing citations" count={c.missing.length}
                     note="The score adds 2 per shared dataset, 3 per similar method and 2 per stronger result; 5 or more is listed.">
              {c.missing.length ? (
                <ul className="space-y-5">
                  {c.missing.map((m, i) => (
                    <li key={i} className="grid grid-cols-[3rem_1fr] gap-x-4">
                      <span className="text-right font-serif text-2xl tabular-nums text-proof" title="score">{m.score}</span>
                      <div>
                        <p className="font-serif text-[17px]"><PaperRef id={m.citing} /> does not cite <PaperRef id={m.paper} /></p>
                        <dl className="mt-1.5 grid gap-x-4 gap-y-1 text-sm sm:grid-cols-[150px_1fr]">
                          <dt className="text-graphite">Shared datasets</dt><dd><Chips items={m.shared_datasets} /></dd>
                          <dt className="text-graphite">Similar methods</dt><dd><Chips items={m.similar_methods} /></dd>
                          <dt className="text-graphite">Stronger results</dt><dd><Chips items={m.stronger_results} /></dd>
                        </dl>
                      </div>
                    </li>
                  ))}
                </ul>
              ) : <Empty>No missing citations found.</Empty>}
            </Section>

            <Section title="Citing a corrected paper" count={c.stale.length}
                     note="The cited paper has an erratum in the library, but the citing paper uses the original.">
              {c.stale.length ? c.stale.map((s, i) => (
                <div key={i} className="mb-4">
                  <p><PaperRef id={s.paper} /> cites <PaperRef id={s.cites} />, which a later erratum corrects: <PaperRef id={s.correction} full />.</p>
                  <div className="mt-2 space-y-1.5">{s.contexts?.map((t, j) => <Quote key={j} text={t} />)}</div>
                </div>
              )) : <Empty>No paper cites corrected work.</Empty>}
            </Section>

            <Section title="Outside papers cited often" count={c.external_hubs.length}
                     note="Cited by several papers here but not in the library. Adding their PDFs would fill in the graph.">
              {c.external_hubs.length ? (
                <ul className="divide-y divide-rule">
                  {c.external_hubs.map((h) => (
                    <li key={h.id} className="flex flex-wrap items-baseline justify-between gap-2 py-2">
                      <span className="font-serif"><PaperRef id={h.id} full />{h.year ? ` (${h.year})` : ''}</span>
                      <span className="text-sm text-graphite">cited by {h.cited_by.length}</span>
                    </li>
                  ))}
                </ul>
              ) : <Empty>No outside paper is cited three or more times.</Empty>}
            </Section>
          </>
        )}
      </Loaded>
    </Page>
  )
}
