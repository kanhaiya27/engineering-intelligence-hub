# PROGRESS — Laptop A (Avaneesh · RTX 4050 6 GB)

`machine_id: laptop-a` · Owns: `routing/` `generation/` `verification/`
`experiments/` `retrieval/` `sustainability/`

Newest entries on top. One entry per working session: what changed, what was
measured (with numbers only if actually measured), what is blocked.

---

## 2026-10-05 (night) — Phase 1b step 7: GPU job queue

Branch `feat/gpu-job-queue` (off `feat/local-inference-routing`; task A2 step 7).

**Done**
- `scripts/job_queue.py`: one unit = (system, task, trial). Exactly-once ledger
  (`results.jsonl`, fsynced; re-running the same `--run-id` resumes, a half-written line
  from a crash re-runs), errors recorded with the exception (never dropped;
  `--retry-errors`), units interleaved and shuffled per trial round (seed 42) so no
  system always runs first/last, the 90 °C discard-cool-repeat rule (temperature read
  between units only), a GPU lock file, and the held-out test split only with
  `--final-test`, once. Writes `run.json` (provenance), `plan.jsonl`, `discarded.jsonl`,
  `summary.json` under `experiments/results/queue/<machine>/<run-id>/`.
- Tests: 11 new; full suite **267 passed**.
- Smoke run (2 dev tasks × baseline_a + system_e × 1 trial, real Ollama/Qdrant, written
  to scratch — not a result): 4/4 ok, resume re-ran 0 units.

**Found (for A3 — runner defects, not queue defects)**
- **System A refuses everything:** `BaselineRAGPipeline` with `skip_retrieval=True` still
  uses the evidence-only SYSTEM_PROMPT, so the 7B answers "INSUFFICIENT EVIDENCE" (~1.5 s,
  47–59 tokens) → A→B would measure a strawman. A needs its own no-evidence prompt.
- **Measured energy never reaches the trial record:** `M5BenchmarkRunner._evaluate_trial`
  sets `gpu_energy_measured_joules=None` and computes `cpu/gpu_energy_joules` as
  45 W / 60 W × latency; the NVML energy from `OllamaProvider` (and its per-call max
  temperature) is dropped. Must be wired before any A–E number counts.

**Next**
- [ ] Step 8: PRs (`feat/local-inference-routing` = step 6, then this branch)
- [ ] A3: fix the two runner defects above, manifest re-freeze, live calibration

---

## 2026-10-05 (evening) — Phase 1b step 6: long-context probe → context budget

Branch `feat/local-inference-routing` (task A2). Script `scripts/phase1_long_context_probe.py`.

**Decision (owner, 2026-10-05):** every model and system runs at **num_ctx 12,288, all
layers on the GPU (`num_gpu 999`), output limit 1,024 tokens** (was 4,096 / 2,048).
Thermal rule for long runs: work up to 90 °C; a condition with a call above 90 °C is
discarded and repeated after cooling to 65 °C.

**Measured** (laptop-a, encoders resident, real-corpus prompts, 1 cold + 2 warm per point)
- Prompt sizes (`long_context_sizes.md`): overhead 236 tokens; formatted chunk p50 117,
  p95 515, p99 903. DERIVED prompt for the widest rung (20–24 chunks): p95 5.5–6.4K,
  p99 7.5–9.0K tokens → fits 12,288 − 1,024.
- 7B all-on-GPU (`long_context_probe.md`): 4K 37.0 tok/s · 8K 35.4 · **12K 34.6 tok/s,
  peak 5,906 / 6,141 MiB, ~763 J/call** · 16K 33.1, VRAM full (6,088) · 20K prefill
  collapses 1,400 → 237 tok/s, 90 s, 3.2 kJ/call · 24K 170 s, 5.4 kJ/call. Ollama still
  reports 100% on GPU at 20K+: the WDDM driver pages to system RAM.
- 7B Ollama default placement: 82% → 64% on GPU as context grows; decode 20.1 → 3.3 tok/s.
- At 12K (`ctx12k_small_models/`): 1.5B 111 tok/s, peak 2,338 MiB; 3B 68.5 tok/s, peak
  3,368 MiB; both 100% on GPU.
- Routing switch 7B → 3B → 1.5B → 7B via the real provider at 12K with ~8.9K-token
  prompts: Ollama evicts the 7B for the smaller models and vice versa; every call 100% on
  GPU, context check headroom ~3,150 tokens.
- Tests: 256 passed (one test updated: all tiers now get `num_gpu 999`).

**Found**
- **81 corpus chunks are > 2,048 tokens, 9 are > 8,192, the largest 67,021** (lockfiles,
  contributor/sponsor lists, `plugin_list.rst`, a 39K-token test file). The prompt guard
  refuses such prompts (no silent truncation), but they must be fixed at ingestion — asked
  Laptop B (see Must pull / Blocked).
- At 24K the Qwen tokenizer counted 23 tokens more than Ollama (exact match up to 20K);
  over-counting is the safe direction for the truncation guard.

**Must pull (Laptop B)** — `core/config.py` max_tokens 2048 → 1024; `configs/models.yaml`
`num_gpu 999` for all three models; `OllamaProvider.DEFAULT_NUM_CTX` 4096 → 12288.

**Blocked / for Laptop B (before A3, ~14 Oct)**
- Re-chunk: cap chunks at ~512 tokens (BGE-small embeds only the first 512) and skip
  lockfiles / generated data; re-ingest, new snapshot in `C:\EIH_share\`, re-check labels.

**Next**
- [ ] Step 7: `scripts/job_queue.py`; Step 8: PR
- [ ] A3: correct and re-freeze the manifest (also stale: `model_max_tokens` 2048)

---

## 2026-10-05 — Phase 1b (steps 1–5 of 8): OllamaProvider, routing, escalation

Branch `feat/local-inference-routing` (task A2 in `docs/WORK_PLAN.md`).

**Done**
- **Decision:** Systems A–E use a fixed `qwen2.5-coder:7b`, all layers on the GPU;
  routing (1.5B→3B→7B) is an added system compared against it (RQ4).
- 7B option A measured (`vram_study_7b_forced_gpu.json`): forcing all layers onto
  the GPU fits and is faster and cheaper (numbers below).
- `OllamaProvider`: temperature 0 + seed 42, exact tokens, cold start measured
  separately, NVML energy per call (MEASURED), cost 0 (DERIVED), model digest,
  and it **refuses prompts that would be silently truncated** (exact Qwen
  tokenizer count matched Ollama 702 = 702).
- **Silent defects fixed:** pipelines and M5 runners fell back to `MockLLMProvider`
  when no OpenAI key was set (the final-test CLI would have run on the mock); the
  manifest's escalation limit never reached the pipeline; the `.env` escalation
  value was never read; `configs/default.yaml` is not loaded at runtime (labelled).
- `TierRouter` wired into `QualityAwareRAGPipeline`; tests assert the `model`
  field of every HTTP request actually sent. Escalation limit 2 → 3 (manifest hash
  `fcdbfa1b825d11e4` → `aa733133d041f11c`).
- Tests: **229 passed** (incl. live Ollama tests on this laptop).

**Measured** (Laptop A, warm n=5, ~1,338 prompt + 128 output tokens, num_ctx 4096)
- 7B default placement (82% on GPU): 22.1 tok/s, 390.1 ± 8.9 J per call
- 7B `num_gpu=999` (100% on GPU): **38.1 tok/s, 306.8 ± 11.8 J per call**, device
  peak 5,342 MiB of 6,141 with the encoders resident; reached 89 °C with hw thermal slowdown

**Must pull (Laptop B)**
- Defaults changed: provider `ollama`, model `qwen2.5-coder:7b`, temperature 0.
- **Edit your `.env`: `EIH_QUALITY_MAX_ESCALATION_ATTEMPTS=3`** (yours says 2, and
  `.env` values are now actually applied).
- Runs without an explicit provider now use the real Ollama; `--provider mock` only for tests.

**Next**
- [ ] Step 6: 20K-token long-context probe → set the context budget (needed before
      any real run: the final escalation rung can exceed num_ctx 4096) — STOP point
- [ ] Step 7: `scripts/job_queue.py`; Step 8: PR
- [ ] A3: correct and re-freeze the manifest (stale: gpt-4o-mini, temp 0.1, UK carbon,
      60 W, OpenAI prices, 2 repos)

---

## 2026-10-05 (later) — Two-laptop git sync guard

Branch `chore/git-sync-guard`.

**Done**
- PR #4 (Phase 1a) merged to `master` (`a29ccfa`).
- `scripts/git_sync_guard.py` + hooks in `.claude/settings.json`: at session start Claude fetches
  and reports what the other laptop merged; code edits are blocked while a must-pull change
  (`[must-pull]` tag or any shared-file change) is missing. 6 end-to-end tests on throwaway repos.
- CLAUDE.md session routine rewritten around the guard; WORK_PLAN §6 updated.

**Must pull** — this change itself is `[must-pull]`: Laptop B must `git pull` on master, then
restart Claude Code (or open `/hooks`) and approve the project hooks when asked.

**Next** — Phase 1b on `feat/local-inference-routing` once the 7B decision is made.

---

## 2026-10-05 — Phase 1a: local inference audit, energy meter, VRAM study

Branch `feat/local-inference` (task A1 in `docs/WORK_PLAN.md`).

**Done**
- Environment audit: RTX 4050 Laptop 6141 MiB, driver 617.14, NVML default power limit
  80 W (max 140 W); torch 2.6.0+cu124; Ollama 0.35.1; qwen2.5-coder 1.5b/3b/7b (all
  Q4_K_M) pinned by digest in `CLAUDE.md`. `.env`: `laptop-a`, CPU 45 W, GPU 60 → 80 W.
- **Bug fixed:** 8 settings groups never read `.env` (only OS env vars) on either laptop —
  TDP, carbon, quality, reranking and graph settings in `.env` were ignored. Now fixed,
  12 regression tests.
- New `NvmlEnergyMeter` (energy counter at start/end only), `experiments/provenance.py`
  (machine_id, GPU, torch/CUDA, Ollama digests, git SHA in every result), `Settings.machine_id`.
- **Measurement finding:** querying the GPU during a measurement perturbs the energy
  counter on this driver (power polling +9–12 W, counter polling +100 W; evidence in
  `experiments/results/phase1/machine_A/nvml_observer_probe.json`). First VRAM-study run
  discarded and re-run with the fixed meter.
- `docs/WORK_PLAN.md` created; README, ROADMAP, CHANGELOG, CLAUDE.md, report updated.

**Measured** (Laptop A, git `215a482`, `experiments/results/phase1/machine_A/vram_study.{json,md}`;
~1,338 prompt + 128 output tokens, num_ctx 4096, temp 0, seed 42; warm n=5, co-resident with encoders)
- 1.5B: 100% on GPU, device peak 1920 MiB, 131 tok/s, **105.7 ± 10.3 J** per call
- 3B: 100% on GPU, device peak 2870 MiB, 76 tok/s, **174.2 ± 10.7 J** per call
- 7B: **82% on GPU** (3992 of 4886 MiB), device peak 4806 MiB, 22 tok/s, **390.1 ± 8.9 J** per call
- Encoders (BGE-small + cross-encoder): +490 MiB device VRAM
- Test suite: 200 passed (Qdrant up) at `8378760`

**Next** (Phase 1b, branch `feat/local-inference-routing`)
- [ ] Decide 7B handling: A) force all layers on GPU (`num_gpu`) and measure, B) A + flash attention, C) accept 82%
- [ ] `OllamaProvider`; routing wired with per-call model-id logging and tests
- [ ] `max_escalation_attempts` 2 → 3 — NB `.env.example` now pins it (show manifest-hash change first)
- [ ] 20K-token long-context probe for the 7B KV cache (large-LLM baseline options)
- [ ] `scripts/job_queue.py`
- [ ] Re-measure reranker energy in batches (report §10.4 figures came from one power sample)

**Blocked / decisions needed**
- 7B handling (above). Large-LLM baseline strategy (dataset spec §7.3). Licence audit (§4.1).

---

## 2026-10-03 — Repository consolidated and shared

**Done**
- Committed ~70 files of uncommitted work from 26 Aug as 8 logical commits on
  `phase-2-intelligence`, to be shared with Laptop B via GitHub.
- Added `.gitattributes` (LF), hardened `.gitignore` (`.corpus_cache/`, snapshots,
  dumps, model weights).
- Test suite: **176 passed, 2 skipped** (the 2 need Docker Qdrant running).
- Added collaboration docs: `CLAUDE.md`, `SETUP_LAPTOP_B.md`, `docs/WORKFLOW.md`.
- Exported Qdrant `eih_knowledge` (48,046 points) to `C:\EIH_share\eih_knowledge.snapshot`
  (169 MB, SHA256 `a5b20b44…cbced7`); restore verified into a clean Qdrant v1.15.1.
  No Neo4j dump: the graph holds only a 2-node test fixture.

**State of the system**
- Implemented: ingestion, BGE embeddings (GPU), Qdrant, BM25 (corpus-backed),
  hybrid retrieval, cross-encoder reranker, knowledge graph, task classifier,
  adaptive retrieval, quality gate + escalation, NVML energy, region-aware CO₂e
  (India, 713 gCO₂e/kWh), M5 evaluation framework.
- Audit fixes: P0-1 (correctness in composite quality) and P0-2 (refusal credit
  capped, UNFOUNDED vs VALID refusal) applied with tests.
- Corpus wave 1 ingested: flask, fastapi, requests, pytest, sphinx, pylint —
  48,046 chunks.

**Not done / next** (superseded by the 2026-10-05 entry above)
- [x] Install Ollama + Qwen2.5-Coder 1.5B / 3B / 7B-Q4 (done 2026-10-04).
- [ ] Wire `routing/` into the pipeline (RQ4).
- [ ] P0-3: re-run validation calibration with a live local LLM; re-freeze manifest.
- [ ] Decide `max_escalation_attempts` 2 → 3 (reranking rung unreachable at 2).
- [x] Record `machine_id` automatically (`experiments/provenance.py`, 2026-10-05).
- [ ] Laptop A's existing `eih-qdrant` container (and its volume data) is still
      Qdrant **v1.13.2**, while `docker-compose.yml` pins v1.15.1. Do NOT run
      `docker compose up` on it blindly (that jumps two minor versions on the stored
      data); use `docker start eih-qdrant` for now, then either upgrade via 1.14.x
      or recreate the volume from `C:\EIH_share\eih_knowledge.snapshot`.
- [ ] First real Mode R / Mode Q run of Systems A–E (dev split only).

**Blocked / decisions needed**
- Large-LLM baseline strategy (dataset spec §7.3).
- Licence audit for external datasets (dataset spec §4.1).
