# PROGRESS — Laptop B (RTX 5050 8 GB)

`machine_id: laptop-b` · Owns: `ingestion/` `knowledge/graph/` `benchmark/`
`apps/` `web/` `docs/`

Newest entries on top. One entry per working session: what changed, what was
measured (with numbers only if actually measured), what is blocked.

## Machine

| Item | Value |
|---|---|
| GPU / VRAM | RTX 5050 Laptop / 8 GB |
| CPU | Intel Core 7 240H |
| RAM | 24 GB |
| NVIDIA driver | 617.14 |
| PyTorch / CUDA | 2.11.0 + cu128 |
| GPU power limit (W) (`nvidia-smi -q -d POWER`) | 115 |

---

## 2026-10-05 — API contract v1, review findings, project plan

**Done**
- `feat/api-contract`: frozen v1 pipeline-trace contract (`apps/api/contract/`,
  `docs/API_CONTRACT.md`, `docs/api/openapi-v1.json`), 31 contract tests. Awaiting
  review by Laptop A (contract is jointly owned).
- `docs/project-plan`: `docs/PROJECT_PLAN.md` (status, remaining work, two-laptop
  split, timeline, decisions D1–D8); README, ROADMAP, CLAUDE.md, WORKFLOW,
  PROJECT_REPORT §10.5/§11 and dataset spec §11 brought up to date.

**Measured** (only numbers from runs that actually executed)
- Full suite on `feat/api-contract`: 209 passed (178 existing + 31 contract) on laptop-b.
- F1, by executing the escalation path against `configs/retrieval.yaml`: escalated
  attempts 1/2/3 requested top_k 10/16/30 (graph on from attempt 2, rerank at 3);
  executed strategy was `hybrid` (top_k 7, no graph, no rerank) every time.

**Next** (Laptop B, see `docs/PROJECT_PLAN.md` §4.2)
- [ ] B1 get `feat/api-contract` reviewed and merged.
- [ ] B2 licence audit (`docs/licence-audit`).
- [ ] B3 web backend hardening + `/v1/trace` stream with mock/cached fallback (`feat/web-backend`).
- [ ] B4 knowledge-graph population plan, then build.

**Blocked / questions for A**
- F1 (escalation fallback) blocks every System E result. Please take A1 first.
- F2–F5 energy provenance (`docs/API_CONTRACT.md` §8), A2 per-attempt objects for the live endpoint.
- Decisions D1 (which machine runs the final A–E), D2 (site hosting).

---

## 2026-10-04 — Laptop B setup complete

**Done**
- Installed the toolchain, created the `.venv311` environment and installed PyTorch (cu128) on the RTX 5050.
- Created `.env` for laptop-b with local CPU/GPU power values (45 W / 115 W).
- Started Qdrant and Neo4j with Docker Compose.
- Loaded the shared snapshot into Qdrant (eih_knowledge, 48,046 points, status green).
- Verified Neo4j Browser login on localhost:7474 (graph empty, as expected).

**Measured** (only numbers from runs that actually executed)
- GPU embedding test: BAAI/bge-small-en-v1.5 loaded on cuda:0, vector dimension 384.
- Full test suite: 178 passed, 8 warnings in 152.53 s (laptop-b).

- [ ] Open this PR for review.
- [ ] Start the first assigned feature branch.

**Blocked / questions for A**
- None.