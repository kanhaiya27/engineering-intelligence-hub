import type {
  Bundle,
  ChatAnswer,
  ConceptDetail,
  ConceptSummary,
  Conversation,
  Proposal,
  ProposalDetail,
  ResultFile,
  ServiceStatus,
  TreeNode,
} from './types'

export const API = '/api'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(API + path, {
    ...init,
    headers: init?.body && !(init.body instanceof FormData) ? { 'Content-Type': 'application/json', ...init?.headers } : init?.headers,
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail ?? body)
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, detail)
  }
  return res.json() as Promise<T>
}

const enc = encodeURIComponent
const cpath = (id: string) => id.split('/').map(enc).join('/')

export const api = {
  status: () => request<ServiceStatus>('/status'),
  bundles: () => request<Bundle[]>('/okf/bundles'),
  tree: (b: string) => request<TreeNode>(`/okf/bundles/${enc(b)}/tree`),
  search: (b: string, q: string, type?: string) =>
    request<{ results: ConceptSummary[]; types: Record<string, number>; tags: Record<string, number> }>(
      `/okf/bundles/${enc(b)}/concepts?q=${enc(q)}&limit=100${type ? `&type=${enc(type)}` : ''}`,
    ),
  semantic: (b: string, q: string) =>
    request<{ results: { id: string; title: string; type: string; section: string; trust_tier: string; score: number }[] }>(
      `/okf/bundles/${enc(b)}/semantic?q=${enc(q)}&limit=15`,
    ),
  concept: (b: string, id: string) => request<ConceptDetail>(`/okf/bundles/${enc(b)}/concept/${cpath(id)}`),
  saveConcept: (b: string, id: string, payload: { frontmatter: Record<string, unknown>; body: string; base_hash: string | null; actor: string; summary: string }) =>
    request<{ concept_id: string; hash: string; sync_failures: { error: string }[] }>(`/okf/bundles/${enc(b)}/concept/${cpath(id)}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),
  graph: (b: string, center?: string, hops = 1) =>
    request<{ nodes: ConceptSummary[]; edges: { source: string; target: string }[]; total_concepts: number }>(
      `/okf/bundles/${enc(b)}/graph?limit=300&hops=${hops}${center ? `&center=${enc(center)}` : ''}`,
    ),
  log: (b: string) => request<{ log: string; audit: Record<string, unknown>[] }>(`/okf/bundles/${enc(b)}/log`),
  conformance: (b: string) => request<Record<string, unknown>>(`/okf/bundles/${enc(b)}/conformance`),
  proposals: (b: string, status?: string) => request<Proposal[]>(`/okf/bundles/${enc(b)}/proposals${status ? `?status=${status}` : ''}`),
  proposal: (b: string, id: string) => request<ProposalDetail>(`/okf/bundles/${enc(b)}/proposals/${enc(id)}`),
  approve: (b: string, id: string, payload: { reviewer: string; note: string; edited_frontmatter?: Record<string, unknown>; edited_body?: string }) =>
    request<{ status: string; reason?: string; sync_failures?: { error: string }[] }>(`/okf/bundles/${enc(b)}/proposals/${enc(id)}/approve`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  reject: (b: string, id: string, payload: { reviewer: string; note: string }) =>
    request<Proposal>(`/okf/bundles/${enc(b)}/proposals/${enc(id)}/reject`, { method: 'POST', body: JSON.stringify(payload) }),
  sync: (b: string) => request<Record<string, unknown>>(`/okf/bundles/${enc(b)}/sync`, { method: 'POST' }),
  importBundle: (name: string, file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    return request<{ imported_as: string; conformance: Record<string, unknown> }>(`/okf/import?name=${enc(name)}`, { method: 'POST', body: fd })
  },
  exportUrl: (b: string) => `${API}/okf/bundles/${enc(b)}/export`,
  conversations: (q?: string) => request<Conversation[]>(`/conversations${q ? `?q=${enc(q)}` : ''}`),
  conversation: (id: string) => request<Conversation>(`/conversations/${enc(id)}`),
  deleteConversation: (id: string) => request<unknown>(`/conversations/${enc(id)}`, { method: 'DELETE' }),
  results: () => request<ResultFile[]>('/results'),
  resultFile: (path: string) => request<unknown>(`/results/file?path=${enc(path)}`),
}

export interface ChatRequest {
  question: string
  conversation_id?: string | null
  bundle?: string | null
  use_code?: boolean
  propose_updates?: boolean
}

export type StreamEvent =
  | { event: 'conversation'; data: { conversation_id: string; bundle: string } }
  | { event: 'context'; data: { concepts: ChatAnswer['concepts']; retrieval_mode: string; code_evidence: ChatAnswer['code_evidence']; stage_ms: Record<string, number> } }
  | { event: 'delta'; data: string }
  | { event: 'answer'; data: ChatAnswer }
  | { event: 'error'; data: { message: string } }

/** POST /chat/stream and parse server-sent events from the response body. */
export async function streamChat(req: ChatRequest, onEvent: (e: StreamEvent) => void, signal?: AbortSignal) {
  const res = await fetch(`${API}/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
    signal,
  })
  if (!res.ok || !res.body) {
    let detail = res.statusText
    try {
      detail = (await res.json()).detail ?? detail
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, detail)
  }
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    let idx
    while ((idx = buf.indexOf('\n\n')) >= 0) {
      const raw = buf.slice(0, idx)
      buf = buf.slice(idx + 2)
      onEvent(parseSSE(raw))
    }
  }
}

export function parseSSE(raw: string): StreamEvent {
  let event = 'message'
  const data: string[] = []
  for (const line of raw.split('\n')) {
    if (line.startsWith('event:')) event = line.slice(6).trim()
    else if (line.startsWith('data:')) data.push(line.slice(5).trimStart())
  }
  return { event, data: JSON.parse(data.join('\n')) } as StreamEvent
}
