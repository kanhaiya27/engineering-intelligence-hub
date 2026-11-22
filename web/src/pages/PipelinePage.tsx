import { useRef, useState } from 'react'
import { API } from '../api/client'
import { ErrorBox, TierTag } from '../components/common'

// Contract v1 (docs/API_CONTRACT.md). Untrusted text (chunk content, model answers) is shown
// as plain text only (§6): no Markdown, no links, no HTML.
type Metric = { value: number | null; unit: string; provenance: string | null; method: string; note?: string | null }
interface Ev { event: string; seq: number; payload: any } // eslint-disable-line @typescript-eslint/no-explicit-any

const SYSTEMS: [string, string][] = [
  ['A', 'LLM only (no retrieval)'],
  ['B', 'Fixed hybrid RAG'],
  ['C', '+ task-aware adaptive retrieval'],
  ['D', '+ knowledge graph'],
  ['E', '+ quality gate and bounded escalation'],
]

function M({ m, digits = 1 }: { m?: Metric; digits?: number }) {
  if (!m) return null
  if (m.value === null) return <span className="fine" title={m.note ?? ''}>n/a</span>
  return <span>{m.value.toLocaleString(undefined, { maximumFractionDigits: digits })} {m.unit} <TierTag tier={m.provenance ?? undefined} /></span>
}

export default function PipelinePage() {
  const [query, setQuery] = useState('How does Flask register a URL rule for a view function?')
  const [system, setSystem] = useState('E')
  const [events, setEvents] = useState<Ev[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const abort = useRef<AbortController | null>(null)

  async function run(e: React.FormEvent) {
    e.preventDefault()
    setEvents([]); setError(null); setBusy(true)
    abort.current = new AbortController()
    try {
      const res = await fetch(`${API}/v1/trace/stream`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ query, system }), signal: abort.current.signal,
      })
      if (!res.ok || !res.body) {
        const body = await res.json().catch(() => null)
        throw new Error(body?.error?.message ?? res.statusText)
      }
      const reader = res.body.getReader(), dec = new TextDecoder()
      let buf = ''
      for (;;) {
        const { value, done } = await reader.read()
        if (done) break
        buf += dec.decode(value, { stream: true })
        let i
        while ((i = buf.indexOf('\n\n')) >= 0) {
          const frame = buf.slice(0, i); buf = buf.slice(i + 2)
          const data = frame.split('\n').find((l) => l.startsWith('data:'))
          if (data) {
            const ev: Ev = JSON.parse(data.slice(5))
            setEvents((x) => [...x, ev])
            if (ev.event === 'error') setError(ev.payload.message)
          }
        }
      }
    } catch (err) {
      if ((err as Error).name !== 'AbortError') setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const started = events.find((e) => e.event === 'trace.started')?.payload
  const done = events.find((e) => e.event === 'trace.completed')?.payload
  return (
    <div className="page">
      <h2>Pipeline trace (Systems A–E)</h2>
      <p className="fine">Runs one query through the research configuration of the chosen system and shows every stage as it happens. Live queries are not part of any benchmark.</p>
      <form onSubmit={run} className="row">
        <input style={{ flex: 1, minWidth: 260 }} value={query} onChange={(e) => setQuery(e.target.value)} minLength={3} maxLength={2000} aria-label="Query" />
        <select value={system} onChange={(e) => setSystem(e.target.value)} aria-label="System">
          {SYSTEMS.map(([id, label]) => <option key={id} value={id}>{id}: {label}</option>)}
        </select>
        {busy ? <button type="button" onClick={() => abort.current?.abort()}>Stop</button> : <button className="primary" type="submit">Run</button>}
      </form>
      {error && <ErrorBox error={error} />}
      {started?.execution?.generation_source === 'mock' && <div className="state error"><strong>Mock output, not a result.</strong></div>}
      {started && <p className="fine">machine {started.execution.producer.machine_id} · {started.execution.producer.gpu_name} · commit {started.execution.producer.git_sha.slice(0, 12)} · grid {started.execution.producer.carbon_region} ({started.execution.producer.carbon_intensity_gco2_per_kwh} gCO₂e/kWh)</p>}

      {events.filter((e) => e.event !== 'trace.started' && e.event !== 'trace.completed').map((e) => (
        <section key={e.seq} className="card" style={{ marginBottom: 10 }}>
          <h4>#{e.seq} {e.event}{e.payload.attempt_index !== undefined ? ` · attempt ${e.payload.attempt_index}` : ''}</h4>
          {e.event === 'classification' && (
            <p>{e.payload.sdlc_stage} · {e.payload.task_type} ({e.payload.task_type_source}) · complexity {e.payload.complexity} · criticality {e.payload.criticality} · threshold {e.payload.quality_threshold}</p>
          )}
          {e.event === 'retrieval' && (
            <>
              <p>
                strategy <code>{e.payload.strategy_name}</code>{e.payload.strategy_fallback && <span className="badge status-deprecated">fell back from {e.payload.requested_strategy}</span>} · {e.payload.mode} · top_k {e.payload.top_k} · <M m={e.payload.latency_ms} />
              </p>
              <p className="small">
                {(['dense', 'sparse', 'graph', 'reranker'] as const).map((ch) => (
                  <span key={ch} className={`badge ${e.payload[ch].executed ? 'trust-human-reviewed' : e.payload[ch].requested ? 'status-deprecated' : ''}`}>
                    {ch}: {e.payload[ch].executed ? 'ran' : e.payload[ch].requested ? 'requested, did not run' : 'off'}
                  </span>
                ))}
              </p>
              <details><summary>{e.payload.chunks.length} chunks</summary>
                {e.payload.chunks.map((c: any) => ( // eslint-disable-line @typescript-eslint/no-explicit-any
                  <div key={c.rank} className="small"><code>{c.rank}. {c.citation}</code> {c.channel} · {c.score_kind} {c.score.toFixed(3)}<pre className="small">{c.content}</pre></div>
                ))}
              </details>
            </>
          )}
          {e.event === 'generation' && (
            <>
              <p className="small">{e.payload.model_id} · in <M m={e.payload.input_tokens} digits={0} /> · out <M m={e.payload.output_tokens} digits={0} /> · <M m={e.payload.latency_ms} /> · {e.payload.finish_reason}</p>
              <pre className="small" style={{ whiteSpace: 'pre-wrap' }}>{e.payload.answer}</pre>
            </>
          )}
          {e.event === 'verification' && (e.payload.executed ? (
            <>
              <p>score <M m={e.payload.aggregated_score} digits={3} /> vs threshold {e.payload.threshold} → <strong>{e.payload.passed ? 'PASSED' : 'FAILED'}</strong>{e.payload.critical_failures.length > 0 && ` · critical: ${e.payload.critical_failures.join(', ')}`}</p>
              <table className="data small"><tbody>{e.payload.signals.map((s: any, i: number) => <tr key={i}><td>{s.signal_type}</td><td>{s.status}</td><td>{s.score ?? '—'}</td><td>w {s.weight}</td></tr>)}</tbody></table>{/* eslint-disable-line @typescript-eslint/no-explicit-any */}
            </>
          ) : <p className="fine">No quality gate for this system.</p>)}
          {e.event === 'escalation' && (
            <p>{e.payload.rung}: <code>{e.payload.from_strategy}</code> → <code>{e.payload.to_strategy}</code> ({e.payload.changes.map((c: any) => `${c.name} ${c.before}→${c.after}`).join(', ')})</p> // eslint-disable-line @typescript-eslint/no-explicit-any
          )}
        </section>
      ))}

      {done && (
        <section className="card ok">
          <h3>Outcome: <span className="badge">{done.outcome.verdict}</span></h3>
          {done.outcome.verdict === 'UNVERIFIED' && <p className="fine">No quality gate ran (systems A–D): treat this answer as unverified.</p>}
          <pre className="small" style={{ whiteSpace: 'pre-wrap' }}>{done.outcome.answer}</pre>
          <table className="data small"><tbody>
            {Object.entries(done.totals as Record<string, Metric>).map(([k, m]) => <tr key={k}><th>{k}</th><td><M m={m} digits={4} /></td><td className="fine">{m.method}{m.note ? ` · ${m.note}` : ''}</td></tr>)}
          </tbody></table>
          {done.warnings.length > 0 && <p className="state error">{done.warnings.join('; ')}</p>}
        </section>
      )}
    </div>
  )
}
