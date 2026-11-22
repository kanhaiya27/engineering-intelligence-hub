import { describe, expect, it, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import type { ReactNode } from 'react'
import { parseSSE, streamChat } from '../api/client'
import { IdentityProvider, Markdown, MeasurementPanel, TrustBadge } from '../components/common'
import StatusPage from '../pages/StatusPage'

const wrap = (ui: ReactNode) =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter>
        <IdentityProvider>{ui}</IdentityProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  )

afterEach(() => vi.restoreAllMocks())

describe('SSE', () => {
  it('parses one event block', () => {
    expect(parseSSE('event: delta\ndata: "Hel"')).toEqual({ event: 'delta', data: 'Hel' })
  })

  it('streams events split across network chunks', async () => {
    const chunks = ['event: conversation\ndata: {"conversation_id":"c1","bundle":"eih"}\n\nevent: del', 'ta\ndata: "A"\n\nevent: delta\ndata: "B"\n\n']
    const body = new ReadableStream({ start(c) { chunks.forEach((x) => c.enqueue(new TextEncoder().encode(x))); c.close() } })
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(body, { status: 200 }))
    const seen: string[] = []
    await streamChat({ question: 'q?' }, (e) => seen.push(e.event === 'delta' ? `delta:${e.data}` : e.event))
    expect(seen).toEqual(['conversation', 'delta:A', 'delta:B'])
  })

  it('surfaces a 503 from the API instead of an empty answer', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ detail: 'Ollama unavailable' }), { status: 503 }))
    await expect(streamChat({ question: 'q?' }, () => {})).rejects.toThrow('Ollama unavailable')
  })
})

describe('OKF rendering', () => {
  it('turns absolute and relative bundle links into in-app navigation', () => {
    const open = vi.fn()
    wrap(<Markdown text={'[abs](/tables/orders.md) [rel](../metrics/revenue.md) [web](https://x.org)'} conceptId="computations/revenue-ytd" onConcept={open} />)
    fireEvent.click(screen.getByText('abs'))
    fireEvent.click(screen.getByText('rel'))
    expect(open.mock.calls).toEqual([['tables/orders'], ['metrics/revenue']])
    expect(screen.getByText('web').getAttribute('target')).toBe('_blank')
  })

  it('labels trust tiers', () => {
    wrap(<TrustBadge tier="human-reviewed" />)
    expect(screen.getByText('Human-reviewed')).toBeInTheDocument()
  })
})

describe('measurements', () => {
  it('shows each value with its measurement tier and never invents missing energy', () => {
    wrap(<MeasurementPanel m={{ latency_ms: 2500, stage_ms: {}, input_tokens: 900, output_tokens: 120, gpu_energy_joules: null, energy_reliability: null, co2e_grams: null, carbon_intensity_gco2_per_kwh: 713, carbon_region: 'custom', cost_usd: 0, model_id: 'qwen2.5-coder:7b', model_digest: 'dae161e27b0e90dd', machine_id: 'laptop-a', tiers: { latency_ms: 'MEASURED', tokens: 'MEASURED', gpu_energy_joules: 'UNAVAILABLE', co2e_grams: 'UNAVAILABLE', cost_usd: 'ESTIMATED' } }} />)
    expect(screen.getByText('2.5 s')).toBeInTheDocument()
    expect(screen.getAllByText('UNAVAILABLE')).toHaveLength(2)
    expect(screen.getAllByText('—')).toHaveLength(2)
  })
})

describe('status page', () => {
  it('checks services once on demand (no polling of the GPU)', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
      machine_id: 'laptop-a', checked_at: new Date().toISOString(),
      services: { qdrant: { ok: true, points: 53905 }, ollama: { ok: false, error: 'not reachable' } },
    }), { status: 200 }))
    wrap(<StatusPage />)
    await waitFor(() => expect(screen.getByText('53905')).toBeInTheDocument())
    expect(screen.getByText('DOWN')).toBeInTheDocument()
    await new Promise((r) => setTimeout(r, 50))
    expect(fetchSpy).toHaveBeenCalledTimes(1)
  })
})
