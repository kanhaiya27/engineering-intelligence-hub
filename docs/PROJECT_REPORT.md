# Engineering Intelligence Hub (EIH)

## Task-Aware, Quality-Constrained Retrieval-Augmented Generation for Software Engineering: Optimising Quality, Cost, Latency, Energy and Carbon Footprint

**Project type:** B.Tech Computer Science (AI/ML) Major Project
**Team:** 3 active members (2 core system + evaluation, 1 agentic orchestration)
**Duration:** 6 months
**Status of this document:** Interim project report — architecture and methodology complete, system validated end-to-end, empirical evaluation pending
**Date:** 26 August 2026

> **NOTE FOR REPORT/LaTeX GENERATION:** Sections 1–9 and 11–13 are complete and
> presentation-ready. Section 10 reports ONLY measurements that have actually been
> taken; no experimental comparison between systems has been run yet and none is
> claimed. Where a number is not yet measured, this document says so explicitly
> rather than estimating. Preserve that distinction in any derived document.

---

## 1. Abstract

Modern software engineering assistants answer developer questions by submitting
large volumes of source code and documentation to large language models on every
query. This is computationally expensive, slow, and carbon-intensive, and the cost
is incurred uniformly regardless of whether the question is trivial or complex.
Retrieval-Augmented Generation (RAG) is widely assumed to reduce this cost by
retrieving only relevant context, but this assumption is not automatically true:
the combined cost of embedding, sparse and dense retrieval, reranking, graph
traversal and possible re-generation can exceed the cost of a single large-context
call.

This project develops the **Engineering Intelligence Hub (EIH)**, a task-aware
engineering RAG system that classifies each incoming task by software development
lifecycle (SDLC) stage, type, complexity and criticality, and allocates retrieval
and generation resources proportionate to that classification. Crucially, answer
quality is treated as a **hard constraint rather than an optimisation objective**:
the system is architecturally prohibited from returning a lower-quality answer in
order to save resources. A verification gate scores every generated answer, a
bounded escalation policy retries with progressively stronger retrieval when the
quality threshold is not met, and the system issues an explicit refusal when
sufficient evidence cannot be found.

The system is instrumented end-to-end for latency, token usage, monetary cost,
directly measured GPU energy, and grid-intensity-aware CO₂e. All inference is
executed on local hardware, which makes energy attributable and measurable rather
than proxied. The evaluation programme compares five progressively-enabled system
configurations across a purpose-built, provenance-preserving software engineering
benchmark and a suite of external validation datasets, and reports a
quality–energy–cost–latency Pareto frontier together with a contamination-controlled
held-out evaluation.

---

## 2. Problem Statement and Motivation

### 2.1 The problem

Developers spend a substantial fraction of their time locating and understanding
existing engineering knowledge — source code, documentation, architectural
decisions, past incidents and change history — rather than writing new code. LLM
assistants address this, but the prevailing usage pattern submits very large
contexts per query.

Three concrete consequences follow:

1. **Uniform cost for non-uniform tasks.** "Which configuration key enables debug
   mode?" and "What is the blast radius of changing this authentication module?"
   consume comparable resources under a fixed-context approach, despite differing
   in difficulty by orders of magnitude.
2. **Unverified output.** Answers are returned whether or not the retrieved
   evidence actually supports them, making hallucination difficult to detect.
3. **Unmeasured environmental cost.** Energy and carbon are rarely reported at all,
   and when reported are usually estimated from token counts rather than measured.

### 2.2 Why RAG is not automatically the answer

A naive framing — "RAG retrieves less, therefore RAG is greener" — is not
defensible. A RAG pipeline introduces its own costs: query embedding, dense vector
search, sparse (BM25) search, score fusion, cross-encoder reranking, optional graph
traversal, and — where a verification gate is present — potential regeneration.
Each is a real computational expense.

The correct research framing is therefore conditional, not absolute:

> **Under what conditions does task-aware RAG become more energy-efficient than
> fixed-context LLM querying, and which retrieval and model configurations lie on
> the quality–energy Pareto frontier for software engineering tasks?**

### 2.3 Supporting evidence from the literature

Two findings motivate this framing directly:

- Pan et al. report that RAG configurations achieving accuracy within ≤3% of one
  another can differ by up to **20.2× in energy consumption**, and that pairing a
  smaller model with a stronger retriever can match a much larger model's accuracy
  at over 5× lower energy. This establishes that large efficiency headroom exists
  and is not visible from accuracy alone [1].
- A controlled ICSE experiment on RAG energy-reduction techniques found that some
  techniques (retrieval-threshold tuning, embedding-size reduction) achieved up to
  **60% energy reduction with no accuracy loss**, while others (certain vector
  indexing strategies) caused accuracy to fall by up to **30%** [2].

The second result is the central motivation for this project's design stance: energy
optimisation applied without a quality constraint *silently degrades correctness*.

---

## 3. Research Questions

| ID | Research question |
|---|---|
| **RQ1** | Does task-aware retrieval routing improve engineering answer quality relative to fixed RAG at comparable or lower resource cost? |
| **RQ2** | Does knowledge-graph augmentation improve multi-file and structural reasoning over purely lexical and semantic retrieval? |
| **RQ3** | Does quality-aware verification with bounded escalation reduce unsupported and hallucinated engineering answers? |
| **RQ4** | Can task-aware model routing reduce energy and cost while preserving a per-task quality constraint? |
| **RQ5** | Does the benefit vary systematically by SDLC stage, task complexity and task criticality? |
| **RQ6** | Does the system generalise across repositories and programming languages? |
| **RQ7** | Do the results hold on fresh, contamination-controlled engineering tasks? |
| **RQ8** | What is the quality–latency–energy–cost–carbon Pareto frontier for software engineering RAG? |

---

## 4. Literature Review and Research Gap

### 4.1 Retrieval-augmented generation for software engineering

RAG has become the dominant architecture for grounding LLM output in an external
corpus. Applied to software engineering, it must handle artefacts that are
structurally unlike prose: source code with symbol boundaries and cross-file
dependencies, configuration, test suites, and version-control history. Repository-level
question answering has emerged as a distinct research problem, with CodeRepoQA
providing 585,687 multi-turn QA entries across five programming languages and 30
repositories [3], and StackRepoQA providing 1,318 real developer questions mapped to
134 open-source Java repositories [4].

StackRepoQA reports a finding of direct relevance to this project: LLMs achieve
approximately 58% accuracy on repository-level QA, but much of that success is
attributable to **memorisation of previously-seen content rather than reasoning over
source code**, and among retrieval strategies, **graph-based retrieval produced the
largest gains** [4]. This is independent published support for RQ2, and a
contamination warning that directly shapes this project's evaluation protocol.

### 4.2 Benchmark validity and contamination

Static software-engineering benchmarks degrade as models are trained on them. In
February 2026, OpenAI announced it would no longer treat SWE-bench Verified as a
measure of frontier capability: on auditing 138 hard tasks, **59.4% were found to
contain flaws in the test design itself**, with evidence that models had seen
answers not present in the problem statements, and scores had saturated such that
model limits could not be distinguished from dataset defects [5].

Two responses to this problem inform our methodology. SWE-bench Pro targets
long-horizon, enterprise-scale tasks across 41 repositories (1,865 tasks, of which
731 are publicly accessible) and mitigates contamination partly through private
repositories [6]. SWE-rebench instead automates continuous collection of fresh tasks
and explicitly tracks task creation date relative to model release date, producing a
contamination-resistant evaluation pipeline over 21,000+ tasks [7]. Multi-SWE-bench
extends issue-resolution evaluation to seven programming languages with 1,632
expert-annotated instances [8].

### 4.3 Green AI and energy-aware software engineering

Sustainability concerns in software engineering now span the full lifecycle [9],
and have been synthesised across a large body of secondary studies [10]. Within AI
specifically, measurement methodology — which tools, which system boundary, which
carbon intensity — has become the central rigour question [11]. Work on efficient
and green LLMs for software engineering argues that the field must weigh compute,
time, memory, energy and carbon alongside accuracy rather than optimising accuracy
alone [12].

Most directly related to this project, a controlled ICSE experiment evaluated five
practical RAG energy-reduction techniques on a production system, reporting up to
60% energy reduction for some techniques and up to 30% accuracy degradation for
others [2].

### 4.4 Research gap

Existing work addresses these areas **separately**:

- RAG and repository-level QA research optimises retrieval quality, largely without
  measuring energy.
- Green AI research measures energy, largely on general-purpose workloads rather
  than software engineering tasks.
- Benchmark-validity research addresses contamination, largely for patch-generation
  rather than grounded question answering.
- Energy-reduction studies tune **global** configuration knobs and accept accuracy
  loss as a reported trade-off.

**The gap this project addresses is their intersection:** a *task-aware* system that
varies its resource allocation *per task* according to classified engineering
context, under a *hard quality constraint* that architecturally forbids the accuracy
degradation observed in prior energy-reduction work, evaluated on *software
engineering tasks across the full SDLC* with *directly measured* rather than proxied
energy, and validated against *contamination-controlled* data.

### 4.5 Positioning against the closest prior work

The nearest published work [2] is distinguished from this project on three axes:

| Dimension | Prior work [2] | This project |
|---|---|---|
| Adaptation granularity | Global configuration knobs, tuned once | Per-task, driven by classified SDLC stage, complexity, criticality |
| Treatment of quality | Reported as a trade-off; up to 30% accuracy loss accepted as a finding | Hard constraint; verification gate, bounded escalation, explicit refusal |
| Domain and scope | General-purpose RAG, general QA dataset | Software engineering across the full SDLC, with structural knowledge graph |
| Energy attribution | Component-level measurement | Full-pipeline local inference, NVML-measured, region-aware CO₂e |

---

## 5. Novelty and Contributions

This project claims four contributions, stated conservatively.

**C1. A task-aware, quality-constrained RAG architecture for software engineering.**
Retrieval strategy, context depth, graph augmentation, reranking and model tier are
selected per task from an automatically inferred engineering classification (SDLC
stage, task type, complexity, criticality, security sensitivity), subject to a
per-task quality threshold that the system may not violate.

**C2. Quality as a hard constraint, implemented rather than asserted.** A
multi-signal verification gate scores citation grounding, query relevance, evidence
coverage and evidence consistency. Failure triggers bounded escalation along a
defined ladder (wider retrieval → graph augmentation → cross-encoder reranking).
Exhausted escalation produces an explicit `INSUFFICIENT EVIDENCE` refusal rather
than an unsupported answer. Refusals are scored as refusals, not as successes.

**C3. A provenance-preserving, contamination-aware evaluation methodology.** Each
benchmark task carries retrieval ground truth (relevant files, symbols, evidence
line spans, expected graph paths) in addition to an answer, enabling retrieval and
generation to be scored **independently** — which answer-string matching alone cannot
do. A held-out set (`EIH-Fresh`) is collected strictly after evaluated models'
training cutoffs, SHA-256 fingerprinted, and frozen before any evaluation run.

**C4. Quality-constrained efficiency metrics for engineering work.** Rather than
energy per query, the primary sustainability metric is **CO₂e per *successful*
engineering task**. A system that consumes more energy per query but succeeds far
more often may be more carbon-efficient per unit of delivered engineering value;
energy-per-query alone cannot express this and can reward systems that fail cheaply.

### 5.1 Explicit non-claims

To keep claims defensible, the project does **not** assert:

- that RAG reduces CO₂e in general (the claim is conditional and configuration-dependent);
- that its heuristic policies are optimal or Pareto-efficient (they are initial
  configurations, to be validated empirically);
- any energy or carbon figure not obtained from measurement or a documented,
  disclosed estimation method;
- that the proposed metrics are established standards (they are labelled as proposed).

---

## 6. System Architecture

### 6.1 Overview

```
                          ENGINEERING DATA
      source code · documentation · configuration · Git history
              issues · pull requests · incidents · tests
                                 |
                        INGESTION PIPELINE
        AST-aware chunking (symbol boundaries) · header-aware
        Markdown/RST · configuration parsing · metadata extraction
                                 |
                 +---------------+---------------+
                 |               |               |
            VECTOR INDEX     BM25 INDEX     KNOWLEDGE GRAPH
            BGE-small-en     code-aware      entities + edges
            384-dim, GPU     tokenisation    (Neo4j)
                 |               |               |
                 +---------------+---------------+
                                 |
                        TASK INTELLIGENCE
        SDLC stage · task type · complexity · criticality ·
        security sensitivity -> per-task quality threshold
                                 |
                       ADAPTIVE RETRIEVAL
        policy-selected strategy · dense / sparse / hybrid /
        graph-augmented · criticality-driven escalation
                                 |
                     CROSS-ENCODER RERANKING
             ms-marco-MiniLM-L-6-v2, GPU, energy-measured
                                 |
                      MODEL / AGENT ROUTING
                  small · medium · large · agentic
                                 |
                    GROUNDED GENERATION
          answer + inline citations [file.py:L512-L587]
                                 |
                     QUALITY VERIFICATION GATE
      citation grounding · query relevance · evidence coverage ·
                     evidence consistency
                                 |
                  +--------------+--------------+
                  |                             |
                PASS                    FAIL -> ESCALATE
                  |                    (bounded; ladder below)
                  |                             |
                  |                    exhausted -> REFUSE
                  +--------------+--------------+
                                 |
                        FINAL ANSWER + TELEMETRY
         latency · tokens · energy (NVML) · cost · CO2e
                                 |
                    MULTI-OBJECTIVE ANALYSIS
              Pareto frontier · stepwise ablation deltas
```

### 6.2 Component detail

**Ingestion.** Python source is chunked on AST symbol boundaries (functions,
classes, methods) so that a semantic unit is never split mid-definition;
oversized classes are decomposed by method. Markdown and reStructuredText are
chunked header-aware. Configuration formats (YAML, JSON, TOML) and Git history are
ingested with provenance metadata (repository, commit SHA, file path, line range).

**Three complementary indexes.** Different engineering questions require different
lookup mechanisms:

| Index | Mechanism | Suited to |
|---|---|---|
| Vector | BGE-small-en-v1.5, 384-dim, CUDA | Conceptual queries ("how does context propagation work?") |
| BM25 | BM25Plus with code-aware tokenisation splitting camelCase, snake_case, dotted and path notation | Exact identifier lookup (`solve_dependencies`, error codes) |
| Graph | Neo4j; entities and edges extracted from AST and history | Structural reasoning (dependencies, change impact, test coverage) |

**Task intelligence.** A transparent rule-based classifier maps a query to SDLC
stage and one of 21 task types, then heuristic analysers estimate complexity and
criticality and derive the per-task quality threshold. Transparency is deliberate:
a rule-based classifier is auditable and its decisions are explainable, which
matters for a system whose central claim concerns *why* resources were allocated.

**Adaptive retrieval.** A policy maps task type to a named retrieval strategy
(`dense_fast`, `hybrid`, `hybrid_bm25`, `graph_augmented`, `incident_sparse`, and
reranked variants). High and critical criticality override to stronger strategies.
This is the primary energy lever: inexpensive questions receive inexpensive
retrieval.

**Cross-encoder reranking.** A bi-encoder scores query and document independently
and never sees them together; a cross-encoder scores the *pair* in a single forward
pass, modelling term interaction directly. It recovers precision lost to score
fusion, at the cost of one forward pass per candidate — a cost this project
measures rather than ignores.

**Verification and bounded escalation.** Four deterministic evaluators produce
weighted quality signals. On failure the escalation ladder proceeds: (1) widen
`top_k` and lower the score threshold; (2) activate graph neighbourhood context;
(3) maximal capability with cross-encoder reranking over a widened candidate pool.
Escalation is strictly bounded; exhaustion yields refusal.

**Sustainability instrumentation.** Every call records latency, input/output
tokens, energy, cost and CO₂e. GPU energy is measured directly through NVML during
local inference. CO₂e is computed as `Energy(kWh) × CarbonIntensity(gCO₂e/kWh)`
with the region and intensity value recorded per run, since grid intensity varies
by more than an order of magnitude between regions (France ≈ 56, UK ≈ 233,
India ≈ 713 gCO₂e/kWh).

### 6.3 Why local inference is a methodological strength

All generation runs on local hardware. With a hosted API, inference energy is
consumed on the provider's hardware and is fundamentally unmeasurable within any
honest system boundary — the best available substitute is a token-count proxy.
Executing locally makes every joule directly attributable and measurable via NVML.
For a project whose central claim concerns energy, this converts the weakest
measurement in the design into its strongest.

---

## 7. Experimental Design

### 7.1 Five-system ablation ladder

Each system adds exactly one capability, so every observed difference is
attributable to a single component.

| System | Configuration | Isolates |
|---|---|---|
| **A** | LLM only, no retrieval | Baseline |
| **B** | + fixed hybrid RAG (dense + BM25, fixed top-k) | Contribution of retrieval |
| **C** | + task classification and adaptive retrieval | Contribution of task-awareness |
| **D** | + knowledge-graph augmentation | Contribution of structural context |
| **E** | + quality gate and bounded escalation | Contribution of verification |

Stepwise ablation deltas Δ(A→B), Δ(B→C), Δ(C→D), Δ(D→E) attribute quality and
resource change to each component.

### 7.2 Controlled variables

All parameters not under investigation are frozen and bound to a SHA-256-hashed
experiment manifest: repository commit pins, embedding model and device,
temperature, maximum output tokens, random seed, carbon intensity, hardware TDP
figures, pricing constants, and trials per task.

### 7.3 Dataset partitioning

Deterministic stratified splits (seed 42), balanced across SDLC stage and
repository. The held-out test partition is not inspected, tuned on, or executed
until all development and validation work is complete and the manifest is re-frozen.

### 7.4 Three evaluation modes

External datasets do not all evaluate the same capability. Conflating them would
invalidate comparisons, so each is assigned an explicit mode:

| Mode | Ground truth | Metrics | Requires |
|---|---|---|---|
| **R — Retrieval** | Relevant files / context spans | Recall@K, Precision@K, MRR, NDCG | No generation — inexpensive |
| **Q — Grounded QA** | Answer text + expected citations | Correctness, faithfulness, citation validity | One generation per system per trial |
| **P — Patch + test** | Passing test suite | Resolve rate (pass@1) | Docker per repository, per-language toolchains, agentic patch loop |

The core contribution of this project is evaluated in Modes R and Q. Mode P is
pursued for external validity and is architecturally independent of the RAG core,
so a delay there cannot invalidate the primary results.

---

## 8. Dataset Strategy

A six-tier portfolio. Instance counts given are the *evaluation slice* actually
executed, which for corpus-scale datasets is a stratified sample — those datasets
are corpora rather than evaluation sets, and their own source papers evaluate on
samples.

| Tier | Asset | Role |
|---|---|---|
| **1** | **EIH Engineering Corpus** (ours) | The knowledge base retrieved from. Code, docs, configuration, Git history, tests. |
| **2** | **EIH-SWE Benchmark** (ours) | Task-aware benchmark spanning the full SDLC with retrieval ground truth. Primary contribution. |
| **3** | **EIH-Fresh** (ours) | Contamination-controlled held-out final test set. |
| **4** | SWE-bench Pro, SWE-rebench | Real-world external validation; contamination resistance |
| **5** | Multi-SWE-bench, CodeRepoQA, StackRepoQA, RepoBench, CrossCodeEval | Multilingual and repository-intelligence validation |
| **6** | Defects4J, BugsInPy, Big-Vul, PrimeVul | Controlled defect and security/criticality validation |

### 8.1 Corpus selection principle

Repository selection is **determined by benchmark coverage, not preference**. Each
external benchmark poses questions about specific repositories; if a repository is
absent from the corpus, retrieval has nothing relevant to return, all
retrieval-enabled systems degrade to the no-retrieval baseline, and the comparison
becomes meaningless. The corpus is therefore the union of repositories the chosen
benchmarks touch, plus those used for our own benchmark.

The registry currently defines **28 repositories across 8 languages** in four
ingestion waves, each entry recording licence, pinned tag, resolved commit SHA,
benchmark alignment, SDLC coverage and a written selection rationale.

### 8.2 EIH-SWE task schema

Each task records, in addition to query and ground-truth answer:
`relevant_files`, `relevant_symbols`, `required_evidence` (file + line span +
justification), `graph_paths`, `expected_citations`, per-task quality threshold,
full provenance (repository, base commit, issue/PR, collection timestamp,
annotator), and a SHA-256 task fingerprint.

### 8.3 Contamination protocol

1. Record the training cutoff of every evaluated model; `T_cut` = the latest.
2. Collect EIH-Fresh tasks strictly after `T_cut`, from repositories outside Tiers 1–5.
3. Exclude Stack Overflow entirely, given the documented memorisation effect [4].
4. Record all relevant timestamps per task.
5. Fingerprint and freeze before any evaluation run.
6. Never tune on the held-out set.

The contamination audit reported in the final paper includes n-gram overlap between
EIH-Fresh and all public tiers, per-model performance split by task date versus
model cutoff, and an explicit statement of which results may be contaminated.

---

## 9. Evaluation Metrics

### 9.1 Measurement tiers

Every reported quantity is labelled by how it was obtained:

- **[MEASURED]** — directly observed (latency, tokens, NVML GPU energy, retrieval counts)
- **[ESTIMATED]** — computed from a documented method with stated assumptions (CPU energy, CO₂e, monetary cost)
- **[DERIVED]** — computed from the above (quality per joule, CO₂e per successful task)

### 9.2 Metric families

**Quality (decomposed, not a single accuracy figure):** answer correctness against
ground truth; faithfulness/groundedness; context relevance; citation accuracy;
completeness.

**Retrieval:** Recall@K, Precision@K, MRR, NDCG@K.

**Performance:** total latency decomposed as
`T_total = T_query + T_retrieval + T_rerank + T_context + T_generation`, enabling
statements such as "reranking improves quality by X% at a cost of Y ms".

**Sustainability:** energy per query (J); tokens per query; CO₂e per query; and the
primary metric, **CO₂e per successful engineering task**.

**Quality-constrained efficiency (proposed):** quality per joule, quality per
second, quality per unit cost — each conditional on the quality constraint being met.

### 9.3 Why CO₂e per successful task is the headline metric

Energy per query is manipulable by answering badly. Consider two systems:

| | Energy/query | Success rate | CO₂e per successful task |
|---|---|---|---|
| System X | Low | Low | High |
| System Y | Moderate | High | **Low** |

System X appears more efficient on a per-query basis while delivering less useful
engineering work per unit of carbon. Normalising by *successful* task measures
delivered engineering value rather than raw model throughput, and it is the correct
rebuttal to the objection "your system saved energy by giving worse answers".

---

## 10. Implementation Status and Preliminary System Validation

> **This section reports only measurements actually taken. No comparison between
> Systems A–E has been executed. No quality, energy or carbon comparison between
> systems is claimed at this stage.**

### 10.1 Implemented and verified

| Subsystem | Status |
|---|---|
| Data schemas, configuration, structured logging | Complete |
| Ingestion (Python AST, Markdown/RST, configuration, Git history) | Complete |
| Vector store (Qdrant) with filtering and batch upsert | Complete |
| Embeddings (BGE-small-en-v1.5, CUDA) | Complete |
| BM25 with code-aware tokenisation | Complete |
| Hybrid retrieval with weighted score fusion | Complete |
| Cross-encoder reranking with energy measurement | Complete |
| Knowledge graph (Neo4j + in-memory), AST extraction, builder | Complete |
| Task intelligence (classifier, complexity, criticality) | Complete |
| Adaptive retrieval policy and pipeline | Complete |
| Quality gate (4 evaluators), bounded escalation, refusal | Complete |
| Sustainability instrumentation (NVML energy, cost, region-aware CO₂e) | Complete |
| Controlled evaluation framework (manifest, splits, metrics, failure taxonomy, Pareto engine) | Complete |
| REST API (FastAPI) | Complete |
| Automated test suite | **178 tests passing, 0 skipped** |

### 10.2 Corpus ingestion (measured)

Six SWE-bench-aligned Python repositories ingested at pinned tags, with commit SHAs
resolved from the actual clone rather than assumed:

| Repository | Chunks indexed | Primary SDLC role |
|---|---|---|
| fastapi/fastapi | 18,899 | Architecture, dependency analysis |
| pylint-dev/pylint | 10,819 | Code review, defect detection |
| sphinx-doc/sphinx | 8,974 | Requirements, documentation |
| pytest-dev/pytest | 6,889 | Testing |
| psf/requests | 976 | Small-corpus control |
| pallets/flask | ~1,500 | Pilot benchmark origin |
| **Total** | **48,046** | |

Content mix is approximately 53% source code and 47% documentation and
configuration — appropriate for an SDLC-wide system, since requirements and
architecture questions are answered from documentation rather than code.

### 10.3 Retrieval validation (measured)

For the query *"How does the Flask application context differ from the request
context?"*, all three retrieval modes return relevant evidence from the ingested
corpus:

| Mode | Top-ranked results | Warm latency |
|---|---|---|
| Dense | `docs/reqcontext.rst`, `tests/test_appctx.py`, `src/flask/ctx.py` | — |
| Sparse (BM25) | `docs/appcontext.rst` (1.000), `docs/quickstart.rst`, `docs/reqcontext.rst` | — |
| Hybrid | Fused ranking of both | **223 ms** |

The BM25 index holds all 48,046 chunks. Index construction takes approximately
7.5 s at this corpus size and is performed once per process.

### 10.4 Cross-encoder reranking (measured)

Using `cross-encoder/ms-marco-MiniLM-L-6-v2` on an NVIDIA RTX 4050 Laptop GPU:

| Quantity | Value |
|---|---|
| Warm reranking latency | 6–10 ms |
| Warm reranking energy (NVML-measured) | 0.07–0.13 J |
| Model cold-start (excluded from per-query cost) | ~12.6 s, reported separately |

Functional validation: on a query about Flask's debug configuration key, score
fusion ranked an irrelevant installation instruction first; the cross-encoder
promoted the correct chunk from rank 2 to rank 0 and demoted the irrelevant one out
of the returned set — the precision recovery reranking is intended to provide.

### 10.5 Defects identified and corrected during validation

Systematic validation of the implemented pipeline identified four defects, each of
which would have produced plausible but invalid experimental results. They are
documented here because the detection methodology is itself relevant to
reproducibility.

| # | Defect | Consequence if uncorrected |
|---|---|---|
| 1 | Reranking was declared in configuration but never implemented; no consumer read `enable_reranking` | The final escalation rung and all high-criticality strategies would have performed no reranking while reporting that they did |
| 2 | Reranking energy was excluded from pipeline energy totals | The cross-encoder would have appeared free, biasing the Pareto frontier toward reranked configurations |
| 3 | Sustainability configuration was never passed to the estimators | Grid carbon intensity and hardware TDP settings were inert; CO₂e was computed against the wrong region regardless of configuration |
| 4 | BM25 index was never populated in the production pipeline | All "hybrid" retrieval would have been dense-only; sparse-dominant strategies would have returned nothing |

A fifth issue — a first energy measurement that attributed 31 s of one-time model
loading to a single query (762 J instead of ~0.09 J, an error of roughly four orders
of magnitude) — was identified and corrected by separating cold-start from
per-query cost.

**Identified 2026-10-04, not yet corrected (open).** A further defect of the same class:
escalated retrieval strategies (`<name>_esc1`, `_esc2_graph`, `_esc_max`) are passed to
the policy by name only, are not in the strategy registry, and silently fall back to
`hybrid` (top_k 7, no graph, no reranking). The escalation ladder therefore never
strengthens retrieval, while attempt telemetry records the escalated name. Verified by
execution on laptop-b; details in `docs/API_CONTRACT.md` §8 (F1). No System E result
may be reported until it is fixed.

**Methodological observation.** Every one of these defects was silent: the system
produced output, tests passed, and results appeared reasonable. This supports a
general argument for the evaluation discipline adopted here — that a declared
capability must be verified as *executing*, not merely as *configured*, before any
measurement derived from it is reported.

### 10.6 Not yet implemented

Architecture diagram ingestion (OCR/vision); incident report loaders; AST-aware
chunking for non-Python languages (currently sliding-window fallback); model routing
(module implemented but not yet wired into the pipeline); multi-turn conversation;
dashboard; Mode P patch-generation harness.

---

## 11. Phased Work Plan

> **Superseded for scheduling by `docs/PROJECT_PLAN.md` (2026-10-05)**, which maps these
> phases onto the two development laptops and the 25 Oct / 15 Nov deadlines. The
> phase content below is unchanged.

Sequential phases with explicit ownership. Parallelism is limited to genuinely
independent tracks, since concurrent work on coupled subsystems has repeatedly
produced the silent-defect class documented in §10.5.

**Team:** Member A (core system + evaluation), Member B (data, corpus, studies),
Member C (agentic orchestration, NVIDIA platform).

| Phase | Weeks | Work | Owner | Unblocks |
|---|---|---|---|---|
| **0** | ✅ done | Foundation, corpus ingestion, retrieval verified end-to-end | A + B | Everything |
| **1** | 1–2 | Local inference stack: Ollama + Qwen2.5-Coder 1.5B/3B/7B; wire model routing | A | RQ4 |
| **2** | 1–3 | Tree-sitter AST chunking for Java, Go, Rust, TS/JS, C/C++ | B | RQ6 |
| **3** | 3–4 | Corpus waves 2–4; knowledge-graph population across all repositories | B | RQ2, RQ6 |
| **4** | 2–12 | **EIH-SWE annotation**, ~300–450 tasks, continuous background task | A + B | RQ1, RQ3, RQ5 |
| **5** | 5–6 | **Mode R**: RepoBench, CrossCodeEval — retrieval metrics, no generation | A | RQ2 |
| **6** | 7–9 | **Mode Q**: EIH-SWE, CodeRepoQA, StackRepoQA — Systems A–E full run | A | RQ1, RQ3, RQ5 |
| **7** | 6–12 | **Mode P**: patch harness — Defects4J, then SWE-bench Pro, Multi-SWE-bench | C | RQ6 |
| **8** | 10–11 | Systems studies: scalability (10K→500K chunks), resilience/fallback, latency decomposition | B | RQ8 |
| **9** | 12–13 | EIH-Fresh construction, fingerprinting, freeze | B | RQ7 |
| **10** | 14–15 | Final held-out evaluation (N=5 trials), Pareto frontier, ablation deltas | A | RQ8 |
| **11** | 15–16 | Optional human study (8–12 participants) if ethics approval obtained | B | Developer-effort dimensions |
| **12** | 8–18 | Paper drafting, continuous from first real results | All | — |

**Total: approximately 18 weeks**, which fits the period from late August to end of
December if the three tracks proceed as scheduled.

### 11.1 Critical path and principal risks

| Risk | Assessment | Mitigation |
|---|---|---|
| **Mode P scope** (Phase 7) | Highest risk. Six patch datasets across seven language toolchains, each requiring Docker environments and a test harness | Assigned to Member C, whose agentic work shares the same problem shape. Ordered Defects4J first (most mature harness). Architecturally independent of Modes R/Q, so slippage does not invalidate the core results |
| **Annotation throughput** (Phase 4) | 300–450 tasks at 15–20 min each is 50–80 hours per core member | Started in week 2, spread across 10 weeks, sized conservatively with room to grow |
| **Human study lead time** (Phase 11) | Ethics approval may take weeks | Confirm institutional requirement immediately; abandon early rather than late if infeasible |
| **Non-Python chunking** (Phase 2) | Blocks RQ6; sliding-window fallback confounds language effects with chunker artefacts | Scheduled early and in parallel; RQ6 claims withheld until complete |

---

## 12. Threats to Validity

**Construct validity.** CPU energy and monetary cost are estimated rather than
measured, with the estimation method disclosed. The evidence-consistency evaluator
currently detects a single narrow contradiction pattern and is therefore a weak
discriminator; it is not described as hallucination detection. Genuine contradiction
detection requires a natural-language-inference entailment model and is scoped as
future work.

**Internal validity.** Retrieval policies and quality-signal weights are heuristic
initial configurations, not tuned optima, and are labelled as such. Until tree-sitter
chunking is complete, non-Python results confound language difficulty with chunking
quality, so cross-language claims are withheld.

**External validity.** The corpus consists of open-source repositories used as a
proxy for proprietary engineering knowledge bases. Results may not transfer to
closed-source settings with different documentation conventions. A single GPU
configuration is used; absolute energy figures are hardware-specific, though
relative comparisons between systems on identical hardware remain valid.

**Contamination.** Public benchmark data may appear in model training corpora. This
is the specific motivation for EIH-Fresh and the contamination audit, and results on
public tiers are reported separately from results on the fresh set.

**Scale.** The pilot benchmark of 60 tasks is a controlled engineering benchmark, not
a large statistical corpus. Statistical claims are made only where the sample size
supports them, and the expanded EIH-SWE benchmark is sized to give a defensible
per-stratum count.

---

## 13. Future Work

**Immediate (within project scope).** Tree-sitter multi-language chunking; model
routing activation; knowledge-graph population across the full corpus; Mode P patch
harness; EIH-Fresh construction; scalability and resilience studies.

**Extensions identified but not scheduled.** Architecture diagram ingestion via
OCR and vision models; incident-report loaders for operational intelligence;
multi-turn conversational workflows; NLI-based contradiction detection to
strengthen the consistency signal; a change-risk scorer combining dependency-graph
centrality, historical incident frequency and test coverage; technical-debt
prioritisation rather than detection; and a real-time monitoring dashboard.

**Longer-term research directions.** Reinforcement-learning-based model routing
trained on the collected quality–energy telemetry; online calibration of quality
thresholds from observed outcomes; carbon-aware scheduling that defers
non-interactive engineering tasks to periods of lower grid carbon intensity; and
agentic orchestration for multi-step engineering workflows.

**Dimensions requiring resources not currently available.** Developer effort,
onboarding time, rework and information-retrieval burden require a human-participant
study. Mean time to recovery, availability, incident frequency, return on investment
and compliance require longitudinal production deployment. These are implemented as
system capabilities where applicable but are **not** claimed as empirically validated.

---

## 14. References

Verified against the cited source on 26 August 2026 unless marked otherwise.

[1] M. Z. Pan et al., "Towards Automatically Optimizing Retrieval Augmented AI Systems." OpenReview. — Reports up to 20.2× energy variation among RAG configurations within ≤3% accuracy, and >5× energy reduction by pairing a smaller model with a stronger retriever.

[2] "On the Effectiveness of Proposed Techniques to Reduce Energy Consumption in RAG Systems: A Controlled Experiment," *Proceedings of the IEEE/ACM 48th International Conference on Software Engineering (ICSE)*, 2026. arXiv:2601.02522. DOI: 10.1145/3786581.3786932.

[3] "CodeRepoQA: A Large-scale Benchmark for Software Engineering Question Answering," arXiv:2412.14764. Published as "Understanding Large Language Model Performance in Software Engineering: A Large-scale Question Answering Benchmark," *Proceedings of the 48th ACM SIGIR Conference*, 2025. DOI: 10.1145/3726302.3730262. — 585,687 multi-turn entries, five languages, 30 repositories.

[4] "Beyond Code Snippets: Benchmarking LLMs on Repository-Level Question Answering" (StackRepoQA), arXiv:2603.26567. — 1,318 developer questions, 134 Java repositories; reports memorisation effects and largest RAG gains from graph-based retrieval.

[5] OpenAI, "Why we no longer evaluate SWE-bench Verified," February 2026. — 59.4% of 138 audited hard tasks found flawed; recommends SWE-bench Pro and continuously-refreshed benchmarks.

[6] "SWE-Bench Pro: Can AI Agents Solve Long-Horizon Software Engineering Tasks?" arXiv:2509.16941. — 1,865 tasks across 41 repositories (public set 731, held-out 858, commercial 276).

[7] "SWE-rebench: An Automated Pipeline for Task Collection and Decontaminated Evaluation of Software Engineering Agents," *NeurIPS* 2025. arXiv:2505.20411. — 21,000+ tasks; contamination tracking against model release dates.

[8] D. Zan et al., "Multi-SWE-bench: A Multilingual Benchmark for Issue Resolving," *NeurIPS 2025 Datasets and Benchmarks Track*. arXiv:2504.02605. — 1,632 instances from 2,456 candidates, 68 expert annotators, seven languages.

[9] "A Survey of Energy Concerns for Software Engineering," *Journal of Systems and Software*, 2024. *(supplied by project team — verify bibliographic details before submission)*

[10] "Sustainability in the Field of Software Engineering: A Tertiary Study," *ACM Transactions on Software Engineering and Methodology*, 2026. *(supplied by project team — verify before submission)*

[11] "Green Artificial Intelligence: A Comprehensive Review of Metrics, Tools, Challenges, Trends, and Future Prospects," *Archives of Computational Methods in Engineering*, 2026. *(supplied by project team — verify before submission)*

[12] "Efficient and Green Large Language Models for Software Engineering: Literature Review, Vision, and the Road Ahead." *(supplied by project team — verify before submission)*

[13] "AutoRAG: Automated Framework for optimization of Retrieval Augmented Generation Pipeline," arXiv:2410.20878.

[14] "The ML.ENERGY Benchmark: Toward Automated Inference Energy Measurement and Optimization," arXiv:2505.06371.

**Reference coverage against requirement:** conference papers — [2] ICSE 2026, [3] SIGIR 2025, [7] NeurIPS 2025, [8] NeurIPS 2025, [1] OpenReview, [13] AutoRAG (six). Journal — [9] and [11]. Survey/tertiary study — [10], with [12] as a vision/review paper.

**Verification status.** References [1]–[8], [13] and [14] were verified against their
published source during preparation of this document. References [9]–[12] were
supplied by the project team and must be independently verified before final
submission, in line with the project's requirement that every citation be real and
traceable.
