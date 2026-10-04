"""
Contract tests for the frozen v1 pipeline-trace interface (docs/API_CONTRACT.md).

The snapshot test fails whenever the contract models, or any domain enum they
re-use (TaskType, SignalType, RetrievalMode, ...), change. That is deliberate:
contract changes need a PR reviewed by both laptops.
"""

from __future__ import annotations

import json

import pytest
from pydantic import TypeAdapter, ValidationError

from apps.api.contract import openapi
from apps.api.contract.examples import (
    EXAMPLES_DIR,
    ILLUSTRATIVE_WARNING,
    example_trace_system_e,
)
from apps.api.contract.v1 import (
    CONTRACT_VERSION,
    ErrorResponse,
    Metric,
    PipelineTrace,
    TraceEvent,
    TraceRequest,
)


def _dump() -> dict:
    return example_trace_system_e().model_dump(mode="json")


def _invalid(payload: dict, match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        PipelineTrace.model_validate(payload)


# --- Snapshot -----------------------------------------------------------------


def test_committed_openapi_export_matches_models():
    committed = openapi.EXPORT_PATH.read_text(encoding="utf-8")
    assert committed == openapi.render(), (
        "docs/api/openapi-v1.json is stale. Contract changes need a PR reviewed by "
        "both sides; regenerate with: python -m apps.api.contract.openapi"
    )


def test_openapi_declares_contract_endpoints_and_errors():
    doc = openapi.build_openapi()
    assert doc["info"]["version"] == CONTRACT_VERSION
    assert set(doc["paths"]) == {"/v1/trace", "/v1/trace/stream"}
    stream = doc["paths"]["/v1/trace/stream"]["post"]["responses"]["200"]["content"]
    assert list(stream) == ["text/event-stream"]
    for path in doc["paths"].values():
        for code in ("400", "413", "422", "429", "503"):
            ref = path["post"]["responses"][code]["content"]["application/json"]["schema"]
            assert ref["$ref"].endswith("/ErrorResponse")
    assert "HTTPValidationError" not in doc["components"]["schemas"]


def test_committed_example_matches_builder_and_validates():
    committed = (EXAMPLES_DIR / "trace-v1-system-e.json").read_text(encoding="utf-8")
    trace = PipelineTrace.model_validate_json(committed)
    assert trace == example_trace_system_e()


# --- Example semantics ----------------------------------------------------------


def test_example_is_labelled_and_never_evidence():
    trace = example_trace_system_e()
    assert ILLUSTRATIVE_WARNING in trace.warnings
    assert trace.execution.generation_source.value == "mock"
    assert trace.execution.research_evidence is False


def test_example_json_round_trip():
    trace = example_trace_system_e()
    assert PipelineTrace.model_validate_json(trace.model_dump_json()) == trace


# --- Metric / provenance ---------------------------------------------------------


def test_metric_requires_provenance_when_available():
    with pytest.raises(ValidationError, match="provenance tier"):
        Metric(value=1.0, unit="ms", provenance=None, method="perf_counter")


def test_unavailable_metric_cannot_carry_tier():
    with pytest.raises(ValidationError, match="unavailable metric"):
        Metric(value=None, unit="ms", provenance="MEASURED", method="perf_counter")


def test_unknown_provenance_tier_rejected():
    with pytest.raises(ValidationError):
        Metric(value=1.0, unit="ms", provenance="GUESSED", method="perf_counter")


# --- Trace invariants -------------------------------------------------------------


def test_mock_output_cannot_be_research_evidence():
    p = _dump()
    p["execution"]["research_evidence"] = True
    _invalid(p, "never be research evidence")


def test_cached_run_requires_cached_from():
    p = _dump()
    p["execution"]["generation_source"] = "cached_run"
    _invalid(p, "cached_from")


@pytest.mark.parametrize(
    "path",
    [
        "/home/user/.corpus_cache/flask/app.py",
        "C:/Users/x/app.py",
        "C:\\Users\\x\\app.py",
        "src\\flask\\app.py",
        "../secrets/app.py",
        "~/app.py",
    ],
)
def test_citation_paths_must_be_repo_relative(path):
    p = _dump()
    p["attempts"][0]["retrieval"]["chunks"][0]["file_path"] = path
    _invalid(p, "repo-relative")


def test_citation_must_match_file_and_lines():
    p = _dump()
    p["attempts"][0]["retrieval"]["chunks"][0]["citation"] = "example/repo:wrong.py:1-2"
    _invalid(p, "citation must be")


def test_reversed_line_range_rejected():
    p = _dump()
    chunk = p["attempts"][0]["retrieval"]["chunks"][0]
    chunk["start_line"], chunk["end_line"] = 20, 10
    _invalid(p, "end_line must be")


def test_channel_cannot_execute_unless_requested():
    p = _dump()
    p["attempts"][0]["retrieval"]["reranker"]["executed"] = True
    _invalid(p, "without being requested")


def test_strategy_fallback_flag_must_be_truthful():
    p = _dump()
    p["attempts"][1]["retrieval"]["strategy_name"] = "hybrid"  # silent fallback
    _invalid(p, "strategy_fallback must equal")
    p["attempts"][1]["retrieval"]["strategy_fallback"] = True
    PipelineTrace.model_validate(p)


def test_extra_fields_are_rejected():
    p = _dump()
    p["attempts"][0]["retrieval"]["chunks"][0]["metadata"] = {"local_path": "D:/x"}
    _invalid(p, "Extra inputs are not permitted")


def test_attempt_indices_must_be_contiguous():
    p = _dump()
    p["attempts"].pop(0)
    _invalid(p, "attempt indices")


def test_verified_requires_passing_gate_on_last_attempt():
    p = _dump()
    p["attempts"][-1]["verification"]["passed"] = False
    _invalid(p, "VERIFIED requires")


def test_insufficient_evidence_requires_exhausted_escalation():
    p = _dump()
    p["outcome"]["verdict"] = "INSUFFICIENT_EVIDENCE"
    p["attempts"][-1]["verification"]["passed"] = False
    _invalid(p, "INSUFFICIENT_EVIDENCE requires")


def test_gate_only_runs_for_system_e():
    p = _dump()
    p["system"] = "D"
    _invalid(p, "only system E")


def test_system_a_performs_no_retrieval():
    p = _dump()
    p["system"] = "A"
    _invalid(p, "system A performs no retrieval")


def test_escalation_steps_must_match_attempts():
    p = _dump()
    p["escalation"]["steps"] = []
    _invalid(p, "exactly one escalation step")


# --- Request, error and stream bodies ---------------------------------------------


def test_request_limits_and_defaults():
    assert TraceRequest(query="why?").system.value == "E"
    with pytest.raises(ValidationError):
        TraceRequest(query="x" * 2001)
    with pytest.raises(ValidationError):
        TraceRequest(query="ok query", repository="../../etc")
    with pytest.raises(ValidationError):
        TraceRequest(query="ok query", experiment_mode="system_d")


def test_error_response_shape():
    body = ErrorResponse(
        request_id="r1", error={"code": "rate_limited", "message": "slow down", "retry_after_s": 5}
    )
    assert body.contract_version == CONTRACT_VERSION


def test_trace_events_discriminate_on_event_name():
    adapter = TypeAdapter(TraceEvent)
    trace = example_trace_system_e()
    completed = adapter.validate_python(
        {"trace_id": trace.trace_id, "seq": 9, "event": "trace.completed",
         "payload": trace.model_dump(mode="json")}
    )
    assert completed.payload == trace
    delta = adapter.validate_python(
        {"trace_id": trace.trace_id, "seq": 3, "event": "generation.delta",
         "payload": {"attempt_index": 0, "text": "tok"}}
    )
    assert delta.payload.text == "tok"
    with pytest.raises(ValidationError):
        adapter.validate_python(
            {"trace_id": "t", "seq": 0, "event": "unknown", "payload": {}}
        )


def test_example_contains_no_absolute_paths():
    text = json.dumps(_dump())
    for marker in ("D:\\\\", "C:\\\\", "/home/", "/Users/", ".corpus_cache", "EIH_share"):
        assert marker not in text
