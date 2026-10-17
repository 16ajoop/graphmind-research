// The library map: every paper as an index card in the row of its publication year (oldest at the top),
// every citation as an edge inked in its intent's colour. Papers that are cited but whose PDF is not added
// share the first row. The legend doubles as a filter. Clicking a card opens the paper panel.
import { useMemo, useState } from 'react'
import dagre from '@dagrejs/dagre'
import {
  Controls, Handle, MarkerType, Position, ReactFlow, type Edge, type Node, type NodeProps,
} from '@xyflow/react'
import type { LibraryGraph } from '../api'
import { INTENTS, intentOf, shortTitle } from '../intents'
import { useWorkspace } from '../workspace'

const CARD_W = 196
const CARD_H = 58
const SLOT_W = 226            // card plus the space beside it
const ROW_H = 128             // card plus the space below it, where the edges fan out
const LABEL_W = 120           // the year, left of each row
const OUTSIDE = -1            // the row for cited-only papers

type PaperData = { title: string; year: number | null; inLibrary: boolean; citedBy: number; dim: boolean }
type RowData = { label: string; width: number; shade: boolean }
type PaperNode = Node<PaperData, 'paper'>
type RowNode = Node<RowData, 'row'>

function PaperCard({ data, selected }: NodeProps<PaperNode>) {
  return (
    <div
      className={`rounded-md border px-3 py-2 transition-opacity ${data.inLibrary ? 'border-rule bg-sheet' : 'border-dashed border-[#b9c0c7] bg-vellum'}
        ${selected ? 'ring-2 ring-pen' : ''} ${data.dim ? 'opacity-35' : ''}`}
      style={{ width: CARD_W, height: CARD_H }}
      title={data.title}
    >
      {/* A citing (newer, lower) paper sends its edges from its top to the bottom of the older paper it cites. */}
      <Handle type="source" position={Position.Top} className="!opacity-0" isConnectable={false} />
      <Handle type="target" position={Position.Bottom} className="!opacity-0" isConnectable={false} />
      <div className={`truncate font-serif text-[16px] font-semibold leading-tight ${data.inLibrary ? '' : 'text-graphite'}`}>
        {shortTitle(data.title)}
      </div>
      <div className="mt-1 truncate text-[13px] text-graphite">
        {data.inLibrary ? `cited ${data.citedBy} time${data.citedBy === 1 ? '' : 's'} here` : `${data.year ?? 'no year'}, cited ${data.citedBy} times`}
      </div>
    </div>
  )
}

function YearRow({ data }: NodeProps<RowNode>) {
  return (
    <div className={`flex items-center rounded-lg ${data.shade ? 'bg-[#eceff0]/70' : ''}`} style={{ width: data.width, height: ROW_H - 24 }}>
      <div className={`px-4 font-serif font-semibold text-[#8f99a3] ${data.label.length > 4 ? 'w-[110px] text-[15px] leading-tight' : 'text-[26px]'}`}>
        {data.label}
      </div>
    </div>
  )
}

const nodeTypes = { paper: PaperCard, row: YearRow }

function layout(graph: LibraryGraph) {
  // dagre orders the cards so that edges cross as little as possible; the year then fixes each card's row.
  const g = new dagre.graphlib.Graph()
  g.setGraph({ rankdir: 'TB', nodesep: 24, ranksep: 60 })
  g.setDefaultEdgeLabel(() => ({}))
  graph.nodes.forEach((n) => g.setNode(n.id, { width: CARD_W, height: CARD_H }))
  graph.edges.forEach((e) => g.setEdge(e.target, e.source))     // older -> newer, so rank follows time
  dagre.layout(g)

  const rowOf = (n: LibraryGraph['nodes'][number]) => (n.in_library ? n.year ?? 0 : OUTSIDE)
  const rows = [...new Set(graph.nodes.map(rowOf))].sort((a, b) => a - b)
  const byRow = new Map<number, { id: string; x: number }[]>()
  graph.nodes.forEach((n) => byRow.set(rowOf(n), [...(byRow.get(rowOf(n)) ?? []), { id: n.id, x: g.node(n.id).x }]))
  const widest = Math.max(...[...byRow.values()].map((r) => r.length))

  // Each row is centred, in dagre's left-to-right order, so the map is only as wide as the busiest year.
  const pos: Record<string, { x: number; y: number }> = {}
  rows.forEach((row, i) => {
    const cards = (byRow.get(row) ?? []).sort((a, b) => a.x - b.x)
    const indent = LABEL_W + ((widest - cards.length) * SLOT_W) / 2
    cards.forEach((c, j) => { pos[c.id] = { x: indent + j * SLOT_W, y: i * ROW_H } })
  })
  return { pos, rows, width: LABEL_W + widest * SLOT_W, height: rows.length * ROW_H }
}

export default function LibraryMap({ graph }: { graph: LibraryGraph }) {
  const { openPaper, paperId } = useWorkspace()
  const [only, setOnly] = useState<string | null>(null)

  const { pos, rows, width, height } = useMemo(() => layout(graph), [graph])
  const counts = useMemo(() => {
    const c: Record<string, number> = {}
    graph.edges.forEach((e) => { c[e.intent ?? ''] = (c[e.intent ?? ''] ?? 0) + 1 })
    return c
  }, [graph])

  // When a paper is open, its own citations stay in full colour and everything else steps back.
  const touching = useMemo(() => new Set(
    paperId ? graph.edges.filter((e) => e.source === paperId || e.target === paperId).flatMap((e) => [e.source, e.target]) : [],
  ), [graph, paperId])

  const nodes: Node[] = [
    ...rows.map((y, i): RowNode => ({
      id: `row-${y}`, type: 'row', position: { x: 0, y: i * ROW_H - (ROW_H - 24 - CARD_H) / 2 }, draggable: false,
      selectable: false, zIndex: -1,
      data: { label: y === OUTSIDE ? 'Cited, PDF not added' : y ? String(y) : 'No year', width: width + 12, shade: i % 2 === 0 },
    })),
    ...graph.nodes.map((n): PaperNode => ({
      id: n.id, type: 'paper', position: pos[n.id], selected: n.id === paperId,
      data: {
        title: n.title, year: n.year, inLibrary: n.in_library,
        citedBy: graph.edges.filter((e) => e.target === n.id).length,
        dim: !!paperId && !touching.has(n.id),
      },
    })),
  ]

  const edges: Edge[] = graph.edges.map((e, i) => {
    const color = intentOf(e.intent).color
    const mine = !paperId || e.source === paperId || e.target === paperId
    return {
      id: `e${i}`, source: e.source, target: e.target,
      hidden: only !== null && (e.intent ?? '') !== only,
      style: { stroke: color, strokeWidth: mine && paperId ? 2.4 : 1.6, opacity: mine ? 0.95 : 0.12 },
      markerEnd: { type: MarkerType.ArrowClosed, color, width: 16, height: 16 },
    }
  })

  const legend = Object.keys(INTENTS).filter((k) => counts[k]).concat(Object.keys(counts).filter((k) => !INTENTS[k]))

  return (
    <div className="overflow-hidden rounded-lg border border-rule bg-sheet">
      <div className="flex flex-wrap items-center gap-x-1 gap-y-1 border-b border-rule px-3 py-2" role="group" aria-label="Show citations by intent">
        {legend.map((k) => {
          const it = intentOf(k)
          const on = only === k
          return (
            <button
              key={k || 'none'}
              aria-pressed={on}
              onClick={() => setOnly(on ? null : k)}
              title={it.meaning}
              className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-sm ${on ? 'bg-ink text-white' : 'hover:bg-vellum'} ${only && !on ? 'opacity-50' : ''}`}
            >
              <span className="h-2.5 w-2.5 rounded-full" style={{ background: it.color }} aria-hidden />
              {it.label} <span className={on ? 'text-white/70' : 'text-graphite'}>{counts[k]}</span>
            </button>
          )
        })}
        {only && <button className="ml-1 text-sm text-pen hover:underline" onClick={() => setOnly(null)}>Show every intent</button>}
      </div>
      {/* As tall as the map needs at full width, within limits. */}
      <div className="max-h-[780px] min-h-[420px] w-full" style={{ aspectRatio: `${width + 40} / ${height + 20}` }}>
        <ReactFlow
          key={graph.nodes.length}
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          fitView
          fitViewOptions={{ padding: 0.04 }}
          minZoom={0.2}
          nodesDraggable={false}
          nodesConnectable={false}
          onNodeClick={(_, n) => { if (n.type === 'paper') openPaper(n.id) }}
          onPaneClick={() => openPaper(null)}
        >
          <Controls showInteractive={false} position="bottom-right" />
        </ReactFlow>
      </div>
    </div>
  )
}
