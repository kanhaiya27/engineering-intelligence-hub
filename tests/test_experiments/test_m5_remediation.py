"""
Engineering Intelligence Hub — P0 Remediation & Quality-Constrained Success Tests
===================================================================================
Regression tests for P0-1 (Ground-Truth Correctness inclusion) and P0-2 (Refusal handling).

Verifies 5 distinct response scenarios:
  1. correct_answer         -> FACTUAL_SUCCESS (quality_constrained_success = True)
  2. incorrect_answer       -> QUALITY_FAILURE (quality_constrained_success = False)
  3. grounded_refusal       -> VALID_REFUSAL when GT absent, UNFOUNDED_REFUSAL when GT present
  4. unsupported_answer     -> CITATION_FAILURE (quality_constrained_success = False)
  5. partially_correct_answer -> Evaluated against threshold
"""

from __future__ import annotations


from experiments.m5.runner import M5BenchmarkRunner
from generation.base import BaseLLMProvider, GenerationRequest, GenerationResponse
from knowledge.schemas.benchmark import BenchmarkTask
from knowledge.schemas.tasks import EngTaskResponse, RetrievalResult, RetrievedChunk


class CannedResponseLLMProvider(BaseLLMProvider):
    """LLM Provider returning controllable canned text for evaluation testing."""

    def __init__(self, response_text: str) -> None:
        self.response_text = response_text

    @property
    def provider_name(self) -> str:
        return "canned"

    def is_available(self) -> bool:
        return True

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        return GenerationResponse(
            text=self.response_text,
            model_id=request.model_id,
            input_tokens=100,
            output_tokens=50,
            latency_ms=20.0,
        )


def _make_dummy_task(ground_truth: str = "In Flask, routes are registered using app.add_url_rule() or the @app.route decorator.",
                     threshold: float = 0.70) -> BenchmarkTask:
    return BenchmarkTask(
        task_id="test-task-p0-001",
        sdlc_stage="development",
        task_type="code_explanation",
        difficulty="medium",
        complexity="medium",
        criticality="medium",
        repository="pallets/flask",
        query="How are URL routes added in Flask?",
        ground_truth=ground_truth,
        expected_quality_threshold=threshold,
    )


def test_scenario_1_correct_answer():
    """Scenario 1: Correct answer with proper citation -> FACTUAL_SUCCESS.

    Correctness is plain token F1 (0.774 here). Until 2026-10-05 it was silently multiplied by
    1.5 and capped at 1.0; this scenario uses a 0.60 threshold instead of relying on that.
    """
    task = _make_dummy_task(ground_truth="In Flask, routes are registered using app.add_url_rule() or the @app.route decorator.",
                            threshold=0.60)
    llm = CannedResponseLLMProvider(
        "SUPPORTED BY EVIDENCE:\nIn Flask, routes are registered using `app.add_url_rule()` or the `@app.route` decorator [`src/flask/app.py:L10-L25`]."
    )
    runner = M5BenchmarkRunner(llm_provider=llm)

    chunks = [
        RetrievedChunk(
            chunk_id="c1",
            source_path="src/flask/app.py",
            content="def add_url_rule(self, rule, endpoint=None, view_func=None): pass",
            score=0.90,
            metadata={"start_line": 10, "end_line": 25},
        )
    ]
    eng_resp = EngTaskResponse(
        task_id=task.task_id,
        answer=llm.response_text,
        retrieval=RetrievalResult(task_id=task.task_id, query=task.query, strategy_used="hybrid", chunks=chunks),
        latency_ms=20.0,
        energy_joules=1.0, cost_usd=0.0, co2e_grams=0.0,  # explicit: the runner no longer invents them
    )

    trial = runner._evaluate_trial("baseline_b", task, eng_resp, trial_index=0, split_name="dev")

    assert trial.task_correctness == 0.7742  # plain F1: no x1.5
    assert trial.composite_quality >= 0.60 and trial.missing_scores == []
    assert trial.success_type == "FACTUAL_SUCCESS"
    assert trial.quality_constrained_success is True


def test_scenario_2_incorrect_answer():
    """Scenario 2: Factually incorrect / off-topic answer -> QUALITY_FAILURE."""
    task = _make_dummy_task(ground_truth="In Flask, routes are registered using app.add_url_rule() or the @app.route decorator.")
    llm = CannedResponseLLMProvider(
        "Database connection pools in SQLAlchemy are configured using create_engine with pool_size parameters [`src/flask/app.py`]."
    )
    runner = M5BenchmarkRunner(llm_provider=llm)

    chunks = [
        RetrievedChunk(
            chunk_id="c1",
            source_path="src/flask/app.py",
            content="def add_url_rule(self, rule): pass",
            score=0.90,
        )
    ]
    eng_resp = EngTaskResponse(
        task_id=task.task_id,
        answer=llm.response_text,
        retrieval=RetrievalResult(task_id=task.task_id, query=task.query, strategy_used="hybrid", chunks=chunks),
        latency_ms=20.0,
        energy_joules=1.0, cost_usd=0.0, co2e_grams=0.0,  # explicit: the runner no longer invents them
    )

    trial = runner._evaluate_trial("baseline_b", task, eng_resp, trial_index=0, split_name="dev")

    assert trial.task_correctness < 0.60
    assert trial.quality_constrained_success is False
    assert trial.success_type in ("QUALITY_FAILURE", "CITATION_FAILURE")


def test_scenario_3_unfounded_refusal_when_ground_truth_exists():
    """Scenario 3A: Refusal issued for a task that HAS ground truth -> UNFOUNDED_REFUSAL (QC Success = False)."""
    task = _make_dummy_task(ground_truth="Flask routes use add_url_rule.")
    llm = CannedResponseLLMProvider(
        "INSUFFICIENT EVIDENCE: The provided repository context does not contain sufficient information to answer."
    )
    runner = M5BenchmarkRunner(llm_provider=llm)

    eng_resp = EngTaskResponse(
        task_id=task.task_id,
        answer=llm.response_text,
        retrieval=RetrievalResult(task_id=task.task_id, query=task.query, strategy_used="hybrid", chunks=[]),
        latency_ms=20.0,
        energy_joules=1.0, cost_usd=0.0, co2e_grams=0.0,  # explicit: the runner no longer invents them
    )

    trial = runner._evaluate_trial("system_e", task, eng_resp, trial_index=0, split_name="dev")

    assert trial.is_grounded_refusal is True
    assert trial.success_type == "UNFOUNDED_REFUSAL"
    assert trial.quality_constrained_success is False


def test_scenario_3_valid_refusal_when_ground_truth_absent():
    """Scenario 3B: Refusal issued for a task WITHOUT ground truth -> VALID_REFUSAL (QC Success = True)."""
    task = _make_dummy_task(ground_truth="")  # Unanswerable query
    llm = CannedResponseLLMProvider(
        "INSUFFICIENT EVIDENCE: The provided repository context does not contain sufficient information to answer."
    )
    runner = M5BenchmarkRunner(llm_provider=llm)

    eng_resp = EngTaskResponse(
        task_id=task.task_id,
        answer=llm.response_text,
        retrieval=RetrievalResult(task_id=task.task_id, query=task.query, strategy_used="hybrid", chunks=[]),
        latency_ms=20.0,
        energy_joules=1.0, cost_usd=0.0, co2e_grams=0.0,  # explicit: the runner no longer invents them
    )

    trial = runner._evaluate_trial("system_e", task, eng_resp, trial_index=0, split_name="dev")

    assert trial.is_grounded_refusal is True
    assert trial.success_type == "VALID_REFUSAL"
    assert trial.quality_constrained_success is True


def test_scenario_4_unsupported_citation():
    """Scenario 4: Answer cites a file absent from retrieved evidence -> CITATION_FAILURE."""
    task = _make_dummy_task()
    llm = CannedResponseLLMProvider(
        "In Flask, routes are defined in [`src/flask/non_existent_file.py:L10`]."
    )
    runner = M5BenchmarkRunner(llm_provider=llm)

    chunks = [
        RetrievedChunk(
            chunk_id="c1",
            source_path="src/flask/app.py",
            content="def add_url_rule(): pass",
            score=0.90,
        )
    ]
    eng_resp = EngTaskResponse(
        task_id=task.task_id,
        answer=llm.response_text,
        retrieval=RetrievalResult(task_id=task.task_id, query=task.query, strategy_used="hybrid", chunks=chunks),
        latency_ms=20.0,
        energy_joules=1.0, cost_usd=0.0, co2e_grams=0.0,  # explicit: the runner no longer invents them
    )

    trial = runner._evaluate_trial("baseline_b", task, eng_resp, trial_index=0, split_name="dev")

    assert trial.citation_grounding < 0.50
    assert trial.success_type == "CITATION_FAILURE"
    assert trial.quality_constrained_success is False


def test_scenario_5_partially_correct_answer():
    """Scenario 5: Partially correct answer evaluated against threshold."""
    task = _make_dummy_task()
    task.expected_quality_threshold = 0.90  # Strict threshold

    llm = CannedResponseLLMProvider(
        "Flask handles routes by mapping URL rules [`src/flask/app.py`]."
    )
    runner = M5BenchmarkRunner(llm_provider=llm)

    chunks = [
        RetrievedChunk(
            chunk_id="c1",
            source_path="src/flask/app.py",
            content="def add_url_rule(): pass",
            score=0.90,
        )
    ]
    eng_resp = EngTaskResponse(
        task_id=task.task_id,
        answer=llm.response_text,
        retrieval=RetrievalResult(task_id=task.task_id, query=task.query, strategy_used="hybrid", chunks=chunks),
        latency_ms=20.0,
        energy_joules=1.0, cost_usd=0.0, co2e_grams=0.0,  # explicit: the runner no longer invents them
    )

    trial = runner._evaluate_trial("baseline_b", task, eng_resp, trial_index=0, split_name="dev")

    assert trial.composite_quality < task.expected_quality_threshold
    assert trial.quality_constrained_success is False


def test_correctness_is_plain_token_f1():
    from evaluation.scorers.correctness import CorrectnessEvaluator

    ev = CorrectnessEvaluator()
    # pred {a,b,c,d}, ref {a,b,x,y}: P = R = 0.5 -> F1 = 0.5 (was min(1, 0.75))
    assert ev.compute_f1_score("a b c d", "a b x y") == 0.5


def test_missing_scores_are_not_invented():
    """An evaluator that returns no score leaves the component None, no composite, excluded."""
    task = _make_dummy_task()
    llm = CannedResponseLLMProvider("Routes use add_url_rule [`src/flask/app.py:L10-L25`].")
    runner = M5BenchmarkRunner(llm_provider=llm)
    runner._relevance_eval.evaluate = lambda req, resp: []  # evaluator produced nothing
    eng_resp = EngTaskResponse(
        task_id=task.task_id, answer=llm.response_text,
        retrieval=RetrievalResult(task_id=task.task_id, strategy_used="hybrid", chunks=[]),
        latency_ms=20.0, energy_joules=1.0, cost_usd=0.0, co2e_grams=0.0,
    )
    trial = runner._evaluate_trial("baseline_b", task, eng_resp, trial_index=0, split_name="dev")
    assert trial.query_relevance is None and trial.missing_scores == ["query_relevance"]
    assert trial.composite_quality is None and trial.quality_constrained_success is None
    assert trial.success_type == "MISSING_SCORES" and trial.quality_per_joule is None

    from experiments.m5.metrics import compute_trial_aggregates

    agg = compute_trial_aggregates([trial])
    assert agg.trials_missing_scores == 1 and agg.composite_quality_mean is None
    assert agg.quality_constrained_success_rate is None
