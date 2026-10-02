# PROGRESS — Laptop A (Avaneesh · RTX 4050 6 GB)

`machine_id: laptop-a` · Owns: `routing/` `generation/` `verification/`
`experiments/` `retrieval/` `sustainability/`

Newest entries on top. One entry per working session: what changed, what was
measured (with numbers only if actually measured), what is blocked.

---

## 2026-10-03 — Repository consolidated and shared

**Done**
- Committed ~70 files of uncommitted work from 26 Aug as 8 logical commits on
  `phase-2-intelligence`, to be shared with Laptop B via GitHub.
- Added `.gitattributes` (LF), hardened `.gitignore` (`.corpus_cache/`, snapshots,
  dumps, model weights).
- Test suite: **176 passed, 2 skipped** (the 2 need Docker Qdrant running).
- Added collaboration docs: `CLAUDE.md`, `SETUP_LAPTOP_B.md`, `docs/WORKFLOW.md`.

**State of the system**
- Implemented: ingestion, BGE embeddings (GPU), Qdrant, BM25 (corpus-backed),
  hybrid retrieval, cross-encoder reranker, knowledge graph, task classifier,
  adaptive retrieval, quality gate + escalation, NVML energy, region-aware CO₂e
  (India, 713 gCO₂e/kWh), M5 evaluation framework.
- Audit fixes: P0-1 (correctness in composite quality) and P0-2 (refusal credit
  capped, UNFOUNDED vs VALID refusal) applied with tests.
- Corpus wave 1 ingested: flask, fastapi, requests, pytest, sphinx, pylint —
  48,046 chunks.

**Not done / next**
- [ ] Install Ollama + Qwen2.5-Coder 1.5B / 3B / 7B-Q4; wire `routing/` into the pipeline (RQ4).
- [ ] P0-3: re-run validation calibration with a live local LLM; re-freeze manifest.
- [ ] Decide `max_escalation_attempts` 2 → 3 (reranking rung unreachable at 2).
- [ ] Record `machine_id` automatically in experiment logs.
- [ ] First real Mode R / Mode Q run of Systems A–E (dev split only).

**Blocked / decisions needed**
- Large-LLM baseline strategy (dataset spec §7.3).
- Licence audit for external datasets (dataset spec §4.1).
