// Ask: questions to the research agent. The answer streams in step by step; every fact comes from a graph query
// and the query's Cypher is one click away. Questions and saved insights are remembered in the session's graph.
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { BookmarkPlus, Plus, SendHorizontal } from 'lucide-react'
import { api, askStream, type Answer, type ApiError, type StepEvent } from '../api'
import AnswerView from '../components/AnswerView'
import { splitAnswer } from '../format'
import StepTimeline from '../components/StepTimeline'
import { Page, Problem } from '../ui'
import { useWorkspace } from '../workspace'

type Turn = { key: string; question: string; events: StepEvent[]; answer?: Answer; running: boolean; error?: string }

const EXAMPLES = [
  'How are GraphWalker-QA and Revisiting Graph Gains related?',
  'Is HopLens really state of the art?',
  'What is the leaderboard on KaveriHop 3-hop?',
  'Where does LiteGraphFuse come from?',
  'Which claims contradict each other?',
  'Which authors bridge the groups?',
]

function SaveInsight({ turn }: { turn: Turn }) {
  const { ws, sessionId } = useWorkspace()
  const [open, setOpen] = useState(false)
  const [text, setText] = useState('')
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<ApiError>()
  if (!turn.answer || !sessionId) return null
  const about = [...new Set(turn.answer.facts.flatMap((f) => f.papers))]

  if (saved) return <p className="text-sm text-pen">Saved to this session. Ask “What did I save earlier?” to recall it.</p>
  if (!open) {
    return (
      <button
        onClick={() => { setText(splitAnswer(turn.answer!.answer).prose[0] ?? ''); setOpen(true) }}
        className="inline-flex items-center gap-1.5 rounded-md border border-rule bg-sheet px-3 py-1.5 text-sm hover:border-graphite"
      >
        <BookmarkPlus size={15} aria-hidden /> Save as insight
      </button>
    )
  }
  const save = async () => {
    try {
      await api.saveInsight(ws, sessionId, text.trim(), about)
      setSaved(true)
    } catch (e) {
      setError(e as ApiError)
    }
  }
  return (
    <div className="max-w-[68ch] space-y-2">
      <label className="block text-sm text-graphite" htmlFor={`insight-${turn.key}`}>
        Your note, linked to {about.length} paper{about.length === 1 ? '' : 's'} in the graph
      </label>
      <textarea id={`insight-${turn.key}`} value={text} onChange={(e) => setText(e.target.value)} rows={3}
                className="w-full rounded-md border border-rule bg-sheet px-3 py-2 font-serif" />
      <div className="flex gap-2">
        <button onClick={save} disabled={!text.trim()} className="rounded-md bg-pen px-3 py-1.5 text-sm text-white disabled:opacity-60">Save insight</button>
        <button onClick={() => setOpen(false)} className="rounded-md px-3 py-1.5 text-sm text-graphite hover:bg-vellum">Cancel</button>
      </div>
      <Problem error={error} />
    </div>
  )
}

export default function Ask() {
  const { ws, sessionId, setSessionId } = useWorkspace()
  const [turns, setTurns] = useState<Turn[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [question, setQuestion] = useState('')
  const [title, setTitle] = useState('')
  const [error, setError] = useState<ApiError>()
  const justCreated = useRef<string | null>(null)
  const asked = useRef(0)                      // numbers the questions asked on this page, for their keys
  const running = turns.some((t) => t.running)

  // Load the session's earlier questions (unless this page just created the session itself).
  useEffect(() => {
    if (!ws || !sessionId) { setTurns([]); setTitle(''); return }
    if (justCreated.current === sessionId) return
    let live = true
    Promise.all([api.session(ws, sessionId), api.sessions(ws)]).then(([s, all]) => {
      if (!live) return
      setTurns(s.history.map((h) => ({ key: h.id, question: h.question, events: [], answer: h.answer, running: false })))
      setTitle(all.find((x) => x.id === sessionId)?.title ?? '')
    }).catch(() => { if (live) setSessionId(null) })       // the session is gone (another workspace, or reset)
    return () => { live = false }
  }, [ws, sessionId, setSessionId])

  const update = (key: string, change: (t: Turn) => Turn) =>
    setTurns((all) => all.map((t) => (t.key === key ? change(t) : t)))

  const ask = async (text: string) => {
    const q = text.trim()
    if (!q || running) return
    setError(undefined)
    let sid = sessionId
    try {
      if (!sid) {
        sid = (await api.newSession(ws, q.slice(0, 60))).id
        justCreated.current = sid
        setSessionId(sid)
        setTitle(q.slice(0, 60))
      }
    } catch (e) {
      setError(e as ApiError)
      return
    }
    const key = `asked-${++asked.current}`
    setTurns((all) => [...all, { key, question: q, events: [], running: true }])
    setSelected(key)
    setQuestion('')
    setTimeout(() => document.getElementById(`turn-${key}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 50)
    try {
      await askStream(ws, sid, q, (e) => {
        update(key, (t) => ({
          ...t,
          events: [...t.events, e],
          answer: e.step === 'final' ? { answer: e.answer, source: e.source, facts: e.facts, evidence: e.evidence } : t.answer,
          error: e.step === 'error' ? e.detail : t.error,
        }))
        if (e.step === 'final') {      // now the answer is long enough to scroll the question to the top
          setTimeout(() => document.getElementById(`turn-${key}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 60)
        }
      })
    } catch (e) {
      update(key, (t) => ({ ...t, error: (e as ApiError).message }))
    }
    update(key, (t) => ({ ...t, running: false }))
  }

  const submit = (e: FormEvent) => { e.preventDefault(); ask(question) }
  const newSession = () => { justCreated.current = null; setSessionId(null); setTurns([]); setSelected(null) }
  const shown = turns.find((t) => t.key === selected) ?? turns[turns.length - 1]

  return (
    <Page
      wide
      title="Ask the library"
      intro="The agent answers from graph queries, not from memory. Each fact below an answer names the query it came from."
      actions={
        <div className="flex items-center gap-3 text-sm">
          {title && <span className="max-w-[28ch] truncate text-graphite" title={title}>Session: {title}</span>}
          <button onClick={newSession} className="inline-flex items-center gap-1.5 rounded-md border border-rule bg-sheet px-3 py-1.5 hover:border-graphite">
            <Plus size={15} aria-hidden /> New session
          </button>
        </div>
      }
    >
      <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_380px]">
        <div className="min-w-0">
          {turns.length === 0 && (
            <div className="mb-8">
              <p className="text-graphite">Try one of these on the demo corpus:</p>
              <div className="mt-3 flex flex-wrap gap-2">
                {EXAMPLES.map((x) => (
                  <button key={x} onClick={() => ask(x)} className="rounded-full border border-rule bg-sheet px-3 py-1.5 text-left font-serif hover:border-pen hover:text-pen">
                    {x}
                  </button>
                ))}
              </div>
            </div>
          )}

          <div className="space-y-10">
            {turns.map((t) => (
              <article key={t.key} id={`turn-${t.key}`} onClick={() => setSelected(t.key)}
                       className={`scroll-mt-6 border-l-2 pl-5 ${shown?.key === t.key ? 'border-pen' : 'border-transparent'}`}>
                <h2 className="font-sans text-[17px] font-semibold">{t.question}</h2>
                <div className="mt-3">
                  {t.answer ? <AnswerView answer={t.answer} id={t.key} />
                    : t.running ? <p className="text-graphite">Working through the graph…</p> : null}
                  {t.error && <p className="mt-2 text-proof">{t.error}</p>}
                </div>
                {!t.running && t.answer && t.answer.source !== 'clarify' && <div className="mt-4"><SaveInsight turn={t} /></div>}
              </article>
            ))}
          </div>

          <form onSubmit={submit} className="sticky bottom-0 mt-8 bg-gradient-to-t from-vellum from-70% to-transparent pb-5 pt-6">
            <Problem error={error} />
            <div className="flex items-end gap-2 rounded-lg border border-rule bg-sheet p-2 focus-within:border-pen">
              <label htmlFor="question" className="sr-only">Your question</label>
              <textarea
                id="question" rows={2} value={question} onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); ask(question) } }}
                placeholder="Ask how papers relate, what is state of the art, who works with whom…"
                className="flex-1 resize-none bg-transparent px-2 py-1.5 font-serif text-[17px] outline-none"
              />
              <button type="submit" disabled={running || !question.trim()}
                      className="inline-flex items-center gap-1.5 rounded-md bg-pen px-4 py-2 text-white disabled:opacity-50">
                <SendHorizontal size={16} aria-hidden /> Ask
              </button>
            </div>
          </form>
        </div>

        <aside className="lg:sticky lg:top-6 lg:max-h-[calc(100vh-3rem)] lg:self-start lg:overflow-y-auto">
          <div className="rounded-lg border border-rule bg-sheet p-5">
            <h2 className="text-lg">How the agent answered</h2>
            {shown && <p className="mt-1 truncate text-sm text-graphite" title={shown.question}>{shown.question}</p>}
            <div className="mt-4">
              {shown ? <StepTimeline events={shown.events} running={shown.running} />
                : <p className="text-sm text-graphite">Ask a question to see each step: what the agent understood, which graph queries it ran, and what it checked.</p>}
            </div>
          </div>
        </aside>
      </div>
    </Page>
  )
}
