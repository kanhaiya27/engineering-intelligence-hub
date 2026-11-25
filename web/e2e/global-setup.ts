import { fileURLToPath as __f2p } from 'node:url'
const __dirname = __f2p(new URL('.', import.meta.url))
import { cpSync, mkdirSync, rmSync } from 'node:fs'
import { resolve } from 'node:path'
import { tmpdir } from 'node:os'

// A fresh e2e bundle: Google's acme_retail sample (an externally produced OKF bundle).
export default function globalSetup() {
  const root = resolve(tmpdir(), 'eih-e2e-bundles')
  rmSync(root, { recursive: true, force: true })
  mkdirSync(root, { recursive: true })
  cpSync(resolve(__dirname, '..', '..', 'tests', 'test_knowledge', 'fixtures', 'okf_external', 'acme_retail'), resolve(root, 'e2e'), { recursive: true })
}
