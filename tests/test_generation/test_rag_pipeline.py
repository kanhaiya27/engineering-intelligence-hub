"""
Tests for BaselineRAGPipeline
"""

import pytest

from generation.providers.openai import MockLLMProvider
from generation.rag import BaselineRAGPipeline
from knowledge.schemas.artifacts import ArtifactType, KnowledgeChunk
from knowledge.schemas.tasks import EngTaskRequest, TaskStatus
from retrieval.bm25 import BM25Retriever


@pytest.fixture
def rag_pipeline():
    chunks = [
        KnowledgeChunk(
            chunk_id="flask-route-chunk",
            artifact_id="flask-src",
            artifact_type=ArtifactType.SOURCE_CODE,
            repository="pallets/flask",
            content="def route(self, rule: str, **options):\n    return self.add_url_rule(rule, endpoint, f, **options)",
            chunk_index=0,
            metadata={"symbol_name": "Flask.route", "file_path": "src/flask/app.py", "start_line": 10, "end_line": 20},
        )
    ]
    retriever = BM25Retriever(chunks=chunks)
    provider = MockLLMProvider()
    return BaselineRAGPipeline(retriever=retriever, llm_provider=provider)


def test_baseline_rag_pipeline_execution(rag_pipeline):
    req = EngTaskRequest(
        task_id="test-task-1",
        query="How does the route decorator work in Flask?",
        repository="pallets/flask",
    )
    resp = rag_pipeline.execute(req)

    assert resp.task_id == "test-task-1"
    assert resp.status == TaskStatus.COMPLETED
    assert resp.answer is not None
    assert "SUPPORTED BY EVIDENCE" in resp.answer
    assert resp.retrieval is not None
    assert resp.retrieval.total_retrieved > 0
    assert resp.energy_joules is not None
    assert resp.cost_usd is not None
    assert resp.co2e_grams is not None


def test_baseline_rag_skip_retrieval_baseline_a(rag_pipeline):
    req = EngTaskRequest(
        task_id="test-task-2",
        query="Explain Python generators",
    )
    resp = rag_pipeline.execute(req, skip_retrieval=True)

    assert resp.task_id == "test-task-2"
    assert resp.retrieval is None
    assert resp.answer is not None
