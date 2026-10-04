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

## 2026-10-05 (later) — Pulled Phase 1b; labels checkout-path fix

**Done**
- Pulled master with A's `feat/local-inference-routing` (PR #8, must-pull) and B2 (PR #5).
  `.env` already had `EIH_QUALITY_MAX_ESCALATION_ATTEMPTS=3`; its keys match `.env.example`.
- `fix/retrieval-labels-repo-dir` (A's request): `benchmark/retrieval_labels.repo_dir()`
  now finds the checkout at `.corpus_cache/<repo_id>` (the `scripts/ingest_corpus.py`
  layout, repo_id from `datasets/registry.yaml`) or the old `.corpus_cache/<owner>__<name>`.
  The pinned-commit check uses `git rev-parse HEAD` instead of reading `.git/HEAD`, so
  normal clones (HEAD = branch ref) also pass. On laptop-b the clones were renamed to
  `flask` / `fastapi`.

**Measured** (laptop-b)
- Label tests: 20 passed, 0 skipped with the old layout and with the ingest_corpus layout;
  `python -m benchmark.retrieval_labels --check`: labels file up to date.
- Full suite: 256 passed.
- Ollama 0.35.1; `qwen2.5-coder` 1.5b / 3b / 7b digests and sizes identical to the
  CLAUDE.md pins (d7372fd8…, f72c60ca…, dae161e2…).

**Next**
- [ ] WORK_PLAN B3: knowledge-graph population.
- [ ] Human verification of the 35 draft labels.

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

## 2026-10-05 — B2: Qdrant healthcheck fixed

**Heads-up (shared file):** `docker-compose.yml`, Qdrant healthcheck only. Neo4j untouched.

**Done**
- `fix/compose-qdrant-healthcheck` (WORK_PLAN B2): the qdrant image has no
  curl/wget/nc, so the curl healthcheck always failed. Replaced it with a bash
  `/dev/tcp` GET of `/readyz` that requires HTTP 200; added `start_period: 20s`.
- Pulled master: confirmed the `.env` fix, since settings now load laptop-b values
  (GPU TDP 115 W, CPU 45 W, custom carbon region) instead of code defaults.

**Measured** (laptop-b)
- Check tested in the running container: exit 0 on `/readyz`, exit 1 on a 404
  path and on a closed port.
- After `docker compose up -d qdrant` (same image v1.15.1, same volume):
  `healthy` within ~6 s; `eih_knowledge` 48,046 points, green (same as before).
- Full suite on this branch: 201 passed.

**Next**
- [ ] WORK_PLAN B1: retrieval ground-truth labels. Open question on the 24
      held-out test tasks vs CLAUDE.md rule 3 (see below).

**Blocked / questions for A**
- B1 asks for labels on all 60 tasks, but 24 are the held-out test split, which
  CLAUDE.md rule 3 says must not be inspected. Agree a protocol before B touches them.
- F1 (found 2026-10-04, unpushed branch `feat/api-contract`): escalated strategies
  (`*_esc1`, `*_esc2_graph`, `*_esc_max`) are not in the registry and silently fall
  back to `hybrid`, so escalation never strengthens retrieval. Verified by execution.
  Relevant to A2 (escalation 2→3).

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