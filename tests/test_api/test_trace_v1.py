"""POST /v1/trace(/stream) against the frozen contract v1.

The mock provider is used on purpose: these tests check the contract shape and the
invariants (§3.1), and the contract itself marks mock output research_evidence=false.
Systems B-E retrieve from the live Qdrant collection (and graph for D/E): integration tests.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.api import trace_adapter
from apps.api.contract.v1 import PipelineTrace
from apps.api.main import app


@pytest.fixture
def client(monkeypatch):
    from experiments.m5.runner import M5BenchmarkRunner
    from generation.providers.openai import MockLLMProvider

    tmp = Path(tempfile.mkdtemp(prefix="eih-trace-test-"))
    r = M5BenchmarkRunner(llm_provider=MockLLMProvider(), raw_output_dir=tmp / "raw", processed_output_dir=tmp / "p")
    monkeypatch.setattr(trace_adapter, "_runner", r)
    return TestClient(app)


def _qdrant_ready() -> bool:
    try:
        from core.config import settings
        from knowledge.vector.qdrant import QdrantVectorStore
        vs = QdrantVectorStore()
        vs.connect()
        return vs.count(settings.vector_store.collection_name) > 0
    except Exception:  # noqa: BLE001
        return False


def test_system_a_trace_is_contract_valid_and_marked_mock(client):
    r = client.post("/v1/trace", json={"query": "What is a WSGI application?", "system": "A"},
                    headers={"X-Request-ID": "req-123"})
    assert r.status_code == 200 and r.headers["x-request-id"] == "req-123"
    t = PipelineTrace.model_validate(r.json())  # every invariant re-checked
    assert t.system.value == "A" and t.attempts[0].retrieval is None and t.classification is None
    assert t.execution.generation_source.value == "mock" and t.execution.research_evidence is False
    assert t.outcome.verdict.value == "UNVERIFIED" and not t.attempts[0].verification.executed
    assert t.totals.energy_cpu_joules.value is None  # not measured per attempt: null, never invented


def test_request_validation_uses_error_response(client):
    r = client.post("/v1/trace", json={"query": "ok?", "system": "E", "skip_verification": True})
    assert r.status_code == 422
    body = r.json()
    assert body["error"]["code"] == "invalid_request" and "skip_verification" in body["error"]["message"]


def test_unavailable_model_is_503(client, monkeypatch):
    monkeypatch.setattr(trace_adapter.runner().llm_provider, "is_available", lambda: False)
    r = client.post("/v1/trace", json={"query": "What is Flask?", "system": "A"})
    assert r.status_code == 503 and r.json()["error"]["code"] == "pipeline_unavailable"


@pytest.mark.integration
@pytest.mark.parametrize("system", ["B", "C", "E"])
def test_retrieval_systems_trace_live_retrieval(client, system):
    if not _qdrant_ready():
        pytest.skip("live Qdrant research collection required")
    r = client.post("/v1/trace", json={"query": "How does Flask register a URL rule for a view function?", "system": system})
    assert r.status_code == 200, r.text
    t = PipelineTrace.model_validate(r.json())
    ret = t.attempts[0].retrieval
    assert ret is not None and ret.chunks and ret.dense.executed
    assert all(c.citation.startswith(f"{c.repository}:{c.file_path}") for c in ret.chunks if c.repository and c.file_path)
    assert (t.classification is not None) == (system in "CDE")
    assert t.attempts[-1].verification.executed == (system == "E")
    if system == "E":
        assert len(t.escalation.steps) == len(t.attempts) - 1
        assert t.outcome.verdict.value in ("VERIFIED", "INSUFFICIENT_EVIDENCE")


def test_stream_event_order(client):
    with client.stream("POST", "/v1/trace/stream", json={"query": "What is a decorator?", "system": "A"}) as r:
        assert r.status_code == 200
        frames = [f for f in r.read().decode().split("\n\n") if f.strip()]
    events = [json.loads(f.split("data: ", 1)[1]) for f in frames]
    assert [e["seq"] for e in events] == list(range(len(events)))
    assert [e["event"] for e in events] == ["trace.started", "generation", "verification", "trace.completed"]
    assert len({e["trace_id"] for e in events}) == 1
    PipelineTrace.model_validate(events[-1]["payload"])
