machine_id: laptop-b` · Owns: `ingestion/` `knowledge/graph/` `benchmark/`
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