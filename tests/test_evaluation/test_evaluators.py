"""
Tests for CorrectnessEvaluator, GroundednessEvaluator, RelevanceEvaluator, and BaselineEvaluatorSuite
"""


from evaluation.metrics import ExperimentResult
from evaluation.scorers.correctness import CorrectnessEvaluator
from evaluation.scorers.groundedness import GroundednessEvaluator
from evaluation.scorers.relevance import RelevanceEvaluator
from evaluation.suite import BaselineEvaluatorSuite


def test_correctness_evaluator():
    evaluator = CorrectnessEvaluator()
    res = ExperimentResult(
        result_id="r1",
        experiment_id="exp1",
        task_id="t1",
        answer_text="Flask routing is managed by the route decorator in app.py delegating to add_url_rule.",
        quality_threshold=0.6,
    )
    ground_truth = "In Flask, routing is handled by the route decorator delegating to add_url_rule."

    metrics = evaluator.evaluate(res, ground_truth=ground_truth)
    assert metrics.task_correctness is not None
    assert metrics.task_correctness > 0.6
    assert metrics.passed_quality_gate is True


def test_groundedness_evaluator():
    evaluator = GroundednessEvaluator()

    # Grounded response with citation and tag
    res_grounded = ExperimentResult(
        result_id="r2",
        experiment_id="exp1",
        task_id="t2",
        answer_text="SUPPORTED BY EVIDENCE: Route definition is in `src/flask/app.py:L10-L20`.",
        quality_threshold=0.7,
    )
    m_grounded = evaluator.evaluate(res_grounded)
    assert m_grounded.groundedness is not None
    assert m_grounded.groundedness >= 0.85
    assert m_grounded.passed_quality_gate is True

    # Refusal response
    res_refusal = ExperimentResult(
        result_id="r3",
        experiment_id="exp1",
        task_id="t3",
        answer_text="INSUFFICIENT EVIDENCE: Repository does not contain database migration files.",
        quality_threshold=0.7,
    )
    m_refusal = evaluator.evaluate(res_refusal)
    assert m_refusal.groundedness >= 0.85


def test_relevance_evaluator():
    evaluator = RelevanceEvaluator()
    res = ExperimentResult(
        result_id="r4",
        experiment_id="exp1",
        task_id="t4",
        answer_text="The FastAPI dependency injection system is declared using Depends().",
        quality_threshold=0.6,
    )
    query = "How does FastAPI dependency injection work?"
    metrics = evaluator.evaluate(res, query=query)
    assert metrics.relevance is not None
    assert metrics.relevance >= 0.6


def test_baseline_evaluator_suite():
    suite = BaselineEvaluatorSuite()
    res = ExperimentResult(
        result_id="r5",
        experiment_id="exp1",
        task_id="t5",
        answer_text="SUPPORTED BY EVIDENCE: In Flask, routing is handled by `src/flask/app.py`.",
        quality_threshold=0.7,
    )
    metrics = suite.evaluate(
        res,
        query="How does Flask handle routing?",
        ground_truth="Routing in Flask is defined in app.py.",
    )
    assert metrics.aggregated_quality_score is not None
    assert metrics.aggregated_quality_score >= 0.7
    assert metrics.passed_quality_gate is True
