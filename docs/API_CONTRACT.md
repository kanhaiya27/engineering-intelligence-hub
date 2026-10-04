# EIH API Contract: Pipeline Trace v1

| | |
|---|---|
| **Status** | **FROZEN** at `1.0.0` once this PR is merged with approval from both laptops |
| **Models** | `apps/api/contract/v1.py` (Pydantic v2) |
| **Export** | `docs/api/openapi-v1.json` (OpenAPI 3.1, generated, do not hand-edit) |
| **Example** | `docs/api/examples/trace-v1-system-e.json` (placeholder values, mock source) |
| **Tests** | `tests/test_api/test_contract_v1.py` |
| **Owners** | Laptop A produces traces (pipeline). Laptop B consumes them (web platform). |

This is the only interface between the research pipeline and the web platform.
The web platform never imports pipeline internals, and the pipeline never shapes
its output for the UI. Both sides talk only through these models.

---

## 1. Change process

1. Any change to `apps/api/contract/` **or to an enum it re-uses** (`TaskType`,
   `SDLCStage`, `ComplexityLevel`, `CriticalityLevel`, `SecuritySensitivity`,
   `SignalType`, `SignalStatus`, `RetrievalMode`, `RerankerType`) changes the
   export. `test_committed_openapi_export_matches_models` then fails until the
   export is regenerated:
   ```powershell
   python -m apps.api.contract.openapi          # rewrite docs/api/openapi-v1.json
   python -m apps.api.contract.openapi --check  # verify only
   python -m apps.api.contract.examples         # rewrite the example
   ```
2. The regenerated `openapi-v1.json` diff goes in a PR that **both** laptops review.
3. Versioning is semver on `contract_version`:
   - **Minor** (`1.x.0`): new *optional* fields, new endpoints, new SSE event
     types. Clients must ignore unknown fields and unknown SSE event types.
   - **Major** (`2.0.0`, new `/v2` path): anything else. That includes removing
     or renaming fields, making a field required, changing a type or meaning, or
     **adding a value to an existing enum** (strict clients would reject it).
   - Within one major version, the server never removes a field or changes its
     meaning.
4. Server-side models use `extra="forbid"`. The server cannot emit a field that
   is not in the contract, so it cannot leak internal metadata either.

## 2. Endpoints

| Method and path | Body | Success | Errors |
|---|---|---|---|
| `POST /v1/trace` | `TraceRequest` | `200` `PipelineTrace` (JSON) | `400 413 422 429 503` with `ErrorResponse` |
| `POST /v1/trace/stream` | `TraceRequest` | `200` `text/event-stream` of `TraceEvent` | same, before the stream starts |

**`TraceRequest`**: `query` (3–2000 chars), optional `repository` (`owner/name`),
`system` (`A`–`E`, default `E`), optional `task_type_hint`. Unknown fields are
rejected. Ablation knobs (`skip_verification`, `override_strategy`, threshold
overrides) are **not** public. The research harness calls the pipeline
directly, not through this API.

**Headers.** The client may send `X-Request-ID` (≤ 64 chars, `[A-Za-z0-9-]`).
The server echoes it, or generates a UUID4 if it is absent or invalid, in the
`X-Request-ID` response header and in `request_id`. A `429` carries
`Retry-After` (seconds), which matches `error.retry_after_s`.

**Errors.** `ErrorResponse = {contract_version, request_id, error: {code,
message, retry_after_s?}}`. `code` is one of `invalid_request`,
`payload_too_large`, `rate_limited`, `pipeline_unavailable`, `internal_error`.
`message` never contains stack traces, file paths, hostnames or configuration.
FastAPI's default `HTTPValidationError` is replaced by this shape for `422` too.

### 2.1 Streaming (SSE)

Each event is one SSE frame. The SSE `event:` line equals the JSON `event`
discriminator, and `data:` holds one JSON `TraceEvent`:

```
event: retrieval
data: {"contract_version":"1.0.0","trace_id":"…","seq":2,"event":"retrieval","payload":{…RetrievalTrace…}}
```

Every event carries `contract_version`, `trace_id` and `seq` (0, 1, 2, … without
gaps). The order for one trace:

```
trace.started
classification                       (systems C–E; omitted for A and B)
repeat for attempt n = 0..N:
    retrieval                        (omitted for system A)
    generation.delta*                (zero or more; only when the model streams)
    generation
    verification
    escalation                       (only between failed attempt n and n+1)
trace.completed                      (payload = the full PipelineTrace; always last on success)
error                                (terminal, replaces trace.completed on failure)
```

`trace.completed.payload` is exactly what `POST /v1/trace` would return. A
client that only needs the final result can wait for that one event.

## 3. Trace structure

```
PipelineTrace
├─ contract_version, trace_id, request_id, created_at, query, system (A–E)
├─ execution: ExecutionContext
│   ├─ producer: MachineInfo  (machine_id, gpu_name, torch_version, cuda_version,
│   │                          git_sha, carbon_region, carbon_intensity_gco2_per_kwh)
│   ├─ served_by_machine_id
│   ├─ generation_source: live_model | mock | cached_run
│   ├─ research_evidence: bool
│   └─ cached_from?: {run_id, recorded_at}
├─ classification?: ClassificationTrace (stage, task_type (+source), complexity,
│                   criticality, security_sensitivity, quality_threshold (+source),
│                   classifier_confidence, reasoning, latency_ms)
├─ attempts[]: AttemptTrace          (index 0..N, contiguous)
│   ├─ retrieval?: RetrievalTrace    (null only for system A)
│   │   ├─ requested_strategy, strategy_name (executed), strategy_fallback
│   │   ├─ mode, top_k, score_threshold, dense_weight, sparse_weight
│   │   ├─ dense / sparse: {requested, executed, candidates, skip_reason}
│   │   ├─ graph:    + {hop_depth, nodes_visited, chunks_injected}
│   │   ├─ reranker: + {reranker_type, returned, latency_ms, energy_joules}
│   │   ├─ chunks[]: RetrievedChunkTrace (rank, channel, citation, file:line, scores,
│   │   │            content [UNTRUSTED], content_truncated)
│   │   └─ latency_ms
│   ├─ generation: provider, model_id, is_local_model, finish_reason, answer,
│   │              input_tokens, output_tokens, latency_ms
│   ├─ verification: executed, gate, threshold, aggregated_score, passed,
│   │                critical_failures, evaluator_errors, signals[]
│   └─ resources: ResourceMetrics (per attempt)
├─ escalation: {max_escalations, exhausted, steps[]: EscalationStep}
├─ outcome: {verdict, answer, answer_attempt_index}
├─ totals: ResourceMetrics (whole trace)
└─ warnings[]
```

`ResourceMetrics` = `latency_ms, input_tokens, output_tokens, cost_usd,
energy_joules, energy_cpu_joules, energy_gpu_joules, energy_rerank_joules,
co2e_grams`. Each of these is a `Metric`.

### 3.1 Invariants the models enforce

| Rule | Where |
|---|---|
| Attempt indices are `0..N`. There are exactly `N` escalation steps, each going from `n` to `n+1`, and `N ≤ max_escalations` | `PipelineTrace` |
| The quality gate executes for system **E** and only E. Systems A–D make exactly one attempt | `PipelineTrace` |
| System A has no retrieval. Systems B–E have retrieval on every attempt | `PipelineTrace` |
| `VERIFIED` ⇒ the gate passed on the last attempt. `INSUFFICIENT_EVIDENCE` ⇒ the gate failed on the last attempt **and** escalation is exhausted. `UNVERIFIED` ⇒ no gate ran | `PipelineTrace` |
| A channel cannot be `executed` unless it was `requested` | `ChannelExecution` |
| `strategy_fallback == (requested_strategy != strategy_name)` | `RetrievalTrace` |
| Chunk ranks are `1..n`. `start_line ≤ end_line`, and both are set or both null | `RetrievalTrace`, `RetrievedChunkTrace` |
| `file_path` is repo-relative POSIX: no leading `/` or `~`, no drive letter, no `\`, no `..` | `RetrievedChunkTrace` |
| `citation == "<repository>:<file_path>:<start>-<end>"` (the line part is dropped when lines are unknown) | `RetrievedChunkTrace` |
| `generation_source = mock` ⇒ `research_evidence = false`. `cached_from` is present iff `cached_run` | `ExecutionContext` |
| A metric has a provenance tier iff it has a value | `Metric`, `SignalTrace` |

### 3.2 Verdicts

| Verdict | Meaning | `answer` |
|---|---|---|
| `VERIFIED` | System E, the gate passed | model answer from `answer_attempt_index` |
| `INSUFFICIENT_EVIDENCE` | System E, the gate failed on every allowed attempt | the refusal text; `answer_attempt_index = null` |
| `UNVERIFIED` | Systems A–D, no gate | model answer, which must be shown as **unverified** |
| `ERROR` | Pipeline failed after at least one attempt | best available; see `warnings` |

## 4. Execution context and evidence

`execution.producer` identifies the machine that **produced the numbers**
(CLAUDE.md rule 5). For a `cached_run` this is the machine that ran the original
experiment, which may differ from `served_by_machine_id`. Energy and latency are
only comparable between traces that share `producer.machine_id`.

`research_evidence` is `true` only for answers from a real model. It is always
`false` for `mock` (CLAUDE.md rule 2). Even when `true`, a public query is
**not** part of any benchmark. The web platform never writes live queries to
`benchmark/` or `experiments/`.

The web UI must show a visible "mock output, not a result" banner whenever
`generation_source = mock`.

## 5. Provenance

Tier definitions follow `docs/PROJECT_REPORT.md` §9.1:

- **MEASURED**: directly observed (timers, token counters, an NVML power reading).
- **ESTIMATED**: computed by a documented method with stated assumptions.
- **DERIVED**: computed from other values.

Rules:

1. **Unavailable means `null`.** `value = null` ⇒ `provenance = null`,
   `method = "not_available"`, and `note` says why. A missing number is never
   replaced by `0` or a default.
2. **Sums inherit the weakest tier** of their non-null parts (MEASURED >
   ESTIMATED). Example: `energy_joules` = CPU (ESTIMATED) + GPU (MEASURED) is
   ESTIMATED. A sum of only MEASURED latencies stays MEASURED.
3. **Combinations across units are DERIVED**: weighted quality scores, CO₂e per
   successful task, quality per joule.
4. **Zero by construction is DERIVED.** Energy of a step that did not execute is
   `0`, `DERIVED`, `method = "not_executed"`.
5. **Labels must reflect what actually happened.** If an instrument fails and a
   fallback is used, the tier and method are those of the fallback (see §8,
   finding F2).

`method` vocabulary (additions are minor changes):

| `method` | Tier | Used for |
|---|---|---|
| `perf_counter` | MEASURED | latencies (`time.perf_counter`) |
| `provider_usage` | MEASURED | token counts reported by the provider/tokenizer |
| `nvml_power_sample` | MEASURED | GPU energy from an NVML power reading over the call |
| `tdp_proxy` | ESTIMATED | CPU or GPU energy = TDP × utilisation × time |
| `pricing_table` | ESTIMATED | `cost_usd` from the per-model price table |
| `local_zero_marginal` | ESTIMATED | `cost_usd = 0` for local models (hardware cost excluded) |
| `grid_intensity` | ESTIMATED | CO₂e = energy × regional grid intensity |
| `sum` | weakest part | totals |
| `weighted_mean` | DERIVED | `aggregated_score` |
| `not_executed` | DERIVED | zero cost/energy of a step that did not run |
| `not_available` | – | value missing |

Individual quality-signal scores (`SignalTrace.score`) carry a `provenance`
field and no `method`. They are MEASURED, following the project convention in
`experiments/m5/metrics.py`.

## 6. Untrusted text (prompt-injection safety)

`RetrievedChunkTrace.content` (`content_trust = "untrusted"`),
`GenerationTrace.answer` and `Outcome.answer` are **untrusted text**. Retrieved
repository content may contain instructions aimed at an LLM or a browser.

- **Clients** render them as plain text. They never use `innerHTML`, never
  auto-link, never render Markdown with raw HTML, and never execute or `eval`.
  Code is displayed in `<pre>` with escaping only.
- **The server** caps `content` at 4,000 chars (`content_truncated = true` when
  cut) and never interprets retrieved text as instructions. In the prompt it is
  delimited as evidence, not instructions.
- Citations are built from structured fields (`repository`, `file_path`,
  lines), never parsed out of model output.

## 7. Mapping from the current pipeline (for Laptop A)

How each contract field is filled from today's code. **Bold** marks gaps the
adapter cannot close without a pipeline change.

| Contract field | Source today |
|---|---|
| `classification.*` | `TaskClassification` from `RuleBasedTaskClassifier`; `latency_ms` timed by the adapter |
| `retrieval.requested_strategy` | strategy passed to `AdaptiveRetrievalPipeline.retrieve` |
| `retrieval.strategy_name` | `RetrievalResult.metadata["resolved_strategy"]` (what executed) |
| `retrieval.sparse.executed`, `candidates` | `metadata["sparse_retrieved"]` (hybrid) |
| `retrieval.graph.executed` etc. | `metadata["graph_augmented"]`, `graph_nodes_visited`, `graph_chunks_injected`, `graph_hop_depth` |
| `retrieval.reranker.*` | `metadata["reranking_applied"]`, `reranker_type`, `reranker_candidates_in`, `reranker_returned`, `reranker_latency_ms`, `reranker_energy_joules` |
| chunk `file_path`, lines, symbol, commit | chunk payload `metadata.file_path`, `start_line`, `end_line`, `symbol_name`, `commit_sha` (repo-relative in the wave-1 Qdrant collection, checked on 3 sampled points) |
| chunk `dense_score`, `sparse_score`, `pre_rerank_*` | chunk `metadata` written by `retrieval/hybrid.py`, `retrieval/reranker.py` |
| `generation.*` | `GenerationResponse` (`text`, `input_tokens`, `output_tokens`, `latency_ms`, `finish_reason`) |
| `verification.*` | `QualityReport` (`signals`, `aggregated_score`, `threshold_applied`, `passed`, `critical_failures`, `evaluator_errors`) |
| `resources.*` | `EnergyEstimate` (`method`, `cpu/gpu_energy_joules`), `CostEstimate`, `CarbonEstimate` (`region`, `carbon_intensity_gco2_per_kwh`) |
| `escalation.steps[].changes` | diff of consecutive `RetrievalStrategyConfig`s |
| `producer.machine_id` | `EIH_MACHINE_ID` (not yet in `core/config.py`) |
| **per-attempt `retrieval` / `generation`** | **`QualityAwareRAGPipeline.execute` keeps only the last `RetrievalResult` and a summarised `attempt_history`. Earlier attempts' chunks and generation objects are discarded. The adapter needs per-attempt objects (a callback or a returned list).** |
| **system A** | **No LLM-only path in `QualityAwareRAGPipeline`.** |
| **system E as a mode** | **`ExperimentMode` has no `SYSTEM_E`.** `/adaptive/strategies` advertises `system_e`, and `/adaptive/query` silently maps unknown modes to `system_d`. |

## 8. Findings from the review (for Laptop A)

Found while mapping the pipeline to this contract. These are in Laptop A's
directories; nothing there was changed.

| # | Finding | How established | Effect |
|---|---|---|---|
| **F1** | **Escalation never strengthens retrieval.** `EscalationPolicy.escalate()` returns configs named `hybrid_esc1`, `hybrid_esc1_esc2_graph`, `…_esc_max`. `quality_rag` passes only the *name* as `override_strategy_name`. `AdaptiveRetrievalPolicy._get_strategy()` cannot find it and falls back to `hybrid` with a log warning. Every escalated attempt re-runs top_k 7, no graph, no rerank, while `attempt_history.strategy_used` records the escalated name. | **Verified by execution** on laptop-b (registry from `configs/retrieval.yaml`, 10 strategies). For attempts 1, 2 and 3 the requested configs were top_k 10/16/30 with graph off/on/on and rerank off/off/on. The executed strategy was `hybrid` (top_k 7, no graph, no rerank) every time. | System E's escalation ladder is inert. Any E-vs-D comparison would measure repeated identical retrieval. This is the same defect class as PROJECT_REPORT §10.5. The contract's `strategy_fallback` exposes it in every trace. |
| F2 | `EnergyEstimator._measure_gpu_energy_nvml()` catches every exception and returns TDP-proxy values, but `estimate()` still sets `method = NVML_MEASUREMENT`. A failed NVML read would be reported as MEASURED. | Code inspection (`sustainability/energy/estimator.py`); not executed | Mislabelled provenance on local-model runs |
| F3 | The NVML path multiplies one instantaneous power reading, taken after the call, by the duration. It does not integrate over the call. | Code inspection | Whether this counts as MEASURED or ESTIMATED is a methodology decision. §5 keeps it as `nvml_power_sample` (MEASURED) pending A's decision |
| F4 | `quality_rag` calls `energy_estimator.estimate(..., is_local_model=False)` unconditionally. | Code inspection | Local Ollama models would get no GPU energy at all |
| F5 | CPU utilisation uses `psutil.cpu_percent(interval=None)`. Per psutil docs, the first call in a process returns a meaningless `0.0`, and later calls cover the interval since the previous call, not the generation call. | Code inspection + psutil documentation | CPU energy for the first request is 0, and later values are not tied to the call |

## 9. Example

`docs/api/examples/trace-v1-system-e.json` is a full, valid System-E trace with
one escalation. **All its values are hand-written placeholders**: it is marked
`generation_source = "mock"`, `research_evidence = false`, and its `warnings`
say so. It shows the shape only and must never be quoted as a result.
