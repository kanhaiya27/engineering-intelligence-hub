import { createContext, useContext, useState, type ReactNode } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { Measurements, TrustTier } from '../api/types'

// ------------------------------------------------------------------ reviewer identity

const KEY = 'eih.reviewer'

function readId(): string {
  try {
    return localStorage.getItem(KEY) ?? ''
  } catch {
    return ''
  }
}

const IdentityCtx = createContext<{ id: string; actor: string | null; setId: (v: string) => void }>({
  id: '',
  actor: null,
  setId: () => {},
})

export function IdentityProvider({ children }: { children: ReactNode }) {
  const [id, setIdState] = useState(readId)
  const setId = (v: string) => {
    const clean = v.replace(/[^A-Za-z0-9_.@-]/g, '').slice(0, 64)
    setIdState(clean)
    try {
      localStorage.setItem(KEY, clean)
    } catch {
      /* private mode */
    }
  }
  return <IdentityCtx.Provider value={{ id, actor: id ? `human:${id}` : null, setId }}>{children}</IdentityCtx.Provider>
}

export const useIdentity = () => useContext(IdentityCtx)

// ------------------------------------------------------------------ badges

const TRUST_LABEL: Record<TrustTier, string> = {
  'human-reviewed': 'Human-reviewed',
  'machine-confirmed': 'Machine-confirmed',
  unverified: 'Unverified',
}

export function TrustBadge({ tier }: { tier: TrustTier | string }) {
  return (
    <span className={`badge trust-${tier}`} title="OKF trust tier (§5.3), derived from `verified`">
      {TRUST_LABEL[tier as TrustTier] ?? tier}
    </span>
  )
}

export function StatusBadge({ status, stale }: { status?: string; stale?: boolean }) {
  return (
    <>
      {status && status !== 'stable' && <span className={`badge status-${status}`}>{status}</span>}
      {stale && <span className="badge status-stale" title="now ≥ stale_after (OKF §5.5)">stale</span>}
    </>
  )
}

export function TierTag({ tier }: { tier?: string }) {
  if (!tier) return null
  return <span className={`tier tier-${tier.toLowerCase()}`}>{tier}</span>
}

// ------------------------------------------------------------------ markdown

/** Render OKF markdown. Bundle links (absolute `/x.md` or relative) open in the explorer. */
export function Markdown({ text, conceptId, onConcept }: { text: string; conceptId?: string; onConcept?: (id: string) => void }) {
  const resolve = (href: string): string | null => {
    if (/^[a-z][a-z0-9+.-]*:/i.test(href) || href.startsWith('#') || !href.endsWith('.md')) return null
    const base = href.startsWith('/') ? [] : (conceptId ?? '').split('/').slice(0, -1)
    const parts = [...base]
    for (const seg of href.replace(/^\//, '').split('/')) {
      if (seg === '..') parts.pop()
      else if (seg && seg !== '.') parts.push(seg)
    }
    return parts.join('/').replace(/\.md$/, '')
  }
  return (
    <div className="markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href = '', children }) => {
            const id = onConcept ? resolve(href) : null
            if (id)
              return (
                <a href={`#concept:${id}`} onClick={(e) => { e.preventDefault(); onConcept?.(id) }}>
                  {children}
                </a>
              )
            return <a href={href} target="_blank" rel="noreferrer">{children}</a>
          },
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  )
}

// ------------------------------------------------------------------ states

export function Loading({ what = 'Loading' }: { what?: string }) {
  return <div className="state">{what}…</div>
}

export function ErrorBox({ error }: { error: unknown }) {
  const msg = error instanceof Error ? error.message : String(error)
  return <div className="state error" role="alert">{msg}</div>
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="state empty">{children}</div>
}

// ------------------------------------------------------------------ measurements

const fmt = (v: number | null | undefined, digits = 1, unit = '') =>
  v === null || v === undefined ? '—' : `${v.toLocaleString(undefined, { maximumFractionDigits: digits })}${unit}`

export function MeasurementPanel({ m }: { m?: Measurements }) {
  if (!m) return null
  const rows: [string, string, string | undefined][] = [
    ['Latency', fmt(m.latency_ms / 1000, 2, ' s'), m.tiers?.latency_ms],
    ['Tokens in / out', `${fmt(m.input_tokens, 0)} / ${fmt(m.output_tokens, 0)}`, m.tiers?.tokens],
    ['GPU energy', fmt(m.gpu_energy_joules, 1, ' J'), m.tiers?.gpu_energy_joules],
    ['CO₂e', fmt(m.co2e_grams, 4, ' g'), m.tiers?.co2e_grams],
    ['Cost', `$${fmt(m.cost_usd, 4)}`, m.tiers?.cost_usd],
  ]
  return (
    <div className="measurements">
      <table>
        <tbody>
          {rows.map(([k, v, t]) => (
            <tr key={k}>
              <th>{k}</th>
              <td>{v}</td>
              <td><TierTag tier={t} /></td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="fine">
        {m.model_id}{m.model_digest ? ` · ${m.model_digest.slice(0, 12)}` : ''} · {m.machine_id} · grid {m.carbon_region} (
        {m.carbon_intensity_gco2_per_kwh} gCO₂e/kWh)
        {m.energy_reliability === 'low_short_window' && ' · energy window too short to be reliable'}
      </p>
      {m.stage_ms && (
        <p className="fine">
          {Object.entries(m.stage_ms).map(([k, v]) => `${k.replace('_', ' ')} ${fmt(v / 1000, 2)} s`).join(' · ')}
        </p>
      )}
    </div>
  )
}
