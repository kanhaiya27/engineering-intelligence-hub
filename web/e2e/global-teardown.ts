import { fileURLToPath as __f2p } from 'node:url'
const __dirname = __f2p(new URL('.', import.meta.url))
import { execFileSync } from 'node:child_process'
import { rmSync } from 'node:fs'
import { resolve } from 'node:path'
import { tmpdir } from 'node:os'

// Remove everything the e2e run projected: its Qdrant collection and its Neo4j OKF nodes
// (bundle names e2e*), then the temp bundle directory. Research data is never touched.
export default function globalTeardown() {
  const repo = resolve(__dirname, '..', '..')
  const py = resolve(repo, '.venv311', 'Scripts', 'python.exe')
  const code = [
    'from qdrant_client import QdrantClient',
    'from knowledge.graph.neo4j import Neo4jGraphStore',
    "c = QdrantClient(host='localhost', port=6333)",
    "c.delete_collection('eih_okf_e2e') if c.collection_exists('eih_okf_e2e') else None",
    "Neo4jGraphStore().query(\"MATCH (n:OKFConcept) WHERE n.bundle STARTS WITH 'e2e' DETACH DELETE n\")",
  ].join('\n')
  execFileSync(py, ['-c', code], { cwd: repo, stdio: 'inherit' })
  rmSync(resolve(tmpdir(), 'eih-e2e-bundles'), { recursive: true, force: true })
}
