"""
Contract v1 trace adapter: run one query through System A-E exactly as the research
harness configures it (experiments/m5/runner.py `_dispatch`), and map what actually ran
onto `PipelineTrace` (docs/API_CONTRACT.md).

* Systems are built by `M5BenchmarkRunner` itself, so the demo cannot drift from the
  research configuration. Nothing is written to benchmark/ or experiments/ (the runner's
  output directories point at a temp dir).
* Per-attempt objects come from `QualityAwareRAGPipeline.execute(on_attempt=...)`.
* Every number carries its tier (§5): latency/tokens MEASURED; GPU generation energy
  MEASURED when the provider's NVML counter produced it, otherwise the provider's tier;
  rerank energy ESTIMATED (one power sample); CPU energy is a trial-level estimate in the
  harness and is reported as not available per attempt; CO2e and cost ESTIMATED.
"""

from __future__ import annotations

import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from apps.api.contract.v1 import (
    CHUNK_CONTENT_MAX_CHARS,
    AttemptTrace,
    ChannelExecution,
    ClassificationTrace,
    EscalationStep,
    EscalationSummary,
    ExecutionContext,
    GenerationSource,
    GenerationTrace,
    GraphExecution,
    MachineInfo,
    Metric,
    Outcome,
    ParameterChange,
    PipelineTrace,
    Provenance,
    RerankerExecution,
    ResourceMetrics,
    RetrievalTrace,
    RetrievedChunkTrace,
    SignalTrace,
    SystemId,
    Verdict,
    VerificationTrace,
)
from core.config import settings

M, E, D = Provenance.MEASURED, Provenance.ESTIMATED, Provenance.DERIVED
_SYSTEM_IDS = {"A": "baseline_a", "B": "baseline_b", "C": "system_c", "D": "system_d", "E": "system_e"}
_runner = None


def _metric(value, unit, tier, method, note=None) -> Metric:
    if value is None:
        return Metric(value=None, unit=unit, provenance=None, method="not_available", note=note)
    return Metric(value=round(float(value), 6) if isinstance(value, float) else value, unit=unit,
                  provenance=tier, method=method, note=note)


def _weakest(*tiers: Optional[Provenance]) -> Optional[Provenance]:
    present = [t for t in tiers if t is not None]
    if not present:
        return None
    return E if E in present else (D if D in present and M not in present else M)


def _resources(latency_ms, tin, tout, gen_j, gen_tier, rerank_j, rerank_method, co2e, cost) -> ResourceMetrics:
    gpu = _metric(gen_j, "joules", M if gen_tier == "MEASURED" else E,
                  "nvml_energy_counter" if gen_tier == "MEASURED" else "tdp_proxy") if gen_j is not None else \
        _metric(None, "joules", None, None, "provider reported no generation energy")
    rr = (_metric(rerank_j, "joules", E, rerank_method or "nvml_power_sample") if rerank_j else
          _metric(0.0, "joules", D, "not_executed"))
    parts = [x for x in (gpu, rr) if x.value is not None]
    total_tier = _weakest(*(p.provenance for p in parts))
    total = _metric(sum(p.value for p in parts) if parts else None, "joules", total_tier, "sum",
                    "GPU generation + rerank; CPU energy is estimated per trial by the research harness only")
    return ResourceMetrics(
        latency_ms=_metric(latency_ms, "ms", M, "perf_counter"),
        input_tokens=_metric(tin, "tokens", M, "provider_usage"),
        output_tokens=_metric(tout, "tokens", M, "provider_usage"),
        cost_usd=_metric(cost if cost is not None else 0.0, "usd", E, "local_zero_marginal"),
        energy_joules=total,
        energy_cpu_joules=_metric(None, "joules", None, None, "estimated per trial in the research harness"),
        energy_gpu_joules=gpu, energy_rerank_joules=rr,
        co2e_grams=_metric(co2e, "gco2e", E, "grid_intensity") if co2e is not None and total.value is not None
        else _metric(None, "gco2e", None, None, "no energy value"),
    )


def _sum_resources(items: List[ResourceMetrics]) -> ResourceMetrics:
    def add(field: str) -> Metric:
        ms = [getattr(r, field) for r in items]
        vals = [m for m in ms if m.value is not None]
        if not vals:
            return Metric(value=None, unit=ms[0].unit, provenance=None, method="not_available",
                          note=ms[0].note)
        return Metric(value=round(sum(m.value for m in vals), 6), unit=ms[0].unit,
                      provenance=_weakest(*(m.provenance for m in vals)), method="sum")
    return ResourceMetrics(**{f: add(f) for f in ResourceMetrics.model_fields})


def _chunks(result) -> List[RetrievedChunkTrace]:
    out = []
    for i, ch in enumerate(result.chunks if result else [], 1):
        md = ch.metadata or {}
        repo = ch.repository or md.get("repository")
        path = md.get("file_path") or ch.source_path
        if path and (path.startswith(("/", "~")) or "\\" in path or ".." in path.split("/") or path[1:2] == ":"):
            path = None  # never leak a local path (contract §3.1)
        start, end = md.get("start_line"), md.get("end_line")
        if not (isinstance(start, int) and isinstance(end, int) and 1 <= start <= end):
            start = end = None
        citation = f"{repo}:{path}" + (f":{start}-{end}" if start else "") if repo and path else (ch.chunk_id or f"chunk-{i}")
        graph_hop = md.get("graph_hop")
        channel = "graph" if graph_hop is not None else (
            "hybrid" if md.get("fused_score") is not None else "sparse" if md.get("sparse_score") is not None
            and md.get("dense_score") is None else "dense")
        kind = "rerank" if md.get("rerank_score") is not None else "graph" if channel == "graph" else \
            "fused" if channel == "hybrid" else channel
        sha = md.get("commit_sha")
        content = ch.content or ""
        out.append(RetrievedChunkTrace(
            rank=i, chunk_id=str(ch.chunk_id)[:300], channel=channel,
            repository=repo if repo and "/" in repo else None, file_path=path if repo else path,
            start_line=start, end_line=end, symbol_name=(md.get("symbol_name") or None),
            commit_sha=sha if isinstance(sha, str) and 7 <= len(sha) <= 40 else None, citation=citation[:800],
            score=float(ch.score), score_kind=kind, dense_score=md.get("dense_score"),
            sparse_score=md.get("sparse_score"), pre_rerank_score=md.get("pre_rerank_score"),
            pre_rerank_rank=md.get("pre_rerank_rank"), graph_hop=graph_hop,
            content=content[:CHUNK_CONTENT_MAX_CHARS], content_truncated=len(content) > CHUNK_CONTENT_MAX_CHARS))
    return out


def _retrieval(idx: int, requested, result, retrieval_ms: float) -> RetrievalTrace:
    md = result.metadata or {}
    # The pipeline records the configuration that actually ran (a dict); the contract's
    # parameters describe what EXECUTED, so they come from it, the request only as fallback.
    ran = md.get("executed_strategy")
    ran = ran if isinstance(ran, dict) else {"strategy_name": ran or md.get("resolved_strategy") or result.strategy_used}

    def p(name, default=None):
        v = ran.get(name)
        return v if v is not None else getattr(requested, name, default)

    executed = str(ran.get("strategy_name") or result.strategy_used)
    mode = p("mode")
    mode_s = str(getattr(mode, "value", mode))
    req_name = getattr(requested, "strategy_name", None) or executed
    wants_sparse, wants_dense = mode_s in ("sparse", "hybrid"), mode_s in ("dense", "hybrid")
    graph_req = bool(p("include_graph_context", False)) or bool(md.get("graph_augmented"))
    rerank_req = bool(p("enable_reranking", False))
    rr_j = md.get("reranker_energy_joules")
    return RetrievalTrace(
        attempt_index=idx, requested_strategy=req_name, strategy_name=executed,
        strategy_fallback=req_name != executed, mode=mode, top_k=p("top_k", 0),
        score_threshold=p("score_threshold", 0.0),
        dense_weight=p("dense_weight"), sparse_weight=p("sparse_weight"),
        dense=ChannelExecution(requested=wants_dense, executed=wants_dense and md.get("dense_retrieved") is not None,
                               candidates=md.get("dense_retrieved")),
        sparse=ChannelExecution(requested=wants_sparse, executed=wants_sparse and md.get("sparse_retrieved") is not None,
                                candidates=md.get("sparse_retrieved")),
        graph=GraphExecution(requested=graph_req, executed=graph_req and bool(md.get("graph_augmented")),
                             hop_depth=md.get("graph_hop_depth"), nodes_visited=md.get("graph_nodes_visited"),
                             chunks_injected=md.get("graph_chunks_injected")),
        reranker=RerankerExecution(
            requested=rerank_req, executed=rerank_req and bool(md.get("reranking_applied")),
            candidates=md.get("reranker_candidates_in"), reranker_type=md.get("reranker_type") or p("reranker_type", "none"),
            returned=md.get("reranker_returned"),
            latency_ms=_metric(md.get("reranker_latency_ms"), "ms", M, "perf_counter") if md.get("reranking_applied") else _metric(0.0, "ms", D, "not_executed"),
            energy_joules=_metric(rr_j, "joules", E, md.get("reranker_energy_method") or "nvml_power_sample") if rr_j else _metric(0.0, "joules", D, "not_executed")),
        chunks=_chunks(result), latency_ms=_metric(retrieval_ms, "ms", M, "perf_counter"))


def _verification(idx: int, report, threshold, gate_ran: bool) -> VerificationTrace:
    if not gate_ran or report is None:
        return VerificationTrace(attempt_index=idx, executed=False, aggregated_score=_metric(None, "score", None, None, "no gate for this system"), passed=None)
    sigs = [SignalTrace(signal_type=s.signal_type, evaluator_name=getattr(s, "evaluator_name", None), status=s.status,
                        score=s.score, weight=s.weight, provenance=M if s.score is not None else None,
                        rationale=(s.rationale or "")[:1000] or None) for s in report.signals]
    return VerificationTrace(attempt_index=idx, executed=True, gate="quality_gate_v1", threshold=threshold,
                             aggregated_score=_metric(report.aggregated_score, "score", D, "weighted_mean"),
                             passed=bool(report.passed), critical_failures=list(report.critical_failures or []),
                             evaluator_errors=list(getattr(report, "evaluator_errors", []) or []), signals=sigs)


def _rung(name: str) -> str:
    return "max_capability" if "esc_max" in name else "graph_augmentation" if "graph" in name else "expanded_retrieval"


def _changes(a, b) -> List[ParameterChange]:
    out = []
    for f in ("top_k", "score_threshold", "include_graph_context", "graph_hop_depth", "enable_reranking", "mode"):
        va, vb = getattr(a, f, None), getattr(b, f, None)
        va, vb = getattr(va, "value", va), getattr(vb, "value", vb)
        if va != vb:
            out.append(ParameterChange(name=f, before=va, after=vb))
    return out


def runner():
    global _runner
    if _runner is None:
        from experiments.m5.runner import M5BenchmarkRunner
        tmp = Path(tempfile.mkdtemp(prefix="eih-trace-"))
        _runner = M5BenchmarkRunner(raw_output_dir=tmp / "raw", processed_output_dir=tmp / "processed")
    return _runner


def _producer() -> MachineInfo:
    from experiments.provenance import collect_provenance
    p = collect_provenance(include_ollama=False)
    gpu, torch_info, git = p.get("gpu") or {}, p.get("torch") or {}, p.get("git") or {}
    from sustainability.carbon.estimator import CarbonEstimator
    est = CarbonEstimator.from_settings()
    return MachineInfo(machine_id=settings.machine_id, gpu_name=gpu.get("name"), torch_version=torch_info.get("torch"),
                       cuda_version=torch_info.get("cuda"), git_sha=(git.get("sha") or "unknown")[:40],
                       carbon_region=str(est.region)[:40], carbon_intensity_gco2_per_kwh=est.carbon_intensity)


def execution_context() -> ExecutionContext:
    llm = runner().llm_provider
    return ExecutionContext(producer=_producer(), served_by_machine_id=settings.machine_id,
                            generation_source=GenerationSource.MOCK if llm.provider_name == "mock" else GenerationSource.LIVE_MODEL,
                            research_evidence=llm.provider_name == "ollama")


def run_trace(query: str, system: str, request_id: str, repository: Optional[str] = None,
              task_type_hint: Optional[str] = None, emit=None, trace_id: Optional[str] = None) -> PipelineTrace:
    """Execute and return the full trace; `emit(kind, payload_model)` receives events as they happen."""
    from experiments.m5.runner import baseline_b_strategy
    from knowledge.schemas.tasks import EngTaskRequest
    from retrieval.adaptive import ExperimentMode

    emit = emit or (lambda kind, payload: None)
    r = runner()
    llm = r.llm_provider
    trace_id = trace_id or uuid.uuid4().hex
    req = EngTaskRequest(task_id=f"web-{trace_id[:12]}", query=query, repository=repository,
                         task_type_hint=task_type_hint)
    warnings: List[str] = []
    clf, cls_trace = None, None
    if system in ("C", "D", "E"):
        t0 = time.perf_counter()
        clf = r._classifier.classify(req)
        ms = (time.perf_counter() - t0) * 1000
        hinted = task_type_hint is not None and getattr(clf, "task_type", None) == task_type_hint
        cls_trace = ClassificationTrace(
            classifier=r._classifier.classifier_name, sdlc_stage=clf.sdlc_stage, task_type=clf.task_type,
            task_type_source="client_hint" if hinted else "classifier", complexity=clf.complexity,
            criticality=clf.criticality, security_sensitivity=clf.security_sensitivity,
            quality_threshold=clf.quality_threshold, quality_threshold_source="classifier",
            classifier_confidence=float(getattr(clf, "confidence", None) or getattr(clf, "classifier_confidence", 0.0) or 0.0),
            reasoning=(getattr(clf, "reasoning", None) or None), latency_ms=_metric(ms, "ms", M, "perf_counter"))
        emit("classification", cls_trace)

    attempts: List[AttemptTrace] = []
    observed: List[Dict[str, Any]] = []
    gate = system == "E"

    steps: List[EscalationStep] = []

    def on_attempt(o: Dict[str, Any]) -> None:
        if observed:  # escalation from the previous attempt happens before this one (§2.1 order)
            a = observed[-1]
            rep = a["report"]
            steps.append(EscalationStep(
                from_attempt=a["attempt_index"], to_attempt=o["attempt_index"], rung=_rung(o["strategy"].strategy_name),
                from_strategy=a["strategy"].strategy_name, to_strategy=o["strategy"].strategy_name,
                trigger_score=rep.aggregated_score if rep else None, threshold=a["threshold"],
                critical_failures=list(rep.critical_failures or []) if rep else [],
                changes=_changes(a["strategy"], o["strategy"])))
            emit("escalation", steps[-1])
        observed.append(o)
        idx = o["attempt_index"]
        ret = _retrieval(idx, o["strategy"], o["retrieval"], o["retrieval_ms"]) if o["retrieval"] is not None else None
        if ret:
            emit("retrieval", ret)
        g = o["generation"]
        gen = GenerationTrace(attempt_index=idx, provider=llm.provider_name, model_id=g.model_id or o["model_id"],
                              is_local_model=llm.provider_name == "ollama", finish_reason=g.finish_reason if g.finish_reason in ("stop", "length", "content_filter", "error") else None,
                              answer=g.text or "", input_tokens=_metric(g.input_tokens, "tokens", M, "provider_usage"),
                              output_tokens=_metric(g.output_tokens, "tokens", M, "provider_usage"),
                              latency_ms=_metric(g.latency_ms, "ms", M, "perf_counter"))
        emit("generation", gen)
        ver = _verification(idx, o["report"], o["threshold"], gate)
        emit("verification", ver)
        res = _resources(o["attempt_latency_ms"], g.input_tokens, g.output_tokens, o["generation_energy_joules"],
                         o["energy_tier"], o["rerank_energy_joules"], (o["retrieval"].metadata or {}).get("reranker_energy_method") if o["retrieval"] else None,
                         o["co2e_grams"], o["cost_usd"])
        attempts.append(AttemptTrace(attempt_index=idx, retrieval=ret, generation=gen, verification=ver, resources=res))

    if system in ("A", "B"):
        pipe = r._get_pipeline_a(llm) if system == "A" else r._get_pipeline_b(llm)
        strategy = None if system == "A" else baseline_b_strategy()
        t0 = time.perf_counter()
        resp = pipe.execute(request=req, strategy=strategy, classification=None, skip_retrieval=system == "A")
        md = resp.metadata or {}
        lb = md.get("latency_breakdown_ms") or {}

        class _G:  # the baseline response carries the generation fields directly
            text, model_id, input_tokens, output_tokens = resp.answer, resp.model_id, resp.input_tokens, resp.output_tokens
            finish_reason = (md.get("finish_reasons") or [None])[0]
            latency_ms = lb.get("generation")
        on_attempt({"attempt_index": 0, "strategy": strategy, "retrieval": resp.retrieval if system == "B" else None,
                    "generation": _G, "report": None, "threshold": None, "model_id": resp.model_id,
                    "retrieval_ms": (lb.get("retrieval") or 0.0) + (lb.get("rerank") or 0.0),
                    "attempt_latency_ms": resp.latency_ms or (time.perf_counter() - t0) * 1000,
                    "energy_tier": md.get("generation_energy_tier"),
                    "generation_energy_joules": (resp.energy_joules or 0.0) - (md.get("rerank_energy_joules") or 0.0) if resp.energy_joules is not None else None,
                    "rerank_energy_joules": md.get("rerank_energy_joules") or 0.0, "co2e_grams": resp.co2e_grams,
                    "cost_usd": resp.cost_usd})
        final_answer = resp.answer
    else:
        mode = ExperimentMode.SYSTEM_C if system == "C" else ExperimentMode.SYSTEM_D
        pipe = r._get_pipeline_quality(llm)
        resp = pipe.execute(request=req, classification=clf, experiment_mode=mode, skip_verification=not gate,
                            on_attempt=on_attempt)
        final_answer = resp.answer

    max_esc = r.manifest.systems[_SYSTEM_IDS[system]].max_escalations if gate else 0
    last = attempts[-1].verification
    if not gate:
        outcome = Outcome(verdict=Verdict.UNVERIFIED, answer=final_answer, answer_attempt_index=len(attempts) - 1)
    elif last.passed:
        outcome = Outcome(verdict=Verdict.VERIFIED, answer=final_answer, answer_attempt_index=len(attempts) - 1)
    else:
        outcome = Outcome(verdict=Verdict.INSUFFICIENT_EVIDENCE, answer=final_answer, answer_attempt_index=None)
    if llm.provider_name != "ollama":
        warnings.append(f"provider '{llm.provider_name}' is not the local research provider")
    return PipelineTrace(
        trace_id=trace_id, request_id=request_id, created_at=datetime.now(timezone.utc), query=query,
        system=SystemId(system),
        execution=execution_context(),
        classification=cls_trace, attempts=attempts,
        escalation=EscalationSummary(max_escalations=max_esc, steps=steps,
                                     exhausted=gate and not last.passed and len(steps) >= max_esc),
        outcome=outcome, totals=_sum_resources([a.resources for a in attempts]), warnings=warnings)
