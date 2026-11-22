import { useEffect, useMemo, useRef, useState } from 'react'
import ForceGraph2D from 'react-force-graph-2d'
import type { ConceptSummary } from '../api/types'

const TYPE_COLORS = ['#2f6fdb', '#d9822b', '#2a9d8f', '#9b5de5', '#e63946', '#6c757d', '#43aa8b', '#f4a261']

interface Props {
  nodes: ConceptSummary[]
  edges: { source: string; target: string }[]
  center?: string
  onSelect: (id: string) => void
}

/** Force-directed view of OKF concept links (OKF §6: every link is an untyped directed edge). */
export default function ConceptGraph({ nodes, edges, center, onSelect }: Props) {
  const box = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(600)
  useEffect(() => {
    const el = box.current
    if (!el) return
    const ro = new ResizeObserver(() => setWidth(el.clientWidth))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  const types = useMemo(() => [...new Set(nodes.map((n) => n.type))].sort(), [nodes])
  const color = (t: string) => TYPE_COLORS[types.indexOf(t) % TYPE_COLORS.length]
  const data = useMemo(
    () => ({
      nodes: nodes.map((n) => ({ ...n })),
      links: edges.map((e) => ({ source: e.source, target: e.target })),
    }),
    [nodes, edges],
  )
  return (
    <div ref={box} className="graph-box">
      <ForceGraph2D
        graphData={data}
        width={width}
        height={460}
        nodeId="id"
        nodeLabel={(n: object) => {
          const c = n as ConceptSummary
          return `${c.title} (${c.type}, ${c.trust_tier})`
        }}
        nodeColor={(n: object) => color((n as ConceptSummary).type)}
        nodeVal={(n: object) => ((n as ConceptSummary).id === center ? 8 : 2)}
        linkDirectionalArrowLength={3}
        linkDirectionalArrowRelPos={1}
        linkColor={() => 'rgba(120,120,140,0.45)'}
        onNodeClick={(n: object) => onSelect((n as ConceptSummary).id)}
        cooldownTicks={120}
      />
      <div className="legend">
        {types.map((t) => (
          <span key={t}>
            <i style={{ background: color(t) }} /> {t}
          </span>
        ))}
      </div>
    </div>
  )
}
