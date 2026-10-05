"""
Measurement-integrity fixes found by the job-queue smoke run and the API review (2026-10-05):

  * the M5 runner substituted invented numbers for missing/zero energy, cost and CO2e
    (a local model's valid cost of 0.0 became gpt-4o-mini prices)
  * measured NVML energy never reached TrialResult (gpu_energy_measured_joules=None)
  * System A was given the evidence-only prompt and refused every task
  * EnergyEstimator labelled a failed NVML read as a measurement (F2) and a single
    power sample as a measurement (F3)
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import List

import pytest

from experiments.m5.runner import M5BenchmarkRunner
from generation.base import BaseLLMProvider, GenerationRequest, GenerationResponse
from generation.rag import NO_RETRIEVAL_SYSTEM_PROMPT, SYSTEM_PROMPT, BaselineRAGPipeline
from knowledge.schemas.tasks import EngTaskRequest, EngTaskResponse, RetrievalResult, RetrievedChunk
from sustainability.energy.estimator import EnergyEstimationMethod, EnergyEstimator


class RecordingLLM(BaseLLMProvider):
    """Returns a fixed answer and records every request; reports MEASURED energy like Ollama."""

    def __init__(self) -> None:
        self.requests: List[GenerationRequest] = []

    @property
    def provider_name(self) -> str:
        return "recording"

    def is_available(self) -> bool:
        return True

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        self.requests.append(request)
        return GenerationResponse(
            text="Flask stores configuration in app.config.", model_id=request.model_id,
            input_tokens=120, output_tokens=12, latency_ms=900.0, finish_reason="stop",
            extra={"energy_joules": 250.0, "measurement_tiers": {"energy_joules": "MEASURED", "cost_usd": "ESTIMATED"},
                   "cost_usd": 0.0, "energy": {"max_temp_c": 71}},
        )


class NoRetriever:
    def retrieve(self, **kw):  # pragma: no cover - System A must never call it
        raise AssertionError("System A must not retrieve")


@pytest.fixture(scope="module")
def runner(tmp_path_factory):
    d = tmp_path_factory.mktemp("m5")
    return M5BenchmarkRunner(llm_provider=RecordingLLM(), raw_output_dir=d / "raw", processed_output_dir=d / "p")


@pytest.fixture(scope="module")
def task():
    from scripts.job_queue import load_split_tasks

    return load_split_tasks("dev")[0]


def response(**kw) -> EngTaskResponse:
    base = dict(task_id="t", answer="Flask stores configuration in app.config.", model_id="qwen2.5-coder:7b",
                input_tokens=120, output_tokens=12, latency_ms=900.0, energy_joules=250.0, cost_usd=0.0,
                co2e_grams=0.0495, metadata={"generation_energy_measured_joules": 250.0, "energy_tier": "MEASURED",
                                             "gpu_max_temp_c": 71})
    base.update(kw)
    return EngTaskResponse(**base)


# ----------------------------------------------------------------------------- runner
def test_local_zero_cost_is_kept_and_measured_energy_reaches_the_trial(runner, task):
    t = runner._evaluate_trial("baseline_a", task, response(), trial_index=0, split_name="dev")
    assert t.cost_usd == 0.0, "a local model's cost of 0.0 must not become API prices"
    assert t.gpu_energy_joules == 250.0 and t.gpu_energy_measured_joules == 250.0 and t.energy_tier == "MEASURED"
    assert t.cpu_energy_joules is None and t.total_energy_joules == 250.0, "no CPU window -> no CPU estimate"
    assert t.gpu_max_temp_c == 71


def test_cpu_energy_is_estimated_from_the_trial_window_and_totals_follow_plan_tiers(runner, task):
    from core.config import settings

    md = {"generation_energy_measured_joules": 250.0, "energy_tier": "MEASURED",
          "cpu_window": {"utilisation": 0.25, "seconds": 2.0},
          "latency_breakdown_ms": {"retrieval": 100.0, "rerank": 0.0, "context": 1.0, "generation": 1800.0,
                                   "other": 5.0},
          "classification": {"classification_ms": 0.4}, "output_truncated": True}
    t = runner._evaluate_trial("system_c", task, response(metadata=md, latency_ms=1906.0), 0, "dev")
    cpu = settings.sustainability.cpu_tdp_watts * 0.25 * 2.0
    assert t.cpu_energy_joules == pytest.approx(cpu)
    assert t.total_energy_joules == pytest.approx(250.0 + cpu) and t.total_energy_tier == "ESTIMATED"
    intensity = runner.manifest.frozen_variables.carbon_intensity_gco2_per_kwh
    assert t.co2e_grams == pytest.approx((250.0 + cpu) / 3_600_000.0 * intensity, abs=1e-6)
    assert t.latency_breakdown_ms["query"] == 0.4 and t.generation_latency_ms == 1800.0
    assert t.output_truncated is True


def test_cpu_utilisation_from_cpu_times_snapshots():
    from collections import namedtuple

    from experiments.m5.runner import _cpu_utilisation

    T = namedtuple("T", "user system idle")
    assert _cpu_utilisation(T(10, 10, 80), T(20, 20, 100)) == pytest.approx(0.5)
    assert _cpu_utilisation(T(1, 1, 1), T(1, 1, 1)) is None


@pytest.mark.parametrize("missing", ["energy_joules", "cost_usd", "co2e_grams", "latency_ms"])
def test_missing_measurement_fails_the_trial_instead_of_being_invented(runner, task, missing):
    with pytest.raises(ValueError, match="refusing to substitute"):
        runner._evaluate_trial("system_e", task, response(**{missing: None}), trial_index=0, split_name="dev")


# ----------------------------------------------------------------------------- System A prompt
def test_system_a_gets_the_no_retrieval_prompt_and_no_evidence_block():
    llm = RecordingLLM()
    pipe = BaselineRAGPipeline(retriever=NoRetriever(), llm_provider=llm)
    resp = pipe.execute(EngTaskRequest(task_id="t", query="Which key enables debug mode in Flask?"),
                        skip_retrieval=True)
    req = llm.requests[0]
    assert req.system_prompt == NO_RETRIEVAL_SYSTEM_PROMPT != SYSTEM_PROMPT
    assert "RETRIEVED REPOSITORY EVIDENCE" not in req.prompt
    assert resp.metadata["system_prompt"] == "no_retrieval" and resp.metadata["retrieval_strategy"] == "none"
    assert resp.metadata["generation_energy_measured_joules"] == 250.0 and resp.metadata["energy_tier"] == "MEASURED"


def test_retrieval_systems_keep_the_evidence_grounded_prompt():
    llm = RecordingLLM()
    chunk = RetrievedChunk(chunk_id="c1", content="app.config['DEBUG']", score=1.0, source_path="src/flask/app.py",
                           repository="pallets/flask", metadata={"start_line": 1, "end_line": 2})
    result = RetrievalResult(task_id="t", strategy_used="hybrid", chunks=[chunk], total_retrieved=1)
    retriever = SimpleNamespace(retrieve=lambda **kw: result)
    BaselineRAGPipeline(retriever=retriever, llm_provider=llm).execute(
        EngTaskRequest(task_id="t", query="Which key enables debug mode in Flask?"))
    assert llm.requests[0].system_prompt == SYSTEM_PROMPT
    assert "RETRIEVED REPOSITORY EVIDENCE" in llm.requests[0].prompt


# ----------------------------------------------------------------------------- estimator labels
def test_failed_nvml_read_is_labelled_tdp_proxy_not_measurement(monkeypatch):
    est = EnergyEstimator(cpu_tdp_watts=45.0, gpu_tdp_watts=80.0)
    est._nvml_available = True
    monkeypatch.setattr(est, "_measure_gpu_energy_nvml", lambda s: None)
    r = est.estimate(1000.0, 0, 0, "cross-encoder", is_local_model=True)
    assert r.method == EnergyEstimationMethod.TDP_PROXY
    assert r.gpu_energy_joules == pytest.approx(80.0 * 0.70 * 1.0)


def test_single_nvml_power_sample_is_labelled_as_a_sample():
    est = EnergyEstimator(cpu_tdp_watts=45.0, gpu_tdp_watts=80.0)
    est._nvml_available = True
    est._measure_gpu_energy_nvml = lambda s: (30.0 * s, 55.0)
    r = est.estimate(2000.0, 0, 0, "cross-encoder", is_local_model=True)
    assert r.method == EnergyEstimationMethod.NVML_POWER_SAMPLE and r.is_estimate is True
    assert r.gpu_energy_joules == pytest.approx(60.0)


# ----------------------------------------------------------------------------- knowledge graph wiring
def _store(repos: int, files: int, available: bool = True):
    from knowledge.graph.base import GraphNode
    from knowledge.graph.in_memory import InMemoryGraphStore

    store = InMemoryGraphStore()
    for i in range(repos):
        store.upsert_node(GraphNode(f"repo:r{i}", "Repository"))
    for i in range(files):
        store.upsert_node(GraphNode(f"file:r0:f{i}.py", "File"))
    store.is_available = lambda: available
    return store


def test_systems_d_e_pipeline_is_built_with_the_graph_store(runner):
    runner._graph_store = _store(6, 10)
    runner._pipe_quality = None
    pipe = runner._get_pipeline_quality(runner.llm_provider)
    assert pipe.adaptive_pipeline._graph_store is runner._graph_store, "D/E without a graph equals C"


@pytest.mark.parametrize("repos,files,available,match", [
    (0, 1, True, "incomplete"),      # laptop-a's 2-node test fixture
    (5, 100, True, "incomplete"),    # a repository missing
    (6, 100, False, "not reachable"),
])
def test_graph_preflight_refuses_a_missing_or_partial_graph(runner, repos, files, available, match):
    runner._graph_store = _store(repos, files, available)
    with pytest.raises(RuntimeError, match=match):
        runner.graph_preflight()


def test_graph_preflight_passes_for_the_full_wave1_graph(runner):
    runner._graph_store = _store(6, 4228)
    info = runner.graph_preflight()
    assert info["repository_nodes"] == 6 and info["file_nodes"] == 4228


# ----------------------------------------------------------------------------- real classifier for C/D/E
@pytest.mark.parametrize("system_id", ["system_c", "system_d", "system_e"])
def test_task_aware_systems_use_the_real_classifier_not_the_answer_key(runner, task, monkeypatch, system_id):
    seen = {}

    def fake_dispatch(sid, req, clf, llm):
        seen.update(req=req, clf=clf)
        return response()

    monkeypatch.setattr(runner, "_dispatch", fake_dispatch)
    resp = runner._execute_system(system_id, task, runner.llm_provider)
    expected = runner._classifier.classify(EngTaskRequest(task_id=task.task_id, query=task.query,
                                                          repository=task.repository))
    assert seen["req"].quality_threshold_override is None, "the benchmark threshold must not leak into the system"
    assert seen["clf"].model_dump(exclude={"classified_at", "reasons"}) == \
        expected.model_dump(exclude={"classified_at", "reasons"})
    info = resp.metadata["classification"]
    assert info["source"] == "rule_based_task_classifier" and info["classification_ms"] >= 0
    assert set(info["agreement_with_benchmark"]) == {"sdlc_stage", "task_type", "complexity", "criticality"}


@pytest.mark.parametrize("system_id", ["baseline_a", "baseline_b"])
def test_non_task_aware_baselines_get_no_classification(runner, task, monkeypatch, system_id):
    seen = {}
    monkeypatch.setattr(runner, "_dispatch", lambda sid, req, clf, llm: seen.update(clf=clf) or response())
    resp = runner._execute_system(system_id, task, runner.llm_provider)
    assert seen["clf"] is None and "classification" not in resp.metadata
