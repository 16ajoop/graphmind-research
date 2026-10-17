// Sessions: what was asked and saved before, kept in the graph, and which new papers touch those topics since.
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import AnswerView from '../components/AnswerView'
import { when } from '../format'
import { Empty, Loaded, Page, PaperRef, Section } from '../ui'
import { useData, useWorkspace } from '../workspace'

function SessionDetail({ id }: { id: string }) {
  const { ws, setSessionId } = useWorkspace()
  const navigate = useNavigate()
  const detail = useData(() => api.session(ws, id), [ws, id])
  const news = useData(() => api.whatsNew(ws, id), [ws, id])
  const [open, setOpen] = useState<string | null>(null)

  return (
    <div>
      <button onClick={() => { setSessionId(id); navigate('/ask') }}
              className="mb-6 rounded-md bg-pen px-4 py-2 text-white hover:bg-[#233d96]">
        Continue this session
      </button>

      <Section title="New since you asked" count={news.data?.length}
               note="Papers added after a question, connected to something that question was about.">
        <Loaded state={news} what="Checking for new papers">
          {(rows) => rows.length ? (
            <ul className="space-y-2">
              {rows.map((r, i) => (
                <li key={i}>
                  <PaperRef id={r.paper_id} full /> <span className="text-graphite">{r.relation.toLowerCase().replaceAll('_', ' ')} {r.topic}, which you asked about in “{r.earlier_question}”</span>
                </li>
              ))}
            </ul>
          ) : <Empty>Nothing new touches this session’s topics.</Empty>}
        </Loaded>
      </Section>

      <Loaded state={detail} what="Loading the session">
        {(d) => (
          <>
            <Section title="Saved insights" count={d.insights.length}>
              {d.insights.length ? (
                <ul className="space-y-3">
                  {d.insights.map((x) => (
                    <li key={x.id} className="border-l-2 border-highlight pl-3">
                      <p className="font-serif leading-relaxed">{x.text}</p>
                      <p className="text-sm text-graphite">{when(x.saved_at)}{x.about.length ? `, about ${x.about.join(', ')}` : ''}</p>
                    </li>
                  ))}
                </ul>
              ) : <Empty>No insights saved. Use “Save as insight” under an answer on the Ask page.</Empty>}
            </Section>

            <Section title="Questions" count={d.history.length}>
              {d.history.length ? (
                <ul className="divide-y divide-rule">
                  {d.history.map((h) => (
                    <li key={h.id} className="py-3">
                      <button onClick={() => setOpen(open === h.id ? null : h.id)} aria-expanded={open === h.id}
                              className="w-full text-left">
                        <span className="font-semibold">{h.question}</span>
                        <span className="ml-2 text-sm text-graphite">{when(h.asked_at)}</span>
                      </button>
                      {open === h.id && <div className="mt-3"><AnswerView answer={h.answer} id={h.id} /></div>}
                    </li>
                  ))}
                </ul>
              ) : <Empty>No questions asked in this session.</Empty>}
            </Section>
          </>
        )}
      </Loaded>
    </div>
  )
}

export default function Sessions() {
  const { ws, sessionId } = useWorkspace()
  const list = useData(ws ? () => api.sessions(ws) : null, [ws])
  const [picked, setPicked] = useState<string | null>(null)
  const current = picked ?? sessionId ?? list.data?.[0]?.id ?? null

  return (
    <Page wide title="Research sessions" intro="Every question, its answer and your saved insights are nodes in this workspace’s graph, linked to the papers and methods they are about. So the agent can recall them, and can tell you what changed since.">
      <Loaded state={list} what="Loading sessions">
        {(sessions) => sessions.length === 0 ? <Empty>No sessions yet. Ask a question to start one.</Empty> : (
          <div className="grid gap-8 lg:grid-cols-[300px_minmax(0,1fr)]">
            <nav aria-label="Sessions">
              <ul className="space-y-1">
                {sessions.map((s) => (
                  <li key={s.id}>
                    <button onClick={() => setPicked(s.id)} aria-current={s.id === current}
                            className={`w-full rounded-md px-3 py-2 text-left ${s.id === current ? 'bg-sheet ring-1 ring-rule' : 'hover:bg-sheet/60'}`}>
                      <span className="block truncate font-serif text-[16px]">{s.title || 'Untitled session'}</span>
                      <span className="text-[13px] text-graphite">{when(s.started_at)}, {s.questions} question{s.questions === 1 ? '' : 's'}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </nav>
            {current && <SessionDetail key={current} id={current} />}
          </div>
        )}
      </Loaded>
    </Page>
  )
}
