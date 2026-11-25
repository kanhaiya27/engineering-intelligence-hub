import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import { ErrorBox, Loading } from '../components/common'

/** Checked on demand only: /status reads the GPU, and polling it during a measured run
 *  would disturb the energy counter (CLAUDE.md measurement rules). */
export default function StatusPage() {
  const q = useQuery({ queryKey: ['status'], queryFn: api.status, refetchOnWindowFocus: false, staleTime: Infinity })
  return (
    <div className="page">
      <div className="row">
        <h2>Service status</h2>
        <span className="spacer" />
        <button onClick={() => q.refetch()} disabled={q.isFetching}>{q.isFetching ? 'Checking…' : 'Check again'}</button>
      </div>
      <p className="fine">Checked on request only, never polled, so it cannot disturb an energy measurement.</p>
      {q.isLoading && <Loading what="Checking services" />}
      {q.isError && <ErrorBox error={q.error} />}
      {q.data && (
        <>
          <p className="fine">machine <code>{q.data.machine_id}</code> · {new Date(q.data.checked_at).toLocaleString()}</p>
          <div className="cards">
            {Object.entries(q.data.services).map(([name, s]) => (
              <div key={name} className={`card ${s.ok ? 'ok' : 'bad'}`}>
                <h3>{name} <span className={`badge ${s.ok ? 'trust-human-reviewed' : 'status-deprecated'}`}>{s.ok ? 'OK' : 'DOWN'}</span></h3>
                {name === 'ollama' && Array.isArray(s.models) ? (
                  <>
                    <p className="fine">version {String(s.version ?? '?')} · default {String(s.default_model)}</p>
                    <table className="data small"><thead><tr><th>model</th><th>pulled</th><th>digest = pin</th></tr></thead><tbody>
                      {(s.models as { model_id: string; pulled: boolean; digest_matches_pin: boolean | null }[]).map((m) => (
                        <tr key={m.model_id}><td>{m.model_id}</td><td>{m.pulled ? 'yes' : 'no'}</td><td>{m.digest_matches_pin === null ? '—' : m.digest_matches_pin ? 'yes' : 'NO'}</td></tr>
                      ))}</tbody></table>
                    {s.error ? <p className="fine">{String(s.error)}</p> : null}
                  </>
                ) : (
                  <dl>{Object.entries(s).filter(([k]) => k !== 'ok').map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{typeof v === 'object' ? JSON.stringify(v) : String(v)}</dd></div>)}</dl>
                )}
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}
