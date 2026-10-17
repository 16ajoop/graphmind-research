// Library: drop PDFs in, watch the four agents read them, and see the papers appear on the citation map.
import { useEffect, useRef, useState } from 'react'
import { FileUp } from 'lucide-react'
import { api, type ApiError, type Job } from '../api'
import LibraryMap from '../components/LibraryMap'
import PipelineBoard from '../components/PipelineBoard'
import { Empty, Loaded, Page, PaperRef, Problem, Section } from '../ui'
import { useData, useWorkspace } from '../workspace'

function DropZone({ onFiles, busy }: { onFiles: (files: File[]) => void; busy: boolean }) {
  const [over, setOver] = useState(false)
  const input = useRef<HTMLInputElement>(null)
  const take = (list: FileList | null) => {
    const pdfs = [...(list ?? [])].filter((f) => f.name.toLowerCase().endsWith('.pdf'))
    if (pdfs.length) onFiles(pdfs)
  }
  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setOver(true) }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => { e.preventDefault(); setOver(false); take(e.dataTransfer.files) }}
      className={`flex flex-wrap items-center gap-4 rounded-lg border-2 border-dashed px-5 py-4 ${over ? 'border-pen bg-pen-soft' : 'border-rule bg-sheet'}`}
    >
      <FileUp size={22} className="text-pen" aria-hidden />
      <p className="flex-1">
        <span className="font-semibold">Drop research papers here</span>
        <span className="text-graphite"> (PDF). The agents read them and add them to this workspace’s graph.</span>
      </p>
      <input ref={input} type="file" accept="application/pdf" multiple hidden onChange={(e) => { take(e.target.files); e.target.value = '' }} />
      <button
        onClick={() => input.current?.click()}
        disabled={busy}
        className="rounded-md bg-pen px-4 py-2 text-white hover:bg-[#233d96] disabled:opacity-60"
      >
        {busy ? 'Uploading…' : 'Choose PDFs'}
      </button>
    </div>
  )
}

export default function Library() {
  const { ws, refreshTitles, refreshWorkspaces } = useWorkspace()
  const [jobs, setJobs] = useState<Job[]>([])
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState<ApiError>()
  // Poll the job board while any job is unfinished. Each time a paper gets past a stage, reload the map and the list.
  const progress = jobs.reduce((n, j) => n + j.history.length, 0)
  const graph = useData(ws ? () => api.libraryGraph(ws) : null, [ws, progress])
  const papers = useData(ws ? () => api.papers(ws) : null, [ws, progress])
  const unfinished = jobs.some((j) => j.status === 'ready' || j.status === 'running')
  useEffect(() => {
    if (!ws) return
    let live = true
    const tick = () => api.jobs(ws).then((j) => { if (live) setJobs(j) }).catch(() => { if (live) setJobs([]) })
    tick()
    if (!unfinished) return () => { live = false }
    const timer = setInterval(tick, 1000)
    return () => { live = false; clearInterval(timer) }
  }, [ws, unfinished])
  useEffect(() => { if (progress) refreshTitles() }, [progress, refreshTitles])

  const upload = async (files: File[]) => {
    setUploading(true)
    setUploadError(undefined)
    try {
      await api.upload(ws, files)
      refreshWorkspaces()
      setJobs(await api.jobs(ws))
    } catch (e) {
      setUploadError(e as ApiError)
    } finally {
      setUploading(false)
    }
  }

  return (
    <Page
      wide
      title="Library"
      intro="Every paper in this workspace and how they cite each other. Each citation is coloured by why it was made, which the graph works out from the citing sentence."
    >
      <div className="space-y-4">
        <DropZone onFiles={upload} busy={uploading} />
        <Problem error={uploadError} />
        {jobs.length > 0 && <PipelineBoard jobs={jobs} />}
      </div>

      <div className="mt-8">
        <Loaded state={graph} what="Drawing the map">
          {(g) => g.nodes.length ? <LibraryMap graph={g} /> : <Empty>No papers yet. Drop a few PDFs above to start the graph.</Empty>}
        </Loaded>
      </div>

      {papers.data && papers.data.length > 0 && (
        <div className="mt-10">
          <Section title="Papers in the library" count={papers.data.length}>
            <table className="w-full text-left">
              <thead className="text-sm text-graphite">
                <tr><th className="py-1.5 font-normal">Title</th><th className="font-normal">Published</th><th className="hidden font-normal md:table-cell">Authors</th></tr>
              </thead>
              <tbody className="divide-y divide-rule">
                {papers.data.map((p) => (
                  <tr key={p.id}>
                    <td className="py-2 pr-4 font-serif"><PaperRef id={p.id} full /></td>
                    <td className="whitespace-nowrap pr-4 text-sm tabular-nums text-graphite">{p.published ?? p.year}</td>
                    <td className="hidden text-sm text-graphite md:table-cell">{p.authors.join(', ')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Section>
        </div>
      )}
    </Page>
  )
}
