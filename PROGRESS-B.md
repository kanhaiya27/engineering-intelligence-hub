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