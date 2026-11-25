import { fileURLToPath as __f2p } from 'node:url'
const __dirname = __f2p(new URL('.', import.meta.url))
import { defineConfig } from '@playwright/test'
import { resolve } from 'node:path'
import { tmpdir } from 'node:os'

// End-to-end tests run the REAL API and UI on separate ports with an isolated OKF root and
// Qdrant collection (eih_okf_e2e), so the project's own bundle `eih` is never touched.
// Neo4j nodes of the e2e bundle are removed in global teardown.
const repo = resolve(__dirname, '..')
export const E2E_ROOT = resolve(tmpdir(), 'eih-e2e-bundles')
const python = resolve(repo, '.venv311', 'Scripts', 'python.exe')

export default defineConfig({
  testDir: './e2e',
  timeout: 120_000,
  workers: 1,
  globalSetup: './e2e/global-setup.ts',
  globalTeardown: './e2e/global-teardown.ts',
  use: { baseURL: 'http://127.0.0.1:5180', trace: 'retain-on-failure' },
  webServer: [
    {
      command: `"${python}" -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8010`,
      cwd: repo,
      url: 'http://127.0.0.1:8010/health',
      timeout: 120_000,
      reuseExistingServer: false,
      env: {
        EIH_OKF_ROOT: E2E_ROOT,
        EIH_OKF_STATE_DIR: resolve(E2E_ROOT, '.eih_state'),
        EIH_OKF_COLLECTION_NAME: 'eih_okf_e2e',
        EIH_OKF_DEFAULT_BUNDLE: 'e2e',
        EIH_DISABLE_WARMUP: '1',
      },
    },
    {
      command: 'npx vite --port 5180 --strictPort',
      url: 'http://127.0.0.1:5180',
      timeout: 60_000,
      reuseExistingServer: false,
      env: { EIH_API_URL: 'http://127.0.0.1:8010' },
    },
  ],
})
