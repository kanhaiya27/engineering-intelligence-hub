import { fileURLToPath as __f2p } from 'node:url'
const __dirname = __f2p(new URL('.', import.meta.url))
import { expect, test } from '@playwright/test'

// Real API + real files. The agent's proposal is filed through the same Python workflow
// the agent uses (no LLM needed), then reviewed in the browser as a person would.

test.beforeEach(async ({ page }) => {
  await page.goto('/status')
  await page.getByLabel('Reviewer id').fill('e2e-tester')
})

test('status page reports live services', async ({ page }) => {
  // first /status call loads the DB and NVML clients
  await expect(page.getByRole('heading', { name: /qdrant/i })).toBeVisible({ timeout: 60_000 })
  await expect(page.getByRole('heading', { name: /neo4j/i })).toBeVisible()
})

test('browse an external OKF bundle: tree, concept, links, trust', async ({ page }) => {
  await page.goto('/knowledge?bundle=e2e')
  await page.getByRole('button', { name: /metrics/ }).click()
  await page.getByRole('button', { name: 'Revenue', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Revenue', level: 2 })).toBeVisible()
  await expect(page.getByText('Human-reviewed').first()).toBeVisible()
  await expect(page.getByRole('heading', { name: /Backlinks/ })).toBeVisible()
  await page.getByRole('button', { name: 'Overview' }).click()
  await expect(page.getByText('OKF conformant')).toBeVisible()
})

test('human edit is saved, attributed and survives reload', async ({ page }) => {
  await page.goto('/knowledge?bundle=e2e&concept=policies/margin-standard')
  await page.getByRole('button', { name: 'Edit' }).click()
  const body = page.getByLabel(/Body \(Markdown/)
  await body.fill((await body.inputValue()) + '\n\nE2E note: reviewed in the browser.\n')
  await page.getByLabel('Change summary').fill('e2e edit')
  await page.getByRole('button', { name: /Save as human:e2e-tester/ }).click()
  await expect(page.getByText('E2E note: reviewed in the browser.')).toBeVisible()
  await page.reload()
  await expect(page.getByText('E2E note: reviewed in the browser.')).toBeVisible()
  await page.getByRole('button', { name: 'History' }).click()
  await expect(page.getByText('human:e2e-tester').first()).toBeVisible()
})

test('agent proposal is reviewed and approved by a person', async ({ page, request }) => {
  // File a proposal as the agent would, through the Python workflow (no LLM involved).
  const { execFileSync } = await import('node:child_process')
  const { resolve } = await import('node:path')
  const { tmpdir } = await import('node:os')
  const repo = resolve(__dirname, '..', '..')
  const code = [
    'import sys',
    'from pathlib import Path',
    'from knowledge.okf.bundle import OKFBundle',
    'from knowledge.okf.collaboration import KnowledgeWorkspace',
    'root = Path(sys.argv[1])',
    "ws = KnowledgeWorkspace(OKFBundle(root / 'e2e'), root / '.eih_state', name='e2e')",
    "p = ws.propose(kind='create', concept_id='glossary/net-revenue', frontmatter={'type': 'Glossary Term', 'title': 'Net revenue'},",
    "  body='Revenue after returns, see [revenue](/metrics/revenue.md).\\n', rationale='Asked in chat; no term defined.', actor='eih_agent/e2e')",
    'print(p.id)',
  ].join('\n')
  const pid = execFileSync(resolve(repo, '.venv311', 'Scripts', 'python.exe'), ['-c', code, resolve(tmpdir(), 'eih-e2e-bundles')], { cwd: repo }).toString().trim()
  expect(pid).toMatch(/^[0-9a-f]{32}$/)

  await page.goto(`/review/${pid}?bundle=e2e`)
  await expect(page.getByText('Asked in chat; no term defined.')).toBeVisible()
  await page.getByRole('button', { name: 'Approve', exact: true }).click()
  // the first approval loads the embedding model to re-index the concept
  await expect(page.getByText('Approved and written to the bundle.')).toBeVisible({ timeout: 60_000 })

  const concept = await (await request.get('http://127.0.0.1:8010/okf/bundles/e2e/concept/glossary/net-revenue')).json()
  expect(concept.generated_by).toBe('eih_agent/e2e')
  expect(concept.trust_tier).toBe('human-reviewed')
})

test('reviewed proposal stays visible in the review history', async ({ page }) => {
  await page.goto('/review?bundle=e2e&status=approved')
  await expect(page.getByText('glossary/net-revenue').first()).toBeVisible()
})
