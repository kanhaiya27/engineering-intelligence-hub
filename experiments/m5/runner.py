"""
Engineering Intelligence Hub — Controlled Benchmark Runner (Phase-2 M5)
========================================================================
Executes the five experimental systems against versioned benchmark splits
with repeated trial support (N=3) and raw JSONL telemetry logging.

Systems Under Evaluation:
  1. BASELINE A : LLM Only (no retrieval, no graph, no gate)
  2. BASELINE B : Fixed Hybrid RAG (dense + BM25, no graph, no gate)
  3. SYSTEM C   : Task-Aware Adaptive RAG (M1 + M3, no graph, no gate)
  4. SYSTEM D   : Task-Aware + Knowledge Graph RAG (M1 + M2 + M3, no gate)
  5. SYSTEM E   : Full Proposed System (M1 + M2 + M3 + M4 Quality Gate & Escalation)
"""

from __future__ import annotations

import datetime
import time
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import psutil

from core.config import settings
from core.logging import get_logger
from benchmark.dataset import BenchmarkDataset
from evaluation.scorers.correctness import CorrectnessEvaluator
from experiments.m5.manifest import ExperimentManifest, SystemID
from experiments.m5.metrics import TrialResult, compute_trial_aggregates
from experiments.m5.splits import load_or_create_splits
from generation.base import BaseLLMProvider
from generation.providers.factory import build_provider
from generation.quality_rag import QualityAwareRAGPipeline
from generation.rag import BaselineRAGPipeline
from knowledge.schemas.benchmark import BenchmarkTask
from knowledge.schemas.tasks import (
    EngTaskRequest,
    EngTaskResponse,
    TaskClassification,
)
from retrieval.adaptive import ExperimentMode
from retrieval.strategies import RetrievalMode, RetrievalStrategyConfig
from verification.config import VerificationConfig
from verification.evaluators import (
    CitationGroundingEvaluator,
    EvidenceConsistencyEvaluator,
    EvidenceCoverageEvaluator,
    QueryRelevanceEvaluator,
)

logger = get_logger(__name__)

DEFAULT_RAW_DIR = Path("experiments/results/m5/raw")
DEFAULT_PROCESSED_DIR = Path("experiments/results/m5/processed")

M5_RAW_DIR = DEFAULT_RAW_DIR
M5_PROCESSED_DIR = DEFAULT_PROCESSED_DIR


_CLASSIFICATION_FIELDS = ("sdlc_stage", "task_type", "complexity", "criticality")


def _value(x: Any) -> Any:
    return x.value if hasattr(x, "value") else x


def _round(x: Optional[float], nd: int = 4) -> Optional[float]:
    return None if x is None else round(x, nd)


def _cpu_utilisation(start, end) -> Optional[float]:
    """Fraction of all CPU time that was busy between two psutil.cpu_times() snapshots."""
    total = sum(end) - sum(start)
    idle = (end.idle - start.idle) + (getattr(end, "iowait", 0.0) - getattr(start, "iowait", 0.0))
    return round(max(0.0, min(1.0, 1.0 - idle / total)), 4) if total > 0 else None


def baseline_b_strategy() -> RetrievalStrategyConfig:
    """System B's fixed hybrid retrieval (plan §7.1): dense 0.7 + BM25 0.3, top_k 5, no graph."""
    return RetrievalStrategyConfig(
        strategy_name="hybrid",
        mode=RetrievalMode.HYBRID,
        top_k=5,
        dense_weight=0.70,
        sparse_weight=0.30,
        include_graph_context=False,
    )


class M5BenchmarkRunner:
    """
    Orchestrates multi-system benchmark execution across dataset splits.
    """

    def __init__(
        self,
        manifest: Optional[ExperimentManifest] = None,
        llm_provider: Optional[BaseLLMProvider] = None,
        provider_name: Optional[str] = None,
        raw_output_dir: Optional[Path] = None,
        processed_output_dir: Optional[Path] = None,
    ) -> None:
        self.manifest = manifest or ExperimentManifest.create_default()
        self._manifest_hash = self.manifest.compute_hash()

        # No silent mock: unless a provider is passed or named explicitly
        # ("mock" is for tests only), runs use the configured real provider.
        self.llm_provider = llm_provider or build_provider(provider_name)

        self.raw_dir = raw_output_dir or M5_RAW_DIR
        self.processed_dir = processed_output_dir or M5_PROCESSED_DIR
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)

        self.dataset = BenchmarkDataset()
        self._correctness_eval = CorrectnessEvaluator()
        self._citation_eval = CitationGroundingEvaluator()
        self._relevance_eval = QueryRelevanceEvaluator()
        self._coverage_eval = EvidenceCoverageEvaluator()
        self._consistency_eval = EvidenceConsistencyEvaluator()

        from intelligence.classifier import RuleBasedTaskClassifier

        self._classifier = RuleBasedTaskClassifier()
        self._pipe_a: Optional[BaselineRAGPipeline] = None
        self._pipe_b: Optional[BaselineRAGPipeline] = None
        self._pipe_quality: Optional[QualityAwareRAGPipeline] = None

    def _get_pipeline_a(self, llm: BaseLLMProvider) -> BaselineRAGPipeline:
        if self._pipe_a is None or self._pipe_a.llm_provider != llm:
            self._pipe_a = BaselineRAGPipeline(llm_provider=llm)
        return self._pipe_a

    def _get_pipeline_b(self, llm: BaseLLMProvider) -> BaselineRAGPipeline:
        if self._pipe_b is None or self._pipe_b.llm_provider != llm:
            from retrieval.hybrid import HybridRetriever
            self._pipe_b = BaselineRAGPipeline(
                retriever=HybridRetriever(),
                llm_provider=llm,
            )
        return self._pipe_b

    def _get_pipeline_routed(self, llm: BaseLLMProvider) -> QualityAwareRAGPipeline:
        """System E + task-aware model routing (RQ4): same pipeline, plus a TierRouter."""
        if getattr(self, "_pipe_routed", None) is None or self._pipe_routed.llm_provider != llm:
            from retrieval.adaptive import AdaptiveRetrievalPipeline
            from routing.registry import ModelRegistry
            from routing.tier_router import TierRouter

            max_esc = self.manifest.systems[SystemID.SYSTEM_E_ROUTED.value].max_escalations
            self._pipe_routed = QualityAwareRAGPipeline(
                adaptive_pipeline=AdaptiveRetrievalPipeline(graph_store=self.graph_store),
                llm_provider=llm,
                verification_config=VerificationConfig(max_escalation_attempts=max_esc),
                model_router=TierRouter(ModelRegistry.from_yaml("configs/models.yaml")),
            )
        return self._pipe_routed

    def _get_pipeline_quality(self, llm: BaseLLMProvider) -> QualityAwareRAGPipeline:
        if self._pipe_quality is None or self._pipe_quality.llm_provider != llm:
            # The manifest's System E escalation limit must reach the pipeline;
            # previously it was never passed, so every run used the built-in 2
            # whatever the manifest (or a calibration candidate) said.
            max_esc = self.manifest.systems[SystemID.SYSTEM_E.value].max_escalations
            # Systems D and E need the knowledge graph. Without a graph_store the
            # graph retriever silently injects nothing and D equals C (found by
            # laptop-b's B3 review), so the store is always passed here.
            from retrieval.adaptive import AdaptiveRetrievalPipeline

            self._pipe_quality = QualityAwareRAGPipeline(
                adaptive_pipeline=AdaptiveRetrievalPipeline(graph_store=self.graph_store),
                llm_provider=llm,
                verification_config=VerificationConfig(max_escalation_attempts=max_esc),
            )
        return self._pipe_quality

    def _retrieval_label(self, task_id: str):
        """Human-checked retrieval label for a task (dev/val now; test labels only before the final run)."""
        if getattr(self, "_labels", None) is None:
            from benchmark.retrieval_labels import LABELS_PATH
            from evaluation.retrieval_metrics import Label

            raw = json.loads(LABELS_PATH.read_text(encoding="utf-8"))["labels"] if LABELS_PATH.exists() else []
            self._labels = {d["task_id"]: Label.from_json(d) for d in raw}
        return self._labels.get(task_id)

    @property
    def graph_store(self):
        if getattr(self, "_graph_store", None) is None:
            from core.config import settings
            from knowledge.graph.neo4j import Neo4jGraphStore

            gs = settings.graph_store
            self._graph_store = Neo4jGraphStore(uri=gs.uri, username=gs.username, password=gs.password)
        return self._graph_store

    def warm_up(self, system_ids: List[str]) -> Dict[str, Any]:
        """Load every retriever, index and model the given systems use, untimed.

        Original plan §10.4: one-time model loading is reported separately and never
        charged to a query. Without this, the first retrieval of each pipeline built
        the BM25 index (48,046 chunks) and loaded the encoders inside a measured trial
        (16–18 s instead of ~0.2 s on 2026-10-05). Returns what was warmed and how long.
        """
        query = "How is the application configured?"  # fixed warm-up query, not a benchmark task
        t0, warmed = time.perf_counter(), []
        if SystemID.BASELINE_B.value in system_ids:
            pipe = self._get_pipeline_b(self.llm_provider)
            pipe.retriever.retrieve(query=query, strategy=RetrievalStrategyConfig(
                strategy_name="hybrid", mode=RetrievalMode.HYBRID, top_k=5), task_id="warm-up")
            warmed.append("baseline_b:hybrid")
        task_aware = [s for s in system_ids if s not in (SystemID.BASELINE_A.value, SystemID.BASELINE_B.value)]
        if task_aware:
            pipes = [self._get_pipeline_quality(self.llm_provider)]
            if SystemID.SYSTEM_E_ROUTED.value in system_ids:
                pipes.append(self._get_pipeline_routed(self.llm_provider))
            clf = self._classifier.classify(EngTaskRequest(task_id="warm-up", query=query))
            graph_ok = bool(set(task_aware) - {SystemID.SYSTEM_C.value})
            for pipe in pipes:
                for name, cfg in pipe.adaptive_pipeline.list_strategies().items():
                    mode = ExperimentMode.SYSTEM_D if graph_ok else ExperimentMode.SYSTEM_C
                    pipe.adaptive_pipeline.retrieve(query=query, classification=clf, experiment_mode=mode,
                                                    override_strategy=cfg, task_id="warm-up")
                    warmed.append(name)
        return {"warmed": sorted(set(warmed)), "seconds": round(time.perf_counter() - t0, 2)}

    def graph_preflight(self) -> Dict[str, Any]:
        """Refuse D/E runs unless the populated wave-1 graph is reachable.

        This laptop holds only a 2-node test fixture until the wave-1 graph is built
        (WORK_PLAN step 5); D/E on it would quietly measure "no graph". Raises with the reason.
        """
        expected_repos = len(self.manifest.frozen_variables.repositories)
        store = self.graph_store
        if not store.is_available():
            raise RuntimeError("Neo4j is not reachable with the .env EIH_GRAPH_* settings; "
                               "Systems D/E need the knowledge graph.")
        repos, files = store.count_nodes("Repository"), store.count_nodes("File")
        if repos < expected_repos or files == 0:
            raise RuntimeError(f"Knowledge graph incomplete: {repos} Repository / {files} File nodes, "
                               f"expected {expected_repos} repositories. Restore C:\\EIH_share\\neo4j.dump "
                               "(WORK_PLAN step 5) before running Systems D/E.")
        return {"repository_nodes": repos, "file_nodes": files, "total_nodes": store.count_nodes(),
                "total_edges": store.count_edges()}

    def _execute_system(
        self,
        system_id: str,
        task: BenchmarkTask,
        llm_provider: BaseLLMProvider,
    ) -> EngTaskResponse:
        """
        Execute one task through the designated system pipeline.
        """
        # Systems A and B are not task-aware (original plan §7.1), so they get no
        # classification. Systems C, D and E classify the query with the REAL
        # rule-based classifier: the plan's classification is "automatically
        # inferred" (contribution C1, §6.2). This runner used to hand C-E the
        # benchmark's answer-key labels and quality threshold — an oracle the
        # system never has in use, which would inflate the task-awareness gain
        # Δ(B→C). The benchmark threshold is still what scores success
        # (_evaluate_trial); the system's own gate uses the classifier's threshold.
        req = EngTaskRequest(task_id=task.task_id, query=task.query, repository=task.repository)
        clf, classification_info = None, None
        if system_id not in (SystemID.BASELINE_A.value, SystemID.BASELINE_B.value):
            t0 = time.perf_counter()
            clf = self._classifier.classify(req)
            classification_info = {
                "source": self._classifier.classifier_name,
                "classification_ms": round((time.perf_counter() - t0) * 1000.0, 3),
                "predicted": {k: _value(getattr(clf, k)) for k in _CLASSIFICATION_FIELDS},
                "agreement_with_benchmark": {
                    k: _value(getattr(clf, k)) == _value(getattr(task, k)) for k in _CLASSIFICATION_FIELDS
                },
                "quality_threshold_used": clf.quality_threshold,
            }

        # CPU energy is ESTIMATED by a disclosed method (original plan §9.1, §12):
        # CPU TDP x system-wide CPU utilisation over this trial's window x duration.
        # Utilisation comes from psutil.cpu_times() snapshots, which (unlike
        # cpu_percent) no other call inside the window can reset.
        cpu_start, t_window = psutil.cpu_times(), time.perf_counter()
        response = self._dispatch(system_id, req, clf, llm_provider)
        window_s = time.perf_counter() - t_window
        response.metadata["cpu_window"] = {
            "utilisation": _cpu_utilisation(cpu_start, psutil.cpu_times()),
            "seconds": round(window_s, 4),
            "method": "system-wide psutil.cpu_times delta over the trial",
        }
        if classification_info is not None:
            response.metadata["classification"] = classification_info
        return response

    def _dispatch(
        self,
        system_id: str,
        req: EngTaskRequest,
        clf: Optional[TaskClassification],
        llm_provider: BaseLLMProvider,
    ) -> EngTaskResponse:
        if system_id == SystemID.BASELINE_A.value:
            pipe_a = self._get_pipeline_a(llm_provider)
            return pipe_a.execute(request=req, classification=clf, skip_retrieval=True)

        elif system_id == SystemID.BASELINE_B.value:
            pipe_b = self._get_pipeline_b(llm_provider)
            return pipe_b.execute(request=req, strategy=baseline_b_strategy(), classification=clf)

        elif system_id == SystemID.SYSTEM_C.value:
            pipe_q = self._get_pipeline_quality(llm_provider)
            return pipe_q.execute(
                request=req,
                classification=clf,
                experiment_mode=ExperimentMode.SYSTEM_C,
                skip_verification=True,
            )

        elif system_id == SystemID.SYSTEM_D.value:
            pipe_q = self._get_pipeline_quality(llm_provider)
            return pipe_q.execute(
                request=req,
                classification=clf,
                experiment_mode=ExperimentMode.SYSTEM_D,
                skip_verification=True,
            )

        elif system_id == SystemID.SYSTEM_E.value:
            pipe_q = self._get_pipeline_quality(llm_provider)
            return pipe_q.execute(
                request=req,
                classification=clf,
                experiment_mode=ExperimentMode.SYSTEM_D,
                skip_verification=False,
            )

        elif system_id == SystemID.SYSTEM_E_ROUTED.value:
            return self._get_pipeline_routed(llm_provider).execute(
                request=req,
                classification=clf,
                experiment_mode=ExperimentMode.SYSTEM_D,
                skip_verification=False,
            )

        else:
            raise ValueError(f"Unknown system_id '{system_id}'")

    def _evaluate_trial(
        self,
        system_id: str,
        task: BenchmarkTask,
        response: EngTaskResponse,
        trial_index: int,
        split_name: str,
    ) -> TrialResult:
        """
        Compute all Measured, Estimated, and Derived metrics for one trial execution.
        Enforces P0-1 (explicit ground-truth correctness weight) and P0-2 (refusal distinction).
        """
        req = EngTaskRequest(
            task_id=task.task_id,
            query=task.query,
            repository=task.repository,
        )

        # 1. Correctness against ground truth
        from evaluation.metrics import ExperimentResult as EvalExpResult
        eval_result = EvalExpResult(
            result_id=f"eval-{system_id}-{task.task_id}-{trial_index}",
            experiment_id=f"exp-m5-{split_name}",
            task_id=task.task_id,
            model_id=response.model_id or "unknown",
            answer_text=response.answer,
            quality_threshold=task.expected_quality_threshold,
        )
        corr_metric = self._correctness_eval.evaluate(
            eval_result,
            ground_truth=task.ground_truth,
            acceptable_alternatives=task.acceptable_alternatives,
        )
        # Missing scores stay missing (None): no invented 0.50. A trial with any missing
        # component has no composite, is excluded from quality aggregates and is counted.
        task_corr = corr_metric.task_correctness if corr_metric is not None else None

        # 2. Quality Gate Signals (System E's own evaluators; see the independent outcome
        #    measures in evaluation/outcome.py for RQ3)
        def _score(signals):
            return signals[0].score if signals and signals[0].score is not None else None

        cit_signals = self._citation_eval.evaluate(req, response)
        rel_signals = self._relevance_eval.evaluate(req, response)
        cov_signals = self._coverage_eval.evaluate(req, response)
        con_signals = self._consistency_eval.evaluate(req, response)
        cit_score, rel_score = _score(cit_signals), _score(rel_signals)
        cov_score, con_score = _score(cov_signals), _score(con_signals)
        components = {"task_correctness": task_corr, "citation_grounding": cit_score,
                      "query_relevance": rel_score, "evidence_coverage": cov_score,
                      "evidence_consistency": con_score}
        missing_scores = [k for k, v in components.items() if v is None]

        cit_valid_ratio = None
        if cit_signals and cit_signals[0].metadata.get("total_citations", 0) > 0:
            v = cit_signals[0].metadata.get("valid_citations", 0)
            t = cit_signals[0].metadata.get("total_citations", 1)
            cit_valid_ratio = v / t

        # Weighted Composite Quality (P0-1): 40% Ground-Truth Correctness + 25% Citation Support + 15% Relevance + 10% Coverage + 10% Consistency
        composite_q = None if missing_scores else round(
            (task_corr * 0.40) + (cit_score * 0.25) + (rel_score * 0.15) + (cov_score * 0.10) + (con_score * 0.10),
            4,
        )

        from evaluation.outcome import outcome as independent_outcome

        indep = independent_outcome(response.answer or "", self._retrieval_label(task.task_id))

        thresh = task.expected_quality_threshold
        is_refusal = "INSUFFICIENT EVIDENCE" in (response.answer or "")
        gt_exists = bool(task.ground_truth or task.acceptable_alternatives)

        # Refusal & Success Classification (P0-2)
        if is_refusal:
            if gt_exists:
                # Task required an answer, but system issued refusal -> UNFOUNDED_REFUSAL
                success_type = "UNFOUNDED_REFUSAL"
                qc_success = False
                passed = False
                refusal_score = 0.0
            else:
                # Task legitimately lacked ground truth evidence -> VALID_REFUSAL
                success_type = "VALID_REFUSAL"
                qc_success = True
                passed = True
                refusal_score = 0.50
        elif composite_q is None:
            refusal_score, passed, qc_success, success_type = 0.0, None, None, "MISSING_SCORES"
        else:
            refusal_score = 0.0
            passed = (composite_q >= thresh) and (task_corr >= thresh)
            if passed:
                success_type = "FACTUAL_SUCCESS"
                qc_success = True
            elif cit_score < 0.50:
                success_type = "CITATION_FAILURE"
                qc_success = False
            else:
                success_type = "QUALITY_FAILURE"
                qc_success = False

        # Telemetry extraction
        # No fallbacks: a missing measurement fails the trial loudly (the job
        # queue records it as an error) instead of being replaced by an invented
        # number. These used `x or <estimate>`, so a local model's valid cost of
        # 0.0 was replaced by gpt-4o-mini prices, and missing energy/CO2e by
        # 45 W + 60 W x latency at the UK grid intensity.
        missing = [name for name, value in (
            ("latency_ms", response.latency_ms), ("energy_joules", response.energy_joules),
            ("cost_usd", response.cost_usd), ("co2e_grams", response.co2e_grams),
        ) if value is None]
        if missing:
            raise ValueError(f"Trial {system_id}/{task.task_id} has no {missing}; "
                             "refusing to substitute estimates.")
        lat = response.latency_ms
        # Model loads (cold starts, routing reloads) measured by the provider. One record from
        # the baseline pipelines (generation_cold_start), a list from the quality pipeline.
        loads = list((response.metadata or {}).get("cold_starts") or [])
        if (response.metadata or {}).get("generation_cold_start"):
            loads.append(response.metadata["generation_cold_start"])
        load_energies = [((c or {}).get("energy") or {}).get("energy_j") for c in loads]
        load_j = sum(e for e in load_energies if e is not None) if loads else None
        in_tok = response.input_tokens or 0
        out_tok = response.output_tokens or 0
        tot_tok = in_tok + out_tok

        md = response.metadata or {}
        # Tiers as defined by the original plan §9.1: GPU energy MEASURED (NVML
        # counter; ESTIMATED if a rerank power sample is included), CPU energy,
        # CO2e and cost ESTIMATED; totals inherit the weakest tier.
        gpu_joules = response.energy_joules
        cpu_window = md.get("cpu_window")
        cpu_joules = None
        if cpu_window and cpu_window.get("utilisation") is not None:
            cpu_joules = (settings.sustainability.cpu_tdp_watts * cpu_window["utilisation"]
                          * cpu_window["seconds"])
        en_joules = gpu_joules + (cpu_joules or 0.0)
        cost = response.cost_usd
        co2e = (en_joules / 3_600_000.0) * self.manifest.frozen_variables.carbon_intensity_gco2_per_kwh
        breakdown = dict(md.get("latency_breakdown_ms") or {})
        classification_ms = (md.get("classification") or {}).get("classification_ms")
        if breakdown and classification_ms is not None:
            breakdown["query"] = classification_ms

        chunks_count = len(response.retrieval.chunks) if response.retrieval else 0
        graph_count = sum(1 for c in response.retrieval.chunks if c.metadata.get("graph_context")) if response.retrieval else 0

        # Derived Ratios (None without a composite)
        qpj = None if composite_q is None else round(composite_q / max(0.001, en_joules), 4)
        qpd = None if composite_q is None else round(composite_q / max(1e-7, cost), 2)
        qps = None if composite_q is None else round(composite_q / max(0.001, (lat / 1000.0)), 4)

        return TrialResult(
            experiment_id=f"exp-m5-{split_name}",
            system_id=system_id,
            task_id=task.task_id,
            benchmark_version=self.manifest.benchmark_version,
            dataset_split=split_name,
            trial_index=trial_index,
            timestamp=datetime.datetime.utcnow().isoformat(),
            manifest_hash=self._manifest_hash,
            latency_ms=round(lat + (classification_ms or 0.0), 2),
            retrieval_latency_ms=round(breakdown.get("retrieval", 0.0) + breakdown.get("rerank", 0.0), 2),
            generation_latency_ms=round(breakdown.get("generation", lat), 2),
            latency_breakdown_ms=breakdown or None,
            output_truncated=md.get("output_truncated"),
            input_tokens=in_tok,
            output_tokens=out_tok,
            total_tokens=tot_tok,
            retrieval_calls_count=1 if chunks_count > 0 else 0,
            chunks_retrieved_count=chunks_count,
            graph_chunks_count=graph_count,
            escalation_count=response.escalation_count,
            total_attempts=response.verification_details.get("total_attempts", 1) if response.verification_details else 1,
            gpu_energy_measured_joules=md.get("generation_energy_measured_joules"),
            cpu_energy_joules=round(cpu_joules, 4) if cpu_joules is not None else None,
            gpu_energy_joules=round(gpu_joules, 4),
            total_energy_joules=round(en_joules, 4),
            energy_tier=md.get("energy_tier"),
            total_energy_tier="ESTIMATED" if cpu_joules is not None else md.get("energy_tier"),
            gpu_max_temp_c=md.get("gpu_max_temp_c"),
            model_load_energy_joules=_round(load_j),
            model_loads=len(loads),
            cost_usd=round(cost, 6),
            co2e_grams=round(co2e, 6),
            task_correctness=_round(task_corr),
            citation_grounding=_round(cit_score),
            query_relevance=_round(rel_score),
            evidence_coverage=_round(cov_score),
            evidence_consistency=_round(con_score),
            correctness_score=_round(task_corr),
            groundedness_score=_round(cov_score),
            relevance_score=_round(rel_score),
            consistency_score=_round(con_score),
            citation_validity_rate=_round(cit_valid_ratio),
            missing_scores=missing_scores,
            has_retrieval_label=indep.has_label,
            line_citations=indep.line_citations,
            cited_span_precision=_round(indep.cited_span_precision),
            cited_span_recall=_round(indep.cited_span_recall),
            cited_file_recall=_round(indep.cited_file_recall),
            answer_supported=indep.supported,
            is_grounded_refusal=is_refusal,
            grounded_refusal_score=refusal_score,
            composite_quality=composite_q,
            quality_threshold=thresh,
            passed_quality_gate=passed,
            success_type=success_type,
            quality_constrained_success=qc_success,
            quality_per_joule=qpj,
            quality_per_dollar=qpd,
            quality_per_second=qps,
            generated_answer=response.answer,
            metadata={
                "classification": md.get("classification"),
                "sdlc_stage": task.sdlc_stage.value if hasattr(task.sdlc_stage, "value") else str(task.sdlc_stage),
                "repository": task.repository,
                "complexity": task.complexity.value if hasattr(task.complexity, "value") else str(task.complexity),
                "criticality": task.criticality.value if hasattr(task.criticality, "value") else str(task.criticality),
            },
        )

    def run_split(
        self,
        split_name: str = "dev",
        system_ids: Optional[List[str]] = None,
        trials_count: int = 3,
        max_tasks: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Execute benchmark evaluation across systems on the selected split.

        Parameters
        ----------
        split_name : str
            "dev" or "val" (Test split strictly reserved for final evaluation).
        system_ids : List[str], optional
            Systems to evaluate. Default: all 5 systems.
        trials_count : int
            Number of repetitions per task/system pair. Default: 3.
        max_tasks : int, optional
            Limit tasks (for fast unit verification).

        Returns
        -------
        Dict[str, Any]
            Processed results dictionary containing trial records and aggregations.
        """
        target_systems = system_ids or [
            SystemID.BASELINE_A.value,
            SystemID.BASELINE_B.value,
            SystemID.SYSTEM_C.value,
            SystemID.SYSTEM_D.value,
            SystemID.SYSTEM_E.value,
        ]

        # Load benchmark tasks and splits
        from benchmark.dataset import BenchmarkDataset
        from experiments.m5.splits import BENCHMARK_TASKS_PATH

        ds = BenchmarkDataset.load_from_json(BENCHMARK_TASKS_PATH)
        splits_data = load_or_create_splits()

        target_task_ids = set(splits_data["splits"].get(split_name, []))
        tasks = [t for t in ds.tasks if t.task_id in target_task_ids]

        if max_tasks is not None:
            tasks = tasks[:max_tasks]

        logger.info(
            f"Starting M5 benchmark on '{split_name}' split: "
            f"{len(tasks)} tasks x {len(target_systems)} systems x {trials_count} trials."
        )

        llm = self.llm_provider

        all_trial_results: Dict[str, List[TrialResult]] = {sys_id: [] for sys_id in target_systems}

        for sys_id in target_systems:
            raw_file = self.raw_dir / f"{sys_id}_{split_name}.jsonl"

            for trial_idx in range(trials_count):
                for task in tasks:
                    try:
                        resp = self._execute_system(system_id=sys_id, task=task, llm_provider=llm)
                        trial_res = self._evaluate_trial(
                            system_id=sys_id,
                            task=task,
                            response=resp,
                            trial_index=trial_idx,
                            split_name=split_name,
                        )
                        all_trial_results[sys_id].append(trial_res)

                        # Write immediately to raw JSONL
                        with open(raw_file, "a", encoding="utf-8") as f:
                            f.write(trial_res.model_dump_json() + "\n")

                    except Exception as exc:
                        logger.exception(
                            f"Execution error on sys={sys_id}, task={task.task_id}, trial={trial_idx}: {str(exc)}"
                        )

        # Compute task-level aggregations across trials
        aggregations: Dict[str, List[Dict[str, Any]]] = {}
        for sys_id, trials in all_trial_results.items():
            task_groups: Dict[str, List[TrialResult]] = {}
            for tr in trials:
                task_groups.setdefault(tr.task_id, []).append(tr)

            agg_list = [compute_trial_aggregates(t_list).model_dump() for t_list in task_groups.values()]
            aggregations[sys_id] = agg_list

        processed_summary = {
            "benchmark_version": self.manifest.benchmark_version,
            "manifest_hash": self._manifest_hash,
            "split_name": split_name,
            "tasks_evaluated": len(tasks),
            "systems_evaluated": target_systems,
            "trials_per_task": trials_count,
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "aggregations": aggregations,
        }

        # Save processed summary
        proc_file = self.processed_dir / f"summary_{split_name}.json"
        with open(proc_file, "w", encoding="utf-8") as f:
            json.dump(processed_summary, f, indent=2)

        return processed_summary


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run Phase-2 M5 Controlled Benchmark")
    parser.add_argument("--split", type=str, default="dev", choices=["dev", "val", "test"], help="Dataset split")
    parser.add_argument("--trials", type=int, default=3, help="Number of trials per task")
    parser.add_argument("--manifest", type=str, default=None, help="Path to custom experiment manifest JSON")
    parser.add_argument("--provider", type=str, default=None,
                        help="LLM provider: ollama (default from settings) | openai | mock (tests only, never results)")
    args = parser.parse_args()

    custom_manifest = None
    if args.manifest:
        with open(args.manifest, "r", encoding="utf-8") as f:
            custom_manifest = ExperimentManifest(**json.load(f))

    benchmark_runner = M5BenchmarkRunner(manifest=custom_manifest, provider_name=args.provider)
    res = benchmark_runner.run_split(split_name=args.split, trials_count=args.trials)
    print(f"M5 benchmark run complete for split='{args.split}'. Evaluated {res['tasks_evaluated']} tasks.")
