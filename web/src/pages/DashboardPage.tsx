import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../api/client'
import type { ResultFile } from '../api/types'
import { Empty, ErrorBox, Loading } from '../components/common'

/** Numeric leaves of a JSON object as rows {label, key: value}, for any measured result file. */
function numericTable(data: unknown): { rows: Record<string, string | number>[]; cols: string[] } | null {
  const rec = data as Record<string, unknown>
  const candidates: [string, unknown][] = []
  const walk = (obj: unknown, path: string, depth: number) => {
    if (depth > 3 || obj === null || typeof obj !== 'object') return
    if (Array.isArray(obj)) {
      if (obj.length && obj.every((x) => x && typeof x === 'object' && !Array.isArray(x))) candidates.push([path, obj])
      return
    }
    const vals = Object.values(obj as object)
    if (vals.length && vals.every((v) => v && typeof v === 'object' && !Array.isArray(v))) candidates.push([path, obj])
    for (const [k, v] of Object.entries(obj as object)) walk(v, path ? `${path}.${k}` : k, depth + 1)
  }
  walk(rec, '', 0)
  for (const [, cand] of candidates) {
    const entries: [string, Record<string, unknown>][] = Array.isArray(cand)
      ? cand.map((r, i) => [String((r as Record<string, unknown>).name ?? (r as Record<string, unknown>).model_id ?? (r as Record<string, unknown>).system ?? (r as Record<string, unknown>).task_id ?? i), r as Record<string, unknown>])
      : Object.entries(cand as Record<string, Record<string, unknown>>)
    const cols = [...new Set(entries.flatMap(([, r]) => Object.entries(r).filter(([, v]) => typeof v === 'number').map(([k]) => k)))]
    if (entries.length >= 2 && cols.length >= 1) {
      return { rows: entries.slice(0, 60).map(([label, r]) => ({ label, ...Object.fromEntries(cols.map((c) => [c, typeof r[c] === 'number' ? (r[c] as number) : ''])) })), cols: cols.slice(0, 12) }
    }
  }
  return null
}

function ResultView({ file }: { file: ResultFile }) {
  const q = useQuery({ queryKey: ['result', file.path], queryFn: () => api.resultFile(file.path) })
  const [metric, setMetric] = useState<string | null>(null)
  const table = useMemo(() => (q.data ? numericTable(q.data) : null), [q.data])
  if (q.isLoading) return <Loading />
  if (q.isError) return <ErrorBox error={q.error} />
  const m = metric && table?.cols.includes(metric) ? metric : table?.cols[0]
  return (
    <div>
      <h3>{file.study ?? file.path}</h3>
      <p className="fine">
        <code>experiments/results/{file.path}</code> · recorded {file.provenance?.recorded_at_utc ?? 'n/a'} on {file.provenance?.machine_id ?? 'n/a'} · driver{' '}
        {file.provenance?.gpu_driver ?? 'n/a'} · commit {file.provenance?.git_sha ?? 'n/a'}{file.provenance?.git_dirty ? ' (dirty)' : ''}
      </p>
      {table && m ? (
        <>
          <label>Metric <select value={m} onChange={(e) => setMetric(e.target.value)}>{table.cols.map((c) => <option key={c}>{c}</option>)}</select></label>
          <div className="chart">
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={table.rows} margin={{ left: 8, right: 8, bottom: 40 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="label" angle={-30} textAnchor="end" interval={0} height={70} tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip />
                <Legend />
                <Bar dataKey={m} fill="#2f6fdb" />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="table-scroll">
            <table className="data">
              <thead><tr><th>row</th>{table.cols.map((c) => <th key={c}>{c}</th>)}</tr></thead>
              <tbody>{table.rows.map((r) => <tr key={String(r.label)}><td>{r.label}</td>{table.cols.map((c) => <td key={c}>{typeof r[c] === 'number' ? (r[c] as number).toLocaleString(undefined, { maximumFractionDigits: 4 }) : ''}</td>)}</tr>)}</tbody>
            </table>
          </div>
        </>
      ) : <Empty>No tabular numbers to chart in this file; raw JSON below.</Empty>}
      <details><summary>Raw JSON</summary><pre className="small">{JSON.stringify(q.data, null, 2).slice(0, 200_000)}</pre></details>
    </div>
  )
}

export default function DashboardPage() {
  const q = useQuery({ queryKey: ['results'], queryFn: api.results })
  const [sel, setSel] = useState<string | null>(null)
  const [group, setGroup] = useState('all')
  if (q.isLoading) return <Loading what="Loading result files" />
  if (q.isError) return <ErrorBox error={q.error} />
  const files = q.data!.filter((f) => group === 'all' || f.group === group)
  const groups = [...new Set(q.data!.map((f) => f.group))].sort()
  const file = q.data!.find((f) => f.path === sel)
  return (
    <div className="kb-layout">
      <aside className="sidebar">
        <p className="fine">Only files written by real runs in <code>experiments/results/</code>. Nothing here is computed by the UI. The System A–E comparison has not been run yet; its results appear here once it has.</p>
        <label>Group<select value={group} onChange={(e) => setGroup(e.target.value)}><option>all</option>{groups.map((g) => <option key={g}>{g}</option>)}</select></label>
        <ul className="plain">
          {files.map((f) => (
            <li key={f.path} className={f.path === sel ? 'active' : ''}>
              <button className="tree-leaf" onClick={() => setSel(f.path)}>{f.path}</button>
              <div className="fine">{f.provenance?.machine_id ?? '?'} · {f.provenance?.recorded_at_utc?.slice(0, 10) ?? 'no date'}</div>
            </li>
          ))}
        </ul>
      </aside>
      <section className="kb-main">{file ? <ResultView file={file} /> : <Empty>Pick a result file to view its measurements and provenance.</Empty>}</section>
    </div>
  )
}
