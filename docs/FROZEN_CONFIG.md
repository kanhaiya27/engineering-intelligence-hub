# Frozen configuration: Systems A–E and every routing tier (Step 2e)

**Frozen 2026-10-06** on dev/val only. No test task has been run, tuned on or read.

All 648 Step 2c trials ran under this configuration:
- 36 dev/val tasks × 6 systems × 3 trials;
- 0 errors and 0 thermal discards;
- one manifest hash for every trial.

| Item | Value |
|---|---|
| **Manifest hash (live)** | **`95e5a587c9d60e7a`** (`ExperimentManifest.create_default(live=True)`; the job queue refuses any mismatch) |
| Code | git `4697594` (branch `master-fix`) |
| Systems | A, B, C, D, E, E + routing (`experiments/m5/manifest.py`) |

**Code that is not in the manifest hash** (sha256, first 16 hex characters):

| File | Hash |
|---|---|
| `intelligence/classifier.py` | `e9b2bf54ee958a2c` |
| `intelligence/complexity.py` | `184a608cf67199e8` |
| `intelligence/criticality.py` | `f7987a27dffa2d07` |
| `retrieval/adaptive.py` | `773f81378cf1a67c` |
| `retrieval/hybrid.py` | `ef3e34890e7e91fc` |
| `retrieval/graph_augmented.py` | `cfec88b09a5279ae` |

## One config for every system and tier

`configs/inference.yaml` (sha256 `a4953733…`) applies to the fixed model and to all three routing
tiers:

| Setting | Value |
|---|---|
| Fixed model (A–E) | `qwen2.5-coder:7b` |
| Routing ladder | 1.5b → 3b → 7b |
| `num_ctx` | 12,288 |
| `num_gpu` | 999 (all layers on the GPU) |
| Temperature | 0.0 |
| Seed | 42 |
| Max output | **2,048 tokens** |
| `keep_alive` | 30m |

Other frozen items:

| Item | Value |
|---|---|
| Retrieval strategies | `configs/retrieval.yaml` sha256 `56d6053b…`: fused-only cut-off 0.25 for the hybrid family (C26) |
| Model registry | `configs/models.yaml` sha256 `bc3fff5d…` |
| Embeddings | BAAI/bge-small-en-v1.5, CUDA, 384-dim |
| Vector collection | `eih_knowledge_v2`, 53,905 points |
| Knowledge graph | 37,066 nodes / 58,982 edges; equals the build report (sha256 `aeed710e…`) |
| Repositories | 6 wave-1 repositories at pinned commits (`datasets/registry.yaml`) |
| Benchmark | tasks sha256 `370e0f74…` (v1.1), splits `87acf6ad…`, labels `d9119576…` (draft) |
| Carbon intensity | 713 gCO₂e/kWh (India) |
| CPU TDP (ESTIMATED CPU energy) | 45 W |
| Trials | 3 on dev/val; N = 5 on the final test (plan Phase 10) |

## Design decisions in this freeze (WORK_PLAN §5)

| Change | What it fixed |
|---|---|
| C23 | System D = System C's retrieval + graph context on every task (A1) |
| C24 | Primary success = correct AND cites labelled evidence (A2) |
| C25 | Classifier rules revised on dev only |
| C26 | Fused-only score cut-off, 0.25 for the hybrid family |
| C19–C22 | No invented scores; whole-trial energy; manifest identity; outcome independent of System E's gate |

## Output limit check (Step 2e)

The master prompt says: if answers hit the cap, raise it for all systems.

| Systems | Trials at the 2,048-token limit | Longest single answer |
|---|---|---|
| A–E (7B) | 0 of 540 | 1,200 tokens |
| E + routing | 9 of 108 | — |

The 9 are 3 tasks × 3 trials:
- **req-008:** the small model repeats one sentence (4% unique words) until the limit.
- **dev-030 and rev-044:** one of three escalation attempts looped.

These are repetition loops, not long answers. A higher limit would not end a loop. It would also
overflow the context window: the ~9K-token prompt of the widest escalation step plus 4,096 output
tokens is more than 12,288.

**Not raised; awaiting decision T1 (ASK_ME).**

## Changes that would reopen the freeze

Approval of any of these is applied, then this file is updated and dev/val is rerun (≈ 2.7 GPU-h at
the measured 15 s per unit):
- **M1** (correctness measure);
- **T1** (repetition loops);
- **V1** (reload before each trial);
- the benchmark fixes in `docs/BENCHMARK_AUDIT.md`;
- the label verification (L1).

The test split is run only after the final freeze and the 12 Oct lock.
