"""
Tests for Baseline A and Baseline B Experiment Runners
"""

from pathlib import Path
import tempfile
import pytest

from evaluation.suite import BaselineEvaluatorSuite
from experiments.baselines.baseline_a import BaselineARunner
from experiments.baselines.baseline_b import BaselineBRunner
from experiments.config import BaselineID, ExperimentConfig, ExperimentType
from experiments.logger import ExperimentLogger
from generation.providers.openai import MockLLMProvider
from generation.rag import BaselineRAGPipeline
from knowledge.schemas.artifacts import ArtifactType, KnowledgeChunk
from knowledge.schemas.benchmark import (
    BenchmarkTask,
    BenchmarkTaskStatus,
    DifficultyLevel,
    SourceEvidence,
    SourceEvidenceType,
)
from knowledge.schemas.tasks import (
    ComplexityLevel,
    CriticalityLevel,
    SDLCStage,
    TaskType,
)
from retrieval.bm25 import BM25Retriever


@pytest.fixture
def test_experiment_environment():
    with tempfile.TemporaryDirectory() as tmpdir:
        res_dir = Path(tmpdir)
        logger_a = ExperimentLogger(experiment_id="test_exp_a", results_dir=res_dir)
        logger_b = ExperimentLogger(experiment_id="test_exp_b", results_dir=res_dir)

        chunks = [
            KnowledgeChunk(
                chunk_id="flask-route-1",
                artifact_id="flask-src-1",
                artifact_type=ArtifactType.SOURCE_CODE,
                repository="pallets/flask",
                content="def route(self, rule: str, **options): return self.add_url_rule(rule, endpoint, f, **options)",
                chunk_index=0,
                metadata={"symbol_name": "Flask.route", "file_path": "src/flask/app.py"},
            )
        ]
        retriever = BM25Retriever(chunks=chunks)
        provider = MockLLMProvider()
        rag_pipeline = BaselineRAGPipeline(retriever=retriever, llm_provider=provider)
        evaluator_suite = BaselineEvaluatorSuite()

        task = BenchmarkTask(
            task_id="eih-test-001",
            repository="pallets/flask",
            sdlc_stage=SDLCStage.DEVELOPMENT,
            task_type=TaskType.CODE_EXPLANATION,
            difficulty=DifficultyLevel.EASY,
            complexity=ComplexityLevel.LOW,
            criticality=CriticalityLevel.LOW,
            query="Explain routing in Flask",
            ground_truth="In Flask, routing is handled by the route decorator in src/flask/app.py which delegates to add_url_rule.",
            expected_quality_threshold=0.7,
            source_evidence=[
                SourceEvidence(
                    evidence_type=SourceEvidenceType.SOURCE_FILE,
                    repository="pallets/flask",
                    file_path="src/flask/app.py",
                )
            ],
            status=BenchmarkTaskStatus.APPROVED,
        )

        try:
            yield {
                "res_dir": res_dir,
                "logger_a": logger_a,
                "logger_b": logger_b,
                "rag_pipeline": rag_pipeline,
                "evaluator_suite": evaluator_suite,
                "tasks": [task],
            }
        finally:
            logger_a.close()
            logger_b.close()


def test_baseline_a_runner_execution(test_experiment_environment):
    env = test_experiment_environment
    cfg = ExperimentConfig(
        experiment_id="test_exp_a",
        experiment_name="Baseline A Test",
        experiment_type=ExperimentType.BASELINE,
        baseline_id=BaselineID.BASELINE_A,
        model_provider="mock",
        model_id="gpt-4o-mini",
        tasks_count=1,
    )

    runner = BaselineARunner(
        config=cfg,
        exp_logger=env["logger_a"],
        tasks=env["tasks"],
        rag_pipeline=env["rag_pipeline"],
        evaluator_suite=env["evaluator_suite"],
    )

    results = runner.run()
    assert len(results) == 1
    res = results[0]
    assert res.task_id == "eih-test-001"
    assert res.quality is not None
    assert res.efficiency is not None
    assert res.efficiency.num_chunks_retrieved == 0
    assert res.outcome is not None

    # Verify JSONL log was written
    events_path = env["res_dir"] / "test_exp_a" / "events.jsonl"
    assert events_path.exists()
    content = events_path.read_text(encoding="utf-8")
    assert "experiment_start" in content
    assert "task_result" in content
    assert "experiment_end" in content


def test_baseline_b_runner_execution(test_experiment_environment):
    env = test_experiment_environment
    cfg = ExperimentConfig(
        experiment_id="test_exp_b",
        experiment_name="Baseline B Test",
        experiment_type=ExperimentType.BASELINE,
        baseline_id=BaselineID.BASELINE_B,
        model_provider="mock",
        model_id="gpt-4o-mini",
        tasks_count=1,
    )

    runner = BaselineBRunner(
        config=cfg,
        exp_logger=env["logger_b"],
        tasks=env["tasks"],
        rag_pipeline=env["rag_pipeline"],
        evaluator_suite=env["evaluator_suite"],
    )

    results = runner.run()
    assert len(results) == 1
    res = results[0]
    assert res.task_id == "eih-test-001"
    assert res.quality is not None
    assert res.efficiency is not None
    assert res.efficiency.num_chunks_retrieved > 0
    assert res.outcome is not None
