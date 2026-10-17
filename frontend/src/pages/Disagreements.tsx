// Disagreements: claims the numbers do not back up, and claims that contradict, qualify or support each other.
import { api } from '../api'
import { Empty, Loaded, Page, PaperRef, Relation, Section } from '../ui'
import { useData, useWorkspace } from '../workspace'

export default function Disagreements() {
  const { ws } = useWorkspace()
  const state = useData(ws ? () => api.claims(ws) : null, [ws])
  return (
    <Page title="Disagreements" intro="Where papers disagree with each other, or with the numbers. Claim pairs are chosen by the graph (the newer paper cites the older one, about the same method); the local model only judges how they relate.">
      <Loaded state={state} what="Comparing claims">
        {(c) => (
          <>
            <Section title="State-of-the-art claims the numbers contradict" count={c.sota.length}
                     note="A paper claims to be best, but an earlier paper in the library reports a higher number on the same split.">
              {c.sota.length ? (
                <ul className="space-y-4">
                  {c.sota.map((s, i) => (
                    <li key={i} className="border-l-2 border-proof pl-4">
                      <p className="font-serif text-[17px] leading-relaxed">
                        <PaperRef id={s.paper} /> claims the best result on {s.dataset} {s.split} with{' '}
                        <span className="tabular-nums">{s.claimed_value}</span>, but {s.better_method} reports{' '}
                        <span className="font-semibold tabular-nums">{s.better_value}</span> in the <PaperRef id={s.better_paper} /> paper.
                      </p>
                    </li>
                  ))}
                </ul>
              ) : <Empty>Every state-of-the-art claim holds against the numbers in the library.</Empty>}
            </Section>

            <Section title="Claims that contradict or qualify each other" count={c.conflicts.length}>
              {c.conflicts.length ? c.conflicts.map((x, i) => (
                <div key={i} className="mb-6 grid gap-3 md:grid-cols-[1fr_auto_1fr] md:items-start">
                  <div>
                    <p className="font-serif leading-relaxed">{x.text}</p>
                    <p className="mt-1 text-sm"><PaperRef id={x.paper} /></p>
                  </div>
                  <div className="md:pt-0.5"><Relation name={x.relation} /></div>
                  <div>
                    <p className="font-serif leading-relaxed">{x.other_text}</p>
                    <p className="mt-1 text-sm"><PaperRef id={x.other_paper} /></p>
                  </div>
                  {x.basis && <p className="text-sm text-graphite md:col-span-3">Why: {x.basis}</p>}
                </div>
              )) : <Empty>No conflicting claims found.</Empty>}
            </Section>

            <Section title="Claims supported by later work" count={c.support.length}>
              {c.support.length ? (
                <ul className="divide-y divide-rule">
                  {c.support.map((s, i) => (
                    <li key={i} className="py-2.5">
                      <p><PaperRef id={s.paper} /> <Relation name="SUPPORTS" /> <PaperRef id={s.supported_paper} /></p>
                      {s.basis && <p className="mt-1 text-sm text-graphite">{s.basis}</p>}
                    </li>
                  ))}
                </ul>
              ) : <Empty>No supporting claims found yet.</Empty>}
            </Section>
          </>
        )}
      </Loaded>
    </Page>
  )
}
