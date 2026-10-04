# Master EIH Dataset Specification

**Status:** v0.1 DRAFT — source of truth for all EIH data decisions
**Owner:** EIH research team (4 members)
**Last updated:** 2026-08-26
**Supersedes:** ad-hoc dataset choices in `DATASET_PLAN.md`

> This document defines every dataset, its source, licence, schema, role, execution mode,
> and the research question it serves. **No dataset enters an experiment without an entry
> here.** No number in this file is recalled from memory; every external fact carries a
> citation to its paper or repository (§10).

---

## 1. Locked decisions

| Decision | Value | Consequence |
|---|---|---|
| Execution scope | **All six tiers executed** | Nothing is cite-only. See §3 for what "executed" means per dataset. |
| Inference | **Local models only, no paid API** | Energy is directly NVML-measurable and fully attributable. This is a methodological strength, not a limitation — see §7.1. |
| EIH-SWE size | **400–500 human-verified tasks** | ~110 tasks per team member. Annotation starts immediately, in parallel with code. |
| Target venue | **Top SE journal (TOSEM / TSE / EMSE)** | Demands contamination control, statistical rigour, reproducibility artifacts. |

### 1.1 Honest note on the impact-factor goal

The stated ambition was an impact factor around 10–12. Factually: TOSEM, TSE and EMSE sit
roughly in the 4–7 band, and an IF above 10 is very rare in software engineering — it occurs
mainly in general-science and broad-AI venues, not SE. The realistic high-ceiling options are:

- **TOSEM / TSE** — highest SE journal prestige.
- **Journal of Systems and Software / EMSE** — strong fit for the sustainability angle.
- **ICSE / FSE / ASE** — highest SE prestige overall, but conferences carry *no* impact factor.

Chasing an IF number is the wrong optimisation target. What actually earns a top-venue
acceptance here is the combination this project is already positioned for: a novel
quality-constrained efficiency framing, a contamination-aware benchmark methodology, honest
negative results where they occur, and full reproducibility. **The dataset methodology in this
document is itself a publishable contribution.** That is the stronger story.

---

## 2. Feasibility envelope — read before planning any run

Local-only inference on one RTX 4050 Laptop (6 GB VRAM). Assume 5 systems × 3 trials and
~4 s per generation for a 7B 4-bit model with RAG context.

| Interpretation of "full runs" | Instances | GPU-time |
|---|---|---|
| Literally every published row | 2,652,192 | **1,842 GPU-days (≈5 years)** |
| Each dataset's *intended* evaluation slice | 9,377 | **6.5 GPU-days** |

**98% of the impossible version is four datasets:** CommitBench (1.6M), CodeRepoQA (585,687),
PrimeVul (~226k), Big-Vul (~188k).

These four are **corpora, not evaluation sets**. Their own papers evaluate on samples. Using a
stratified sample of a corpus is using it *as designed* — it is not scope reduction. Every tier
is still executed; every dataset still contributes evidence.

**Rule:** an instance count in this document is always the *evaluation slice*, never the raw
row count. Both are recorded in §4 so the distinction is never lost.

### 2.1 GPU budget policy

- Target ≤ **10 GPU-days** total for the full experimental programme, leaving headroom for
  re-runs after bugs (there will be bugs).
- Any single dataset exceeding **1.5 GPU-days** must be sampled down, with the sampling
  procedure and seed recorded in §4.
- Every run logs wall-clock and NVML energy so the cost of the research itself is reportable —
  a genuinely novel thing to include in a Green-AI paper.

---

## 3. The structural issue: three evaluation modes

**This is the most important design point in this document.**

The datasets in the portfolio do not all evaluate the same thing. They fall into three modes,
and conflating them would waste months.

```
MODE R — RETRIEVAL EVALUATION            MODE Q — GROUNDED QA              MODE P — PATCH + TEST EXECUTION
Ground truth = relevant files/context    Ground truth = answer text        Ground truth = passing test suite
Metrics: Recall@K, MRR, NDCG, nDCG       Metrics: correctness, grounding,  Metrics: resolve rate (pass@1)
No generation needed → very cheap                 citation validity        Needs Docker + per-repo toolchain
                                                                            + agentic patch loop
        │                                        │                                    │
        ▼                                        ▼                                    ▼
RepoBench, CrossCodeEval,              CodeRepoQA, StackRepoQA,          SWE-bench, SWE-bench Pro,
CodeRepoQA(ret), StackRepoQA(ret)      EIH-SWE, EIH-Fresh                Multi-SWE-bench, SWE-rebench,
                                                                          Defects4J, BugsInPy, CodeFlaws
```

**What EIH currently does is Mode Q.** M1–M5 produce grounded, cited answers. They do not
generate patches and do not execute tests.

**Implication:** running the SWE-bench family "end to end" requires building a second system —
a Docker environment per repository (Multi-SWE-bench alone needs Java/Maven, Go, Rust/Cargo,
C/C++ and Node toolchains), an agentic patch-generation loop, and a test harness. That is
legitimate and it is in the target architecture (the Model/Agent Router), but it is months of
infrastructure work that is independent of the RAG contribution.

**Therefore the sequencing is by mode, not by tier** (§8). Modes R and Q validate the actual
research novelty — task-aware adaptive retrieval — and need no patch harness at all. Mode P
comes after, and its scope is honestly bounded by how much harness the team builds.

Nothing is cut. The order is chosen so that a dependency failure in Mode P cannot invalidate
the core RAG results.

---

## 4. Dataset registry

Instance counts: **raw** = as published; **slice** = what we execute.
Licence column must be completed before any dataset is downloaded (§4.1 is a blocking task).

### Tier 1 — EIH Engineering Corpus (ours, core)

| Field | Value |
|---|---|
| Role | The knowledge base everything retrieves from. Not a benchmark. |
| Content | Source code, tests, docs, ADRs, READMEs, Git history (commits/PRs/issues/reviews/releases), configs, incidents, logs, diagrams |
| Repositories | Currently `pallets/flask@3.0.3`, `fastapi/fastapi@0.111.0`. **Expand to ≥8 repos across ≥4 languages** to support RQ6. |
| Mode | n/a (corpus) |
| Status | **Not yet built — no repository has ever been ingested.** This is the single hardest blocker in the project. |

### Tier 2 — EIH-SWE Benchmark (ours, core contribution)

| Field | Value |
|---|---|
| Role | Task-aware benchmark spanning the full SDLC. The primary contribution. |
| Slice | 400–500 human-verified tasks |
| Mode | Q (+ R, since every task carries retrieval ground truth) |
| Schema | §5 |
| Status | To build. MEIB v1.0 (60 tasks) becomes its pilot/dev subset. |

### Tier 3 — EIH-Fresh (ours, critical)

| Field | Value |
|---|---|
| Role | Contamination-controlled final held-out test set. |
| Slice | ~150 tasks |
| Mode | Q + R |
| Protocol | §6 |
| Status | To build, **last** — must post-date the evaluated models' training cutoffs. |

### Tier 4 — Real-world SWE validation (external)

| Dataset | Raw | Slice | Mode | Role / RQ | Notes |
|---|---|---|---|---|---|
| **SWE-bench** | 2,294 | 300 (Lite) | P | Historical comparability | See §4.2 — do **not** use SWE-bench Verified as a headline result. |
| **SWE-bench Pro** | 1,865 total | **731** | P | RQ6, long-horizon | Only the public set (11 repos) is accessible. Held-out (858) and commercial (276) are not. Never report 1,865 as our N. |
| **SWE-rebench** | 21,000+ | ~500 fresh | P | **RQ7 contamination** | Tracks task creation date vs model release date — directly reusable for our own contamination protocol (§6). |

### Tier 5 — Multilingual + repository intelligence (external)

| Dataset | Raw | Slice | Mode | Role / RQ | Notes |
|---|---|---|---|---|---|
| **Multi-SWE-bench** | 1,632 | **300 (flash)** | P | RQ6 multilingual | 7 languages. Official `flash` (300) and `mini` (400) variants exist precisely for compute-limited evaluation — use them. |
| **SWE-bench Multilingual** | 300 | 300 | P | RQ6 | 9 languages. |
| **CodeRepoQA** | 585,687 | **1,000 stratified** | Q + R | RQ1, RQ5, multi-turn | Corpus-scale. Stratify by language × repo × turn-count. Also our only real **multi-turn** source. |
| **StackRepoQA** | 1,318 | **1,318 (full)** | Q + R | RQ2 graph | Small enough to run whole. See §4.3 — its findings matter to us. |
| **RepoBench** | ~10k | 1,000 | **R** | RQ2 cross-file | Separates retrieval / completion / combined — maps cleanly onto our ablation. |
| **CrossCodeEval** | ~10k | 1,000 | **R** | RQ2 cross-file | Deliberately requires cross-file context. Ideal for Dense vs BM25 vs Hybrid vs Graph. |

### Tier 6 — Specialised validation (external)

| Dataset | Raw | Slice | Mode | Role / RQ | Notes |
|---|---|---|---|---|---|
| **Defects4J** | 835 | 835 | P | RQ5 testing/maintenance | Java. Mature harness — easiest Mode-P entry point. |
| **BugsInPy** | 493 | 493 | P | RQ5 | Python. |
| **CodeFlaws** | 3,902 | 500 | P | RQ5 | C. |
| **Big-Vul** | ~188k | 500 stratified | **classification** | **RQ4 criticality** | Do not frame as patch generation. Frame as: does criticality-aware routing change behaviour on security tasks? |
| **PrimeVul** | ~226k | 500 stratified | **classification** | RQ4 criticality | Stronger data quality than Big-Vul; prefer it where they overlap. |

### Supporting corpora (not benchmarks)

| Dataset | Role |
|---|---|
| **CommitBench** | Reference for commit-message data quality/licensing practice. We build our **own** commit layer from Tier-1 repos — that is what feeds the knowledge graph. |
| **LogHub** | Log-analysis experimentation. Our incident corpus is constructed from Tier-1 repositories' real issues/postmortems. |
| **SWE-bench Multimodal** | Reserved for the diagram/OCR track once that ingestion path exists. |

### 4.1 BLOCKING: licence audit

Before **any** dataset is downloaded, every entry above needs: licence, redistribution
permission, attribution requirement, and whether derived task files may be published in our
artifact. Several of these datasets have restrictions that would prevent redistributing derived
data. A top-venue submission will be asked about this. **Owner: TBD. Due before Tier-4 work.**

### 4.2 Why SWE-bench Verified is not a headline result

In February 2026 OpenAI stopped treating SWE-bench Verified as a measure of frontier capability.
On auditing 138 hard tasks, **59.4% were found to have flaws in the test design itself**, and
there were signs that models had seen answers absent from the problem statements. Scores had
also saturated (74.9% → 80.9% over six months), making it impossible to distinguish model limits
from dataset defects. OpenAI points to SWE-bench Pro and continuously-refreshed benchmarks
instead.

**Our policy:** SWE-bench Lite may be reported for historical comparability only, always with
this caveat cited. Headline external validity comes from SWE-bench Pro, SWE-rebench and
Multi-SWE-bench.

### 4.3 Why StackRepoQA matters to us specifically

StackRepoQA reports that LLMs reach ~58% on repository-level QA, but attributes much of that to
**memorisation of Stack Overflow content rather than reasoning over source code** — and finds
that **graph-based retrieval produced the largest RAG gains**.

Two consequences:

1. It is independent published support for our RQ2 (graph augmentation helps structural
   reasoning). We should position relative to it, not pretend to have discovered it.
2. It is a contamination warning for any Stack Overflow-derived benchmark, including this one.
   Our EIH-Fresh protocol (§6) must not draw from Stack Overflow.

---

## 5. EIH-SWE task schema

Every task is a JSON object. Fields marked **R** carry retrieval ground truth — this is what
makes the benchmark score retrieval and generation independently, which answer-string matching
alone cannot do.

```jsonc
{
  "task_id": "EIH-ARCH-000123",
  "schema_version": "2.0",

  // --- Task framing ---
  "query": "How does dependency resolution handle sub-dependencies with caching?",
  "sdlc_stage": "architecture",          // §5.1
  "task_type": "dependency_analysis",    // §5.1
  "complexity": "high",                  // low | medium | high | very_high
  "criticality": "medium",               // low | medium | high | critical
  "security_sensitivity": "none",

  // --- Provenance (immutable, enables reproduction) ---
  "repository": "fastapi/fastapi",
  "language": "python",
  "base_commit": "0.111.0",
  "provenance": {
    "issue_url": null,
    "pr_url": null,
    "collected_at": "2026-08-26T00:00:00Z",
    "collector": "member_2"
  },

  // --- R: retrieval ground truth ---
  "relevant_files":   ["fastapi/dependencies/utils.py"],
  "relevant_symbols": ["solve_dependencies", "get_dependant"],
  "required_evidence": [
    { "file": "fastapi/dependencies/utils.py", "start_line": 512, "end_line": 587,
      "why": "Implements the sub-dependency resolution loop and the cache key." }
  ],
  "graph_paths": [
    "APIRoute -> get_dependant -> solve_dependencies -> SecurityRequirement"
  ],

  // --- Generation ground truth ---
  "ground_truth_answer": "...",
  "acceptable_alternatives": ["..."],
  "expected_citations": ["[fastapi/dependencies/utils.py:L512-L587]"],
  "gold_patch": null,                    // non-null only for Mode-P tasks

  // --- Evaluation control ---
  "evaluation_type": "retrieval+generation",   // retrieval | generation | retrieval+generation | patch
  "expected_quality_threshold": 0.80,

  // --- Integrity ---
  "task_fingerprint": "sha256:...",      // §6.2
  "status": "approved",
  "human_approved_by": "member_1",
  "annotation_minutes": 18
}
```

**Migration:** MEIB v1.0's 60 tasks lack `relevant_files`, `relevant_symbols`,
`required_evidence`, `graph_paths` and `task_fingerprint`. They must be back-filled before
MEIB is used for any retrieval claim, or explicitly restricted to generation-only evaluation.

### 5.1 Task taxonomy

Extends the current 21 types. Each leaf must have ≥8 tasks in EIH-SWE for per-stratum analysis
to be meaningful.

| SDLC stage | Task types |
|---|---|
| **Requirements** | requirement understanding · requirement traceability · ambiguity detection |
| **Architecture** | architecture explanation · dependency analysis · design decision retrieval · impact analysis · architecture comparison |
| **Development** | code explanation · code generation · code modification · API usage · cross-file implementation |
| **Testing** | test generation · failure diagnosis · coverage analysis · regression analysis |
| **Code Review** | defect detection · security review · maintainability · change impact |
| **Operations** | incident diagnosis · log analysis · root-cause analysis · remediation |
| **Maintenance** | bug fixing · dependency upgrade · refactoring · technical debt |

7 stages × ~4 types ≈ **28 leaves × 8 tasks minimum = 224 tasks floor**; the 400–500 target
gives ~15 per leaf, which is a defensible per-stratum N.

---

## 6. Contamination protocol

The mechanism SWE-rebench uses — tying task creation date to model release date — is the model
to follow.

### 6.1 EIH-Fresh construction

1. **Fix the cutoff.** Record the training cutoff of every evaluated local model. `T_cut` = the
   latest of these.
2. **Collect only after `T_cut`.** Source issues/PRs/commits merged strictly after `T_cut`,
   from repositories *not* in Tiers 1–5.
3. **Exclude Stack Overflow entirely** (§4.3).
4. **Record timestamps** for repository, issue, PR, base commit, resolution commit, collection
   date, and `T_cut` for each model.
5. **Freeze and fingerprint** before a single evaluation run (§6.2).
6. **Never tune on it.** Not once. Dev/val tuning happens on EIH-SWE only.

### 6.2 Task fingerprinting

Every task gets `sha256(query ‖ repository ‖ base_commit ‖ ground_truth_answer)`, stored in the
task and in a manifest. This lets us (a) detect accidental duplication across tiers, (b) prove
the test set was frozen before evaluation, (c) let others check for overlap with their data.

### 6.3 Contamination audit (reported in the paper)

- N-gram overlap between EIH-Fresh queries and every public tier.
- Per-model performance split by task-date vs model-cutoff.
- Explicit statement of which results may be contaminated and which cannot be.

---

## 7. Local model policy

### 7.1 Why local-only is a strength here

With an API model, inference energy happens on the provider's hardware and is fundamentally
**unmeasurable** within any honest system boundary — the best available is a token-count proxy.
Running locally makes every joule directly attributable and NVML-measurable. For a paper whose
central claim is about energy, this converts the weakest measurement in the design into the
strongest. State this explicitly as a methodological choice, not an apology.

### 7.2 The 6 GB VRAM constraint

RTX 4050 Laptop = 6 GB. That caps a single resident model at roughly 7B 4-bit (~4 GB), sharing
VRAM with BGE-small embeddings and the cross-encoder reranker. Workable, but tight.

**Proposed routing ladder** (one family keeps the comparison clean):

| Tier | Model | Purpose |
|---|---|---|
| Small | Qwen2.5-Coder-1.5B-Instruct | Cheap path for low-complexity/low-criticality tasks |
| Medium | Qwen2.5-Coder-3B-Instruct | Default |
| Large | Qwen2.5-Coder-7B-Instruct (4-bit) | Escalation / high-criticality |

This finally gives `routing/` — currently unwired dead code — something real to route between,
and makes RQ4 answerable.

### 7.3 Open problem: the "Large LLM baseline"

The metrics table calls for a large-LLM baseline (the "just send 20K tokens to a big model"
comparison that motivates the whole energy argument). That cannot run on 6 GB.

Options, to decide: (a) cite published figures and mark clearly as not-measured; (b) use a
one-off small paid API run purely for this baseline, disclosed as the only paid component;
(c) treat 7B-with-full-context as the long-context baseline and reframe the claim accordingly.
**Recommendation: (c), with (a) as supporting context.** Unresolved — see §9.

---

## 8. Sequencing (by evaluation mode, not by tier)

| Phase | Work | Unblocks |
|---|---|---|
| **0** | Ingest Tier-1 corpus. Stand up Qdrant + Neo4j. | Everything. Nothing else is meaningful until retrieval returns non-zero chunks. |
| **1** | Local model ladder (§7.2); wire `routing/`. | RQ4 |
| **2** | **Mode R** — RepoBench, CrossCodeEval. Retrieval metrics only, no generation. | RQ2. Cheap, fast, and directly tests the core novelty. |
| **3** | **Mode Q** — EIH-SWE annotation + CodeRepoQA + StackRepoQA. | RQ1, RQ2, RQ5 |
| **4** | Expand Tier-1 to ≥8 repos, ≥4 languages. | RQ6 |
| **5** | **Mode P** — patch harness. Defects4J first (most mature), then SWE-bench Pro public, then Multi-SWE-bench flash. | RQ6. Scope bounded by harness progress; failure here does not invalidate Phases 2–3. |
| **6** | Big-Vul / PrimeVul criticality slice. | RQ4 |
| **7** | EIH-Fresh construction and single frozen run. | RQ7 |
| **8** | Pareto + ablation across everything. | RQ8 |

**Phase 0 is the critical path and is not started.** Every result currently on disk came from a
mock LLM over an empty index.

---

## 9. RQ → dataset matrix

| RQ | Question | Primary | Secondary |
|---|---|---|---|
| RQ1 | Does task-aware routing beat fixed RAG on quality? | EIH-SWE | CodeRepoQA |
| RQ2 | Does graph augmentation help multi-file/structural reasoning? | CrossCodeEval, RepoBench | StackRepoQA, EIH-SWE |
| RQ3 | Does quality-aware escalation reduce unsupported answers? | EIH-SWE | EIH-Fresh |
| RQ4 | Can model routing cut energy/cost under a quality constraint? | EIH-SWE | Big-Vul, PrimeVul |
| RQ5 | Does benefit vary by SDLC stage / complexity / criticality? | EIH-SWE | Defects4J, BugsInPy |
| RQ6 | Does it generalise across repos and languages? | Multi-SWE-bench, SWE-bench Pro | SWE-bench Multilingual |
| RQ7 | Does it hold on fresh, contamination-resistant tasks? | **EIH-Fresh** | SWE-rebench |
| RQ8 | What is the quality–latency–energy–cost–carbon Pareto frontier? | All executed | — |

Every RQ has a primary dataset. Any dataset without an RQ should be challenged.

---

## 10. Verified sources

All figures in §4 were verified against these on 2026-08-26. Anything not listed here is marked
unverified in-place and must not be cited.

| Claim | Source |
|---|---|
| SWE-bench Verified retired; 59.4% of 138 hard tasks flawed; recommends SWE-bench Pro | [OpenAI — Why we no longer evaluate SWE-bench Verified](https://openai.com/index/why-we-no-longer-evaluate-swe-bench-verified/) |
| SWE-bench Pro: 1,865 tasks / 41 repos; public 731, held-out 858, commercial 276 | [arXiv:2509.16941](https://arxiv.org/abs/2509.16941) · [Scale Labs](https://labs.scale.com/papers/swe_bench_pro) |
| SWE-rebench: 21,000+ tasks; contamination tracking vs model release dates; NeurIPS 2025 | [arXiv:2505.20411](https://arxiv.org/abs/2505.20411) |
| Multi-SWE-bench: 1,632 instances from 2,456 candidates, 68 annotators, 7 languages; NeurIPS 2025 D&B; mini=400, flash=300 | [arXiv:2504.02605](https://arxiv.org/abs/2504.02605) · [NeurIPS proceedings](https://proceedings.neurips.cc/paper_files/paper/2025/hash/5afa9cb1e917b898ad418216dc726fbd-Abstract-Datasets_and_Benchmarks_Track.html) |
| CodeRepoQA: 585,687 entries, 5 languages, 30 repos, 6.62 avg turns; SIGIR 2025 | [arXiv:2412.14764](https://arxiv.org/abs/2412.14764) |
| StackRepoQA: 1,318 SO questions, 134 Java repos; ~58% accuracy largely memorisation; graph retrieval largest gains | [arXiv:2603.26567](https://arxiv.org/html/2603.26567v1) |

**Still to verify before use:** RepoBench, CrossCodeEval, Defects4J, BugsInPy, CodeFlaws,
Big-Vul, PrimeVul, CommitBench, LogHub, SWE-bench Multimodal exact sizes and licences.
Counts for these in §4 are marked `~` and are estimates, not citable figures.

---

## 11. Open decisions

| # | Decision | Owner | Blocks |
|---|---|---|---|
| 1 | Licence audit for all external datasets (§4.1) | Laptop B (`docs/LICENCE_AUDIT.md`, B2) | Tier-4 downloads |
| 2 | Large-LLM baseline strategy (§7.3) | Laptop A (D4) | RQ8 framing |
| 3 | Team task split | **Decided:** two laptops, see `docs/PROJECT_PLAN.md` §3–§4 | — |
| 4 | Which ≥8 repositories form the expanded Tier-1 corpus | Laptop B (B8, P2) | Phase 4 |
| 5 | `max_escalation_attempts` 2 → 3 (reranking rung currently unreachable). Decide after F1 fix | Laptop A (D5) | System E design, manifest hash |
| 6 | Mode-P harness scope: how many of the 6 patch datasets are realistic? (no third member) | A + B (D6) | Phase 5 |
| 7 | Annotation tooling — spreadsheet, custom UI, or LLM-assisted draft + human verify | Laptop B (B6) | Annotation throughput |

---

## 12. Change log

| Version | Date | Change |
|---|---|---|
| v0.2 | 2026-10-05 | §11 owners assigned to the two-laptop split (`docs/PROJECT_PLAN.md`). No dataset facts changed. |
| v0.1 | 2026-08-26 | Initial specification. Six-tier portfolio, three evaluation modes, feasibility envelope, contamination protocol, EIH-SWE schema v2.0. |
