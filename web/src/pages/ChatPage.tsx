import { useEffect, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, streamChat, type StreamEvent } from '../api/client'
import type { ChatAnswer, Message } from '../api/types'
import { Empty, ErrorBox, Markdown, MeasurementPanel, StatusBadge, TrustBadge } from '../components/common'

interface Turn {
  id: string
  role: 'user' | 'assistant'
  content: string
  meta?: Partial<ChatAnswer> & { error?: string }
  pending?: boolean
  context?: Extract<StreamEvent, { event: 'context' }>['data']
}

const toTurn = (m: Message): Turn => ({ id: m.id, role: m.role, content: m.content, meta: m.meta ?? undefined })

export default function ChatPage() {
  const { conversationId } = useParams()
  const nav = useNavigate()
  const qc = useQueryClient()
  const [turns, setTurns] = useState<Turn[]>([])
  const [question, setQuestion] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const [useCode, setUseCode] = useState(true)
  const [propose, setPropose] = useState(true)
  const [selected, setSelected] = useState<string | null>(null)
  const abort = useRef<AbortController | null>(null)
  const end = useRef<HTMLDivElement>(null)

  const conversations = useQuery({ queryKey: ['conversations'], queryFn: () => api.conversations() })
  const conv = useQuery({
    queryKey: ['conversation', conversationId],
    queryFn: () => api.conversation(conversationId!),
    enabled: !!conversationId && !busy,
  })

  useEffect(() => {
    if (!conversationId) setTurns([])
    else if (conv.data && !busy) setTurns((conv.data.messages ?? []).map(toTurn))
  }, [conversationId, conv.data, busy])
  useEffect(() => end.current?.scrollIntoView?.({ behavior: 'smooth' }), [turns])

  async function ask(e: React.FormEvent) {
    e.preventDefault()
    const q = question.trim()
    if (q.length < 3 || busy) return
    setError(null)
    setBusy(true)
    setQuestion('')
    const aid = `pending-${Date.now()}`
    setTurns((t) => [...t, { id: `u-${aid}`, role: 'user', content: q }, { id: aid, role: 'assistant', content: '', pending: true }])
    const update = (fn: (t: Turn) => Turn) => setTurns((ts) => ts.map((t) => (t.id === aid ? fn(t) : t)))
    abort.current = new AbortController()
    let newConv: string | null = null
    try {
      await streamChat(
        { question: q, conversation_id: conversationId ?? null, use_code: useCode, propose_updates: propose },
        (ev) => {
          if (ev.event === 'conversation') newConv = ev.data.conversation_id
          else if (ev.event === 'context') update((t) => ({ ...t, context: ev.data }))
          else if (ev.event === 'delta') update((t) => ({ ...t, content: t.content + ev.data }))
          else if (ev.event === 'answer') {
            update((t) => ({ ...t, content: ev.data.answer, meta: ev.data, pending: false }))
            setSelected(aid)
          } else if (ev.event === 'error') {
            update((t) => ({ ...t, pending: false, meta: { error: ev.data.message } }))
            setError(ev.data.message)
          }
        },
        abort.current.signal,
      )
    } catch (err) {
      update((t) => ({ ...t, pending: false }))
      setError(err)
    } finally {
      setBusy(false)
      qc.invalidateQueries({ queryKey: ['conversations'] })
      qc.invalidateQueries({ queryKey: ['proposals'] })
      if (newConv && newConv !== conversationId) nav(`/chat/${newConv}`, { replace: true })
    }
  }

  const detail = turns.find((t) => t.id === selected) ?? [...turns].reverse().find((t) => t.role === 'assistant' && t.meta)

  return (
    <div className="chat-layout">
      <aside className="sidebar">
        <button className="primary block" onClick={() => nav('/chat')}>New conversation</button>
        <h4>History</h4>
        {conversations.isError && <ErrorBox error={conversations.error} />}
        {conversations.data?.length === 0 && <Empty>No conversations yet.</Empty>}
        <ul className="conv-list">
          {conversations.data?.map((c) => (
            <li key={c.id} className={c.id === conversationId ? 'active' : ''}>
              <Link to={`/chat/${c.id}`}>{c.title}</Link>
              <span className="fine">{c.message_count} msgs · {new Date(c.updated_at).toLocaleString()}</span>
            </li>
          ))}
        </ul>
      </aside>

      <section className="chat-main">
        <div className="messages">
          {turns.length === 0 && (
            <Empty>
              Ask an engineering question. Answers are grounded in the OKF knowledge bundle and the indexed
              repositories, with citations; the agent may propose knowledge updates for you to review.
            </Empty>
          )}
          {turns.map((t) => (
            <div key={t.id} className={`msg ${t.role} ${t.id === detail?.id ? 'selected' : ''}`}
                 onClick={() => t.role === 'assistant' && setSelected(t.id)}>
              {t.role === 'assistant' ? (
                <>
                  {t.pending && !t.content && <div className="fine">{t.context ? 'Generating…' : 'Retrieving knowledge…'}</div>}
                  <Markdown text={t.content} />
                  {t.meta?.insufficient_evidence && <div className="badge status-deprecated">Insufficient evidence</div>}
                  {t.meta?.error && <ErrorBox error={t.meta.error} />}
                </>
              ) : (
                <p>{t.content}</p>
              )}
            </div>
          ))}
          <div ref={end} />
        </div>
        {error !== null && <ErrorBox error={error} />}
        <form className="ask" onSubmit={ask}>
          <textarea value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="e.g. How does Flask dispatch a request to a view?"
                    onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) ask(e) }} rows={3} aria-label="Question" />
          <div className="row">
            <label><input type="checkbox" checked={useCode} onChange={(e) => setUseCode(e.target.checked)} /> code evidence</label>
            <label><input type="checkbox" checked={propose} onChange={(e) => setPropose(e.target.checked)} /> allow knowledge proposals</label>
            {busy ? <button type="button" onClick={() => abort.current?.abort()}>Stop</button>
                  : <button className="primary" type="submit" disabled={question.trim().length < 3}>Ask</button>}
          </div>
        </form>
      </section>

      <aside className="trace">
        <h3>Trace</h3>
        {!detail?.meta && !detail?.context && <Empty>Select an answer to see its sources and measurements.</Empty>}
        {(detail?.meta?.concepts ?? detail?.context?.concepts) && (
          <>
            <h4>Knowledge used <span className="fine">({detail?.meta?.retrieval_mode ?? detail?.context?.retrieval_mode})</span></h4>
            <ul className="plain">
              {(detail?.meta?.concepts ?? detail?.context?.concepts ?? []).map((c) => (
                <li key={c.concept_id}>
                  <Link to={`/knowledge?concept=${encodeURIComponent(c.concept_id)}`}>{c.title}</Link>{' '}
                  <TrustBadge tier={c.trust_tier} /> <StatusBadge status={c.status} stale={c.stale} />
                  {detail?.meta?.citations?.includes(`okf:${c.concept_id}`) && <span className="badge cited">cited</span>}
                  <div className="fine">{c.type} · via {c.reason}</div>
                </li>
              ))}
            </ul>
          </>
        )}
        {(detail?.meta?.code_evidence ?? detail?.context?.code_evidence)?.length ? (
          <>
            <h4>Code evidence</h4>
            <ul className="plain">
              {(detail?.meta?.code_evidence ?? detail?.context?.code_evidence ?? []).map((c) => (
                <li key={c.n}>
                  <code>[code:{c.n}]</code> {c.repository} <code>{c.source_path}{c.start_line ? `:${c.start_line}-${c.end_line}` : ''}</code>
                  {detail?.meta?.citations?.includes(`code:${c.n}`) && <span className="badge cited">cited</span>}
                </li>
              ))}
            </ul>
          </>
        ) : null}
        {detail?.meta?.invalid_citations?.length ? (
          <div className="state error">Invalid citations (not in the evidence): {detail.meta.invalid_citations.join(', ')}</div>
        ) : null}
        {detail?.meta?.proposals?.length ? (
          <>
            <h4>Knowledge proposals</h4>
            <ul className="plain">
              {detail.meta.proposals.map((p) => (
                <li key={p.id}>
                  <Link to={`/review/${p.id}`}>{p.kind} <code>{p.concept_id}</code></Link> — {p.rationale}
                </li>
              ))}
            </ul>
          </>
        ) : null}
        {detail?.meta?.rejected_proposals?.length ? (
          <p className="fine">{detail.meta.rejected_proposals.length} malformed proposal(s) discarded: {detail.meta.rejected_proposals.map((r) => r.reason).join('; ')}</p>
        ) : null}
        <MeasurementPanel m={detail?.meta?.measurements} />
      </aside>
    </div>
  )
}
