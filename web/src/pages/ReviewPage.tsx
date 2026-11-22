import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { diffLines } from 'diff'
import YAML from 'yaml'
import { api } from '../api/client'
import { Empty, ErrorBox, Loading, useIdentity } from '../components/common'

function Diff({ before, after }: { before: string; after: string }) {
  return (
    <pre className="diff">
      {diffLines(before, after).map((p, i) => (
        <span key={i} className={p.added ? 'add' : p.removed ? 'del' : ''}>{p.value}</span>
      ))}
    </pre>
  )
}

const doc = (fm: Record<string, unknown>, body: string) => `---\n${YAML.stringify(fm)}---\n\n${body}`

function ProposalReview({ bundle, id }: { bundle: string; id: string }) {
  const { actor } = useIdentity()
  const qc = useQueryClient()
  const nav = useNavigate()
  const q = useQuery({ queryKey: ['proposals', bundle, id], queryFn: () => api.proposal(bundle, id) })
  const [note, setNote] = useState('')
  const [edit, setEdit] = useState<string | null>(null)
  const done = () => { qc.invalidateQueries({ queryKey: ['proposals'] }); qc.invalidateQueries({ queryKey: ['okf'] }) }
  const approve = useMutation({
    mutationFn: () => {
      let extra = {}
      if (edit !== null) {
        const m = edit.match(/^---\n([\s\S]*?)\n---\n?\n?([\s\S]*)$/)
        if (!m) throw new Error('Edited text must start with a --- frontmatter block ---')
        extra = { edited_frontmatter: YAML.parse(m[1]), edited_body: m[2] }
      }
      return api.approve(bundle, id, { reviewer: actor!, note, ...extra })
    },
    onSuccess: done,
  })
  const reject = useMutation({ mutationFn: () => api.reject(bundle, id, { reviewer: actor!, note }), onSuccess: done })
  if (q.isLoading) return <Loading />
  if (q.isError) return <ErrorBox error={q.error} />
  const { proposal: p, current, stale } = q.data!
  const proposed = doc(p.proposed_frontmatter, p.proposed_body)
  const before = current ? doc(Object.fromEntries(Object.entries(current.frontmatter).filter(([k]) => k !== 'generated' && k !== 'verified')), current.body) : ''
  return (
    <article className="proposal">
      <header>
        <div className="fine">{p.kind} · proposed by <code>{p.proposed_by}</code> · {new Date(p.created_at).toLocaleString()}</div>
        <h2><code>{p.concept_id}</code></h2>
        <span className={`badge status-${p.status}`}>{p.status}</span>
        {stale && p.status === 'pending' && <div className="state error">The concept changed after this proposal was made; approving will be refused as a conflict.</div>}
      </header>
      <h4>Rationale</h4>
      <p>{p.rationale}</p>
      {p.conflicts_with.length > 0 && <p className="state error">Agent says this conflicts with: {p.conflicts_with.map((c) => <code key={c}> {c}</code>)}</p>}
      <h4>Evidence the agent used</h4>
      <ul className="plain small">
        {p.evidence.map((e, i) => <li key={i}>{'okf' in e ? <Link to={`/knowledge?bundle=${bundle}&concept=${encodeURIComponent(String(e.okf))}`}>okf:{String(e.okf)}</Link> : <code>{JSON.stringify(e)}</code>}</li>)}
      </ul>
      <h4>{current ? 'Change (current → proposed)' : 'Proposed new concept'}</h4>
      {edit === null ? <Diff before={before} after={proposed} /> : <textarea className="mono" rows={18} value={edit} onChange={(e) => setEdit(e.target.value)} />}
      {p.status === 'pending' ? (
        actor ? (
          <div className="review-actions">
            <label>Review note<input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Required to reject" /></label>
            <div className="row">
              {edit === null ? <button onClick={() => setEdit(proposed)}>Edit before approving</button> : <button onClick={() => setEdit(null)}>Discard my edits</button>}
              <button className="primary" disabled={approve.isPending} onClick={() => approve.mutate()}>{edit === null ? 'Approve' : 'Approve with my edits'}</button>
              <button className="danger" disabled={!note.trim() || reject.isPending} onClick={() => reject.mutate()}>Reject</button>
            </div>
            <p className="fine">Approval writes the concept as <code>verified by {actor}</code>; with edits, you become its author.</p>
          </div>
        ) : <div className="state error">Set your reviewer id (top right) to approve or reject.</div>
      ) : (
        <p className="fine">Reviewed by <code>{p.reviewed_by}</code> {p.reviewed_at && new Date(p.reviewed_at).toLocaleString()}{p.review_note ? `: ${p.review_note}` : ''}</p>
      )}
      {approve.data && (approve.data.status === 'conflict'
        ? <div className="state error">Conflict: {approve.data.reason}. Nothing was written.</div>
        : <div className="state ok">Approved and written to the bundle. <button onClick={() => nav(`/knowledge?bundle=${bundle}&concept=${encodeURIComponent(p.concept_id)}`)}>Open concept</button>
            {approve.data.sync_failures?.length ? ` Index sync failed: ${approve.data.sync_failures.map((f) => f.error).join('; ')}` : ''}</div>)}
      {(approve.isError || reject.isError) && <ErrorBox error={approve.error ?? reject.error} />}
    </article>
  )
}

export default function ReviewPage() {
  const { proposalId } = useParams()
  const [params, setParams] = useSearchParams()
  const bundles = useQuery({ queryKey: ['okf', 'bundles'], queryFn: api.bundles })
  const bundle = params.get('bundle') ?? bundles.data?.find((b) => b.default)?.name ?? bundles.data?.[0]?.name
  const status = params.get('status') ?? 'pending'
  const list = useQuery({ queryKey: ['proposals', bundle, status], queryFn: () => api.proposals(bundle!, status === 'all' ? undefined : status), enabled: !!bundle })
  if (bundles.isError) return <ErrorBox error={bundles.error} />
  return (
    <div className="kb-layout">
      <aside className="sidebar">
        <label>Bundle<select value={bundle ?? ''} onChange={(e) => setParams({ bundle: e.target.value, status })}>{bundles.data?.map((b) => <option key={b.name}>{b.name}</option>)}</select></label>
        <label>Status<select value={status} onChange={(e) => setParams({ bundle: bundle ?? '', status: e.target.value })}>
          {['pending', 'approved', 'rejected', 'conflict', 'all'].map((s) => <option key={s}>{s}</option>)}</select></label>
        {list.isLoading ? <Loading /> : list.isError ? <ErrorBox error={list.error} /> : list.data!.length === 0 ? <Empty>No {status} proposals.</Empty> : (
          <ul className="plain">
            {list.data!.map((p) => (
              <li key={p.id} className={p.id === proposalId ? 'active' : ''}>
                <Link to={`/review/${p.id}?bundle=${bundle}&status=${status}`}>{p.kind} <code>{p.concept_id}</code></Link>
                <div className="fine">{p.proposed_by} · {new Date(p.created_at).toLocaleString()}</div>
              </li>
            ))}
          </ul>
        )}
      </aside>
      <section className="kb-main">
        {proposalId && bundle ? <ProposalReview bundle={bundle} id={proposalId} /> : <Empty>Agent-proposed knowledge changes wait here for a person to approve, edit or reject. Nothing an agent writes reaches the bundle without approval.</Empty>}
      </section>
    </div>
  )
}
