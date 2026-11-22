// Shapes returned by the EIH API (apps/api/routers/okf.py, chat.py, health.py, results.py).

export type TrustTier = 'unverified' | 'machine-confirmed' | 'human-reviewed'

export interface ConceptSummary {
  id: string
  title: string
  type: string
  description: string
  tags: string[]
  status: string
  trust_tier: TrustTier
  stale: boolean
  generated_by: string | null
  generated_at: string | null
  score?: number
}

export interface Bundle {
  name: string
  concepts: number
  conformant: boolean
  errors: number
  broken_links: number
  declared_okf_version: string | null
  types: Record<string, number>
  pending_proposals: number
  default: boolean
}

export interface TreeNode {
  name: string
  path: string
  count: number
  dirs: TreeNode[]
  concepts: { id: string; title: string; type: string; trust_tier: TrustTier; status: string }[]
}

export interface ConceptLink {
  text: string
  target: string
  resolved: string | null
  external: boolean
  broken: boolean
}

export interface AuditEvent {
  at: string
  action: string
  actor: string
  [key: string]: unknown
}

export interface ConceptDetail extends ConceptSummary {
  frontmatter: Record<string, unknown>
  body: string
  content_hash: string
  path: string
  warnings: string[]
  errors: string[]
  links: ConceptLink[]
  backlinks: ConceptSummary[]
  sources: { id?: string; resource: string; title?: string }[]
  pending_proposals: string[]
  history: AuditEvent[]
}

export interface Proposal {
  id: string
  bundle: string
  kind: 'create' | 'update' | 'deprecate'
  concept_id: string
  proposed_frontmatter: Record<string, unknown>
  proposed_body: string
  rationale: string
  proposed_by: string
  created_at: string
  base_hash: string | null
  evidence: Record<string, unknown>[]
  conflicts_with: string[]
  status: 'pending' | 'approved' | 'rejected' | 'conflict'
  reviewed_by: string | null
  reviewed_at: string | null
  review_note: string | null
}

export interface ProposalDetail {
  proposal: Proposal
  current: { frontmatter: Record<string, unknown>; body: string; content_hash: string } | null
  stale: boolean
}

export interface ContextConcept {
  concept_id: string
  title: string
  type: string
  trust_tier: TrustTier
  status: string
  stale: boolean
  reason: string
  score: number | null
}

export interface CodeEvidence {
  n: number
  repository: string | null
  source_path: string | null
  start_line: number | null
  end_line: number | null
  score: number
}

export interface Measurements {
  latency_ms: number
  stage_ms: Record<string, number>
  input_tokens: number
  output_tokens: number
  gpu_energy_joules: number | null
  energy_reliability: string | null
  co2e_grams: number | null
  carbon_intensity_gco2_per_kwh: number
  carbon_region: string
  cost_usd: number
  model_id: string
  model_digest: string | null
  machine_id: string
  tiers: Record<string, string>
}

export interface ChatAnswer {
  conversation_id: string
  message_id: string
  question: string
  answer: string
  insufficient_evidence: boolean
  citations: string[]
  invalid_citations: string[]
  concepts: ContextConcept[]
  code_evidence: CodeEvidence[]
  proposals: Proposal[]
  rejected_proposals: { gap: unknown; reason: string }[]
  retrieval_mode: string
  model_id: string
  measurements: Measurements
}

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  meta: Partial<ChatAnswer> & { error?: string } | null
  created_at: string
}

export interface Conversation {
  id: string
  title: string
  bundle: string | null
  created_at: string
  updated_at: string
  message_count?: number
  messages?: Message[]
}

export interface ServiceStatus {
  machine_id: string
  checked_at: string
  services: Record<string, { ok: boolean; error?: string; [k: string]: unknown }>
}

export interface ResultFile {
  path: string
  bytes: number
  group: string
  study?: string | null
  keys?: string[]
  provenance?: {
    recorded_at_utc: string | null
    machine_id: string | null
    gpu_driver: string | null
    git_sha: string | null
    git_dirty: boolean | null
  }
}
