# ROADMAP

Engineering Intelligence Hub — Six-Month Development Roadmap.
Task-level assignment per laptop lives in [docs/WORK_PLAN.md](docs/WORK_PLAN.md); this file
tracks milestones. Last updated 2026-10-05.

---

## Milestone 1 — Research Presentation (25 August 2026) ✅

Research PPT: problem statement, literature review (RAG, green AI, SE agents, adaptive
retrieval, model routing), conservative novelty statement, architecture, evaluation method.

---

## Milestone 2 — Baseline System + Initial Benchmark (15 September 2026) ✅

- [x] Ingestion: Git history, Python AST chunking, Markdown/RST, config files
- [x] Embeddings: BAAI/bge-small-en-v1.5 on the local GPU
- [x] Qdrant vector store; BM25Plus sparse retrieval; weighted hybrid fusion
- [x] Baselines A (LLM only) and B (fixed hybrid RAG)
- [x] 60-task pilot benchmark (6 SDLC stages, flask + fastapi)
- [x] Evaluators (correctness, groundedness, relevance); sustainability instrumentation
- [x] Docker Compose for Qdrant + Neo4j
- [x] Interim project report, SRS, master dataset specification (`docs/`)

---

## Milestone 3 — Major Implementation + Experiments (25 October 2026) 🟡

### Implemented
- [x] **M1 Task intelligence** — rule-based classifier, complexity and criticality analysers
- [x] **M2 Knowledge graph code** — Neo4j + in-memory stores, AST extractor, graph builder
- [x] **M3 Adaptive retrieval** — policy over 21 task types, graph-augmented retriever
- [x] **M4 Quality gate** — 4 deterministic evaluators, bounded escalation, explicit refusal
- [x] **M5 Controlled evaluation** — frozen manifest, seed-42 splits (24/12/24), 3-tier metrics, failure taxonomy, Pareto engine
- [x] **P0-1 / P0-2 audit fixes** — correctness in composite quality; refusals no longer count as success
- [x] **Cross-encoder reranker** with energy accounting; corpus-backed BM25 (hybrid was dense-only before)
- [x] **Corpus wave 1** — 6 repositories, 48,046 chunks
- [x] **Phase 1a** — local-only inference decision; Ollama Qwen2.5-Coder 1.5B/3B/7B pinned by digest;
      NVML energy meter (counter-based, observer effect characterised); run provenance with
      `machine_id`; measured VRAM/throughput/energy study
      (`experiments/results/phase1/machine_A/`)

### Remaining for 25 October (owners in WORK_PLAN.md)
- [ ] **Phase 1b** — OllamaProvider, model routing wired into the pipeline, escalation 2→3, long-context probe, GPU job queue (A)
- [ ] **Retrieval ground truth** for the 60 tasks (B) → **Mode R** retrieval metrics (A)
- [ ] **Knowledge graph populated** for wave-1 repos (B) — required for System D to differ from C
- [ ] **P0-3** — live-model calibration on the validation split, manifest re-frozen (A)
- [ ] **Mode Q** — Systems A–E on dev/val, held-out test once with N=5 (A, Laptop A only)
- [ ] **Pareto frontier + ablation deltas** Δ(A→B)…Δ(D→E), CO₂e per successful task (A)
- [ ] **EIH-SWE batch 1** — 60–100 new human-verified tasks (B)

---

## Milestone 4 — Final Submission (15 November 2026)

- [ ] Paper and report with the measured results (B: docs, A: results)
- [ ] Larger EIH-SWE set; EIH-Fresh contamination-controlled set if time allows
- [ ] Final code freeze with reproducibility documentation (hardware, software, seeds, model digests)
- [ ] Plagiarism check < 10%

---

## After submission / stretch

- Tree-sitter chunking for Java, Go, Rust, TS/JS, C/C++ and corpus waves 2–4 (RQ6)
- Mode P patch + test harness (SWE-bench Pro, Multi-SWE-bench, Defects4J)
- Scalability study (10K → 500K chunks); human study (needs ethics approval)
- Learned router; dashboard / web UI
