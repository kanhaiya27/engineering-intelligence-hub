# PROGRESS — Laptop B (Sanvi · RTX 5050 8 GB)

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

## 2026-10-05 — B1: retrieval labels for dev + val (draft)

**Heads-up (shared file):** `knowledge/schemas/benchmark.py`. Adds new models
(`RetrievalGroundTruth`, `RequiredEvidence`, `RetrievalLabelSet`); `BenchmarkTask` unchanged.

**Done**
- `feat/benchmark-retrieval-labels` (WORK_PLAN B1): retrieval ground truth for the
  36 dev+val tasks in `benchmark/data/retrieval_labels_v1.json`, built by
  `benchmark/retrieval_labels.py` from directives resolved against the pinned
  source. Protocol and findings: `docs/RETRIEVAL_LABELS.md`.
- Held-out test split not loaded or labelled (decision: blind pass later, protocol
  to be agreed with A).

**Measured** (laptop-b)
- Ingested commits from Qdrant payloads: flask `c12a5d8` (1,489 chunks / 188 files),
  fastapi `1c3e691` (18,899 chunks / 1,902 files).
- 36 labels, 76 evidence spans, 48 distinct files; every span overlaps ≥1 indexed chunk.
- 16 of 36 tasks have problems in existing evidence/ground truth (12 wrong line
  ranges; ops-052 premise absent from FastAPI; ops-053 contradicts CHANGES.rst;
  rev-045 likely outdated; code-014 cache name and range wrong).
- Tests: 18 new (incl. 2 integration: rebuild matches, span hashes match);
  full suite 219 passed.

**Next**
- [ ] Human verification of the 35 draft labels (`docs/RETRIEVAL_LABELS.md` §3).
- [ ] WORK_PLAN B3: knowledge-graph population.

**Blocked / questions for A**
- ops-052 and ops-053 are **val** tasks; exclude or fix before P0-3 calibration (A3).
- Agree the blind labelling protocol for the 24 test tasks (§4 of the doc).

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

**Next**
- [ ] Open this PR for review.
- [ ] Start the first assigned feature branch.

**Blocked / questions for A**
- None.