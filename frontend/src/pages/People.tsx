// People and influence: FalkorDB's graph algorithms (PageRank, betweenness, connected components) on the library.
import { api } from '../api'
import { Empty, Loaded, Page, PaperRef, Section } from '../ui'
import { useData, useWorkspace } from '../workspace'

export default function People() {
  const { ws } = useWorkspace()
  const state = useData(ws ? () => api.people(ws) : null, [ws])
  return (
    <Page title="People and influence" intro="Computed inside FalkorDB with its built-in graph algorithms, over the citation and co-author edges.">
      <Loaded state={state} what="Running the graph algorithms">
        {(p) => {
          const topPaper = Math.max(...p.influential.map((x) => x.score), 1e-9)
          const topBridge = Math.max(...p.bridges.map((x) => x.score), 1e-9)
          return (
            <>
              <Section title="Most influential papers" note="PageRank over citations: a paper ranks high when well-cited papers cite it. Papers outside the library count too.">
                <ol className="space-y-2.5">
                  {p.influential.map((x, i) => (
                    <li key={x.id} className="grid grid-cols-[1.5rem_minmax(0,1fr)_40%] items-center gap-3">
                      <span className="text-right text-graphite tabular-nums">{i + 1}</span>
                      <span className="min-w-0 font-serif"><PaperRef id={x.id} full />{!x.in_library && <span className="font-sans text-sm text-graphite"> (cited only)</span>}</span>
                      <span className="h-2 rounded-full bg-vellum" aria-hidden>
                        <span className="block h-2 rounded-full bg-pen/70" style={{ width: `${(x.score / topPaper) * 100}%` }} />
                      </span>
                    </li>
                  ))}
                </ol>
              </Section>

              <Section title="Authors who bridge groups" note="Betweenness over co-authorship: how often an author sits on the shortest path between two others.">
                {p.bridges.length ? (
                  <ol className="space-y-2.5">
                    {p.bridges.map((b, i) => (
                      <li key={b.author} className="grid grid-cols-[1.5rem_minmax(0,1fr)_40%] items-center gap-3">
                        <span className="text-right text-graphite tabular-nums">{i + 1}</span>
                        <span className="font-serif text-[17px]">{b.author}</span>
                        <span className="h-2 rounded-full bg-vellum" aria-hidden>
                          <span className="block h-2 rounded-full bg-pen/70" style={{ width: `${(b.score / topBridge) * 100}%` }} />
                        </span>
                      </li>
                    ))}
                  </ol>
                ) : <Empty>No co-author links yet.</Empty>}
              </Section>

              <Section title="Co-author groups" count={p.groups.length} note="Connected components: no chain of co-authors links one group to another.">
                <div className="grid gap-4 md:grid-cols-2">
                  {p.groups.map((g) => (
                    <div key={g.componentId} className="rounded-lg border border-rule bg-sheet p-4">
                      <p className="text-sm text-graphite">{g.authors.length} author{g.authors.length === 1 ? '' : 's'}</p>
                      <p className="mt-1 font-serif leading-relaxed">{g.authors.join(', ')}</p>
                    </div>
                  ))}
                </div>
              </Section>
            </>
          )
        }}
      </Loaded>
    </Page>
  )
}
