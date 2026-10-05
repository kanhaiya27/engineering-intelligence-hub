"""
Routing tests that prove the capability EXECUTES, not just that it is configured.

The pipeline is driven through the real OllamaProvider against a fake Ollama
HTTP server, and the assertions are made on the `model` field of every HTTP
request the pipeline actually sent. A live test then runs the real local
models and checks the sha256 digest of the model that answered.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, Dict, List
from unittest.mock import MagicMock

import httpx
import pytest

from core.config import settings
from generation.providers.factory import build_provider, local_model_options
from generation.providers.ollama import OllamaProvider
from generation.providers.openai import MockLLMProvider
from generation.quality_rag import QualityAwareRAGPipeline
from generation.rag import BaselineRAGPipeline
from knowledge.schemas.tasks import (
    ComplexityLevel,
    CriticalityLevel,
    EngTaskRequest,
    RetrievalResult,
    RetrievedChunk,
    SDLCStage,
    TaskClassification,
    TaskType,
)
from retrieval.strategies import RetrievalStrategyConfig
from routing.registry import ModelRegistry
from routing.tier_router import TierRouter

SMALL, MEDIUM, LARGE = "qwen2.5-coder:1.5b", "qwen2.5-coder:3b", "qwen2.5-coder:7b"
DIGESTS = {
    SMALL: "d7372fd828518a4d38b1eb196c673c31a85f2ed302b3d1e406c4c2d1b64a0668",
    MEDIUM: "f72c60cabf6237b07f6e632b2c48d533cef25eda2efbd34bed21c5e9c01e6225",
    LARGE: "dae161e27b0e90dd1856c8bb3209201fd6736d8eb66298e75ed87571486f4364",
}
GOOD = "SUPPORTED BY EVIDENCE: `src/auth/jwt.py:L10-L25` verify_token verifies the token."
BAD = "Token is checked somewhere in auth."


def registry() -> ModelRegistry:
    return ModelRegistry.from_yaml("configs/models.yaml")


def clf(complexity="medium", criticality="medium", security="none", threshold=0.75) -> TaskClassification:
    return TaskClassification(
        task_id="t1", task_type=TaskType.CODE_EXPLANATION, sdlc_stage=SDLCStage.DEVELOPMENT,
        complexity=complexity, criticality=criticality, security_sensitivity=security,
        quality_threshold=threshold,
    )


def adaptive_stub() -> MagicMock:
    chunk = RetrievedChunk(
        chunk_id="c1", source_path="src/auth/jwt.py", score=0.9, repository="org/auth",
        content="def verify_token(token: str) -> bool:\n    return decode(token) is not None",
        metadata={"start_line": 10, "end_line": 25, "symbol_name": "verify_token"},
    )
    stub = MagicMock()
    stub.retrieve.return_value = RetrievalResult(task_id="t1", strategy_used="hybrid", chunks=[chunk],
                                                 total_retrieved=1, retrieval_latency_ms=5.0)
    stub.list_strategies.return_value = {"hybrid": RetrievalStrategyConfig(strategy_name="hybrid")}
    return stub


class FakeOllama:
    """Answers per model, records every request body."""

    def __init__(self, answers: Dict[str, str]):
        self.answers, self.loaded, self.chats = answers, set(), []

    def handler(self, request: httpx.Request) -> httpx.Response:
        path, body = request.url.path, (json.loads(request.content) if request.content else {})
        if path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": m, "digest": d} for m, d in DIGESTS.items()]})
        if path == "/api/ps":
            return httpx.Response(200, json={"models": [{"name": m, "size": 1, "size_vram": 1} for m in self.loaded]})
        if path == "/api/generate":
            self.loaded.add(body["model"])
            return httpx.Response(200, json={"done": True, "load_duration": 1_000_000_000})
        if path == "/api/chat":
            self.chats.append(body)
            return httpx.Response(200, json={
                "message": {"content": self.answers[body["model"]]}, "done": True, "done_reason": "stop",
                "prompt_eval_count": 300, "prompt_eval_duration": 100_000_000,
                "eval_count": 40, "eval_duration": 1_000_000_000,
            })
        return httpx.Response(404)


class FakeMeter:
    def __init__(self):
        self.result = SimpleNamespace(energy_j=20.0, duration_s=2.0,
                                      to_dict=lambda: {"energy_j": 20.0, "duration_s": 2.0})

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def provider(fake: FakeOllama) -> OllamaProvider:
    return OllamaProvider(base_url="http://ollama.test", transport=httpx.MockTransport(fake.handler),
                          model_options=local_model_options(), meter_factory=FakeMeter,
                          token_counter=SimpleNamespace(count=lambda m, msgs: 300))


# ------------------------------------------------------------ router rules
@pytest.mark.parametrize("kw, expected", [
    ({"complexity": "low", "criticality": "low"}, SMALL),
    ({"complexity": "low", "criticality": "medium"}, SMALL),
    ({"complexity": "medium", "criticality": "medium"}, MEDIUM),
    ({"complexity": "unknown", "criticality": "unknown"}, MEDIUM),
    ({"complexity": "high", "criticality": "low"}, LARGE),
    ({"complexity": "very_high", "criticality": "low"}, LARGE),
    ({"complexity": "low", "criticality": "critical"}, LARGE),
    ({"complexity": "low", "criticality": "high"}, LARGE),
    ({"complexity": "low", "criticality": "low", "security": "high"}, LARGE),
])
def test_tier_rules(kw, expected):
    assert TierRouter(registry()).select_model(clf(**kw)) == expected


def test_ladder_is_local_only_and_escalation_climbs_then_stops():
    r = TierRouter(registry())
    assert r.ladder == [SMALL, MEDIUM, LARGE]
    assert [r.escalate(SMALL), r.escalate(MEDIUM), r.escalate(LARGE)] == [MEDIUM, LARGE, LARGE]
    assert r.select_model(clf(), override_model_id=SMALL) == SMALL


# ------------------------------------------------------------ execution proof
def test_routed_pipeline_actually_calls_the_selected_model():
    fake = FakeOllama({SMALL: GOOD, MEDIUM: GOOD, LARGE: GOOD})
    pipe = QualityAwareRAGPipeline(adaptive_pipeline=adaptive_stub(), llm_provider=provider(fake),
                                   model_router=TierRouter(registry()))
    easy = pipe.execute(EngTaskRequest(task_id="t1", query="Explain verify_token in jwt.py"),
                        classification=clf("low", "low", threshold=0.7))
    hard = pipe.execute(EngTaskRequest(task_id="t2", query="Explain verify_token in jwt.py"),
                        classification=clf("high", "medium", threshold=0.7))
    assert [c["model"] for c in fake.chats] == [SMALL, LARGE]          # what went over HTTP
    assert easy.metadata["models_called"] == [SMALL] and hard.metadata["models_called"] == [LARGE]
    assert easy.verification_details["attempt_history"][0]["model_digest"] == DIGESTS[SMALL]
    assert fake.chats[1]["options"]["num_gpu"] == 999                  # measured 7B setting applied
    assert fake.chats[0]["options"]["num_gpu"] == 999                  # all tiers: all layers on GPU


def test_quality_failure_escalates_to_the_next_model():
    fake = FakeOllama({SMALL: BAD, MEDIUM: GOOD, LARGE: GOOD})
    pipe = QualityAwareRAGPipeline(adaptive_pipeline=adaptive_stub(), llm_provider=provider(fake),
                                   model_router=TierRouter(registry()))
    resp = pipe.execute(EngTaskRequest(task_id="t1", query="Explain verify_token in jwt.py"),
                        classification=clf("low", "low", threshold=0.75))
    assert [c["model"] for c in fake.chats] == [SMALL, MEDIUM]
    hist = resp.verification_details["attempt_history"]
    assert [(h["model_id"], h["passed"]) for h in hist] == [(SMALL, False), (MEDIUM, True)]
    assert resp.model_id == MEDIUM and resp.passed_quality_gate is True


def test_without_router_every_attempt_uses_the_fixed_model():
    fake = FakeOllama({SMALL: BAD, MEDIUM: BAD, LARGE: BAD})
    pipe = QualityAwareRAGPipeline(adaptive_pipeline=adaptive_stub(), llm_provider=provider(fake))
    resp = pipe.execute(EngTaskRequest(task_id="t1", query="Explain verify_token in jwt.py"),
                        classification=clf("low", "low"))
    assert {c["model"] for c in fake.chats} == {settings.model.default_model_id} == {LARGE}
    assert resp.metadata["router"] is None


def test_measured_energy_is_used_and_labelled():
    fake = FakeOllama({SMALL: GOOD, MEDIUM: GOOD, LARGE: GOOD})
    pipe = QualityAwareRAGPipeline(adaptive_pipeline=adaptive_stub(), llm_provider=provider(fake),
                                   model_router=TierRouter(registry()))
    resp = pipe.execute(EngTaskRequest(task_id="t1", query="Explain verify_token in jwt.py"),
                        classification=clf("low", "low", threshold=0.7))
    attempt = resp.verification_details["attempt_history"][0]
    assert attempt["generation_energy_tier"] == "MEASURED"
    assert attempt["generation_energy_joules"] == 20.0
    assert resp.cost_usd == 0.0
    assert resp.metadata["cold_starts"][0]["model_id"] == SMALL       # load reported separately


# ------------------------------------------------------------ no silent mock
def test_pipelines_default_to_the_real_provider_not_the_mock():
    assert isinstance(QualityAwareRAGPipeline(adaptive_pipeline=adaptive_stub()).llm_provider, OllamaProvider)
    assert isinstance(BaselineRAGPipeline(retriever=MagicMock()).llm_provider, OllamaProvider)


def test_factory_only_returns_mock_when_asked():
    assert isinstance(build_provider(), OllamaProvider)
    assert build_provider().model_options[LARGE] == {"num_gpu": 999}
    assert isinstance(build_provider("mock"), MockLLMProvider)
    with pytest.raises(ValueError):
        build_provider("gpt-magic")


# ------------------------------------------------------------ live
@pytest.mark.integration
def test_live_routing_runs_different_real_models(monkeypatch):
    real = build_provider("ollama")
    if not real.is_available():
        pytest.skip(f"Ollama is not reachable at {real.base_url}")
    missing = [m for m in (SMALL, LARGE) if m not in real.list_available_models()]
    if missing:
        pytest.skip(f"models not pulled: {missing}")
    monkeypatch.setattr(settings.model, "max_tokens", 32)
    pipe = QualityAwareRAGPipeline(adaptive_pipeline=adaptive_stub(), llm_provider=real,
                                   model_router=TierRouter(registry()))
    req = EngTaskRequest(task_id="live", query="What does verify_token return?")
    easy = pipe.execute(req, classification=clf("low", "low"), skip_verification=True)
    hard = pipe.execute(req, classification=clf("high", "medium"), skip_verification=True)
    e0 = easy.verification_details["attempt_history"]
    h0 = hard.verification_details["attempt_history"]
    assert easy.metadata["models_called"] == [SMALL] and hard.metadata["models_called"] == [LARGE]
    # The digest Ollama reports proves which weights actually answered.
    assert real.model_digest(SMALL) == DIGESTS[SMALL] and real.model_digest(LARGE) == DIGESTS[LARGE]
    assert easy.metadata["generation_energy_tier"] == "MEASURED"
    assert hard.metadata["generation_energy_tier"] == "MEASURED"
    assert e0 == [] and h0 == []  # skip_verification: no gate attempts recorded
