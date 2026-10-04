"""
Tests for OllamaProvider.

Unit tests run against a fake Ollama server (httpx.MockTransport) and a fake
energy meter, so they need no GPU. One live integration test talks to the real
local Ollama and is skipped, with the reason shown, when Ollama or the model is
unavailable.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, Dict, List

import httpx
import pytest

from core.exceptions import GenerationError
from generation.base import GenerationRequest
from generation.providers.ollama import ContextOverflowError, OllamaProvider

DIGEST = "d7372fd828518a4d38b1eb196c673c31a85f2ed302b3d1e406c4c2d1b64a0668"
MODEL = "qwen2.5-coder:1.5b"


class FakeOllama:
    """Minimal stateful stand-in for the Ollama HTTP API."""

    def __init__(self, known=(MODEL, "qwen2.5-coder:7b")) -> None:
        self.known = set(known)
        self.loaded: set = set()
        self.requests: List[Dict[str, Any]] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        body = json.loads(request.content) if request.content else {}
        self.requests.append({"path": path, "body": body})
        if path == "/api/version":
            return httpx.Response(200, json={"version": "0.35.1"})
        if path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": m, "digest": DIGEST if m == MODEL else "x" * 64}
                                                        for m in sorted(self.known)]})
        if path == "/api/ps":
            return httpx.Response(200, json={"models": [{"name": m, "size": 1000, "size_vram": 1000,
                                                         "context_length": 4096} for m in self.loaded]})
        if body.get("model") not in self.known:
            return httpx.Response(404, json={"error": "model not found"})
        if path == "/api/generate":
            if body.get("keep_alive") == 0:
                self.loaded.discard(body["model"])
            else:
                self.loaded.add(body["model"])
            return httpx.Response(200, json={"done": True, "load_duration": 2_500_000_000})
        if path == "/api/chat":
            self.loaded.add(body["model"])
            return httpx.Response(200, json={
                "message": {"role": "assistant", "content": f"answer from {body['model']}"},
                "done": True, "done_reason": "stop",
                "prompt_eval_count": 120, "prompt_eval_duration": 40_000_000,
                "eval_count": 64, "eval_duration": 500_000_000, "load_duration": 0,
            })
        return httpx.Response(404)


class FakeMeter:
    def __init__(self, energy_j=12.5, duration_s=1.6):
        self.result = SimpleNamespace(energy_j=energy_j, duration_s=duration_s,
                                      to_dict=lambda: {"energy_j": energy_j, "duration_s": duration_s,
                                                       "method": "nvml_energy_counter"})

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeCounter:
    def __init__(self, n=120):
        self.n = n

    def count(self, model_id, messages):
        return self.n


def make(fake: FakeOllama, **kw) -> OllamaProvider:
    kw.setdefault("meter_factory", lambda: FakeMeter())
    kw.setdefault("token_counter", FakeCounter())
    return OllamaProvider(base_url="http://ollama.test", transport=httpx.MockTransport(fake.handler), **kw)


def req(model=MODEL, **kw) -> GenerationRequest:
    kw.setdefault("temperature", 0.0)
    return GenerationRequest(prompt="Explain Flask app context.", model_id=model, max_tokens=128, **kw)


def chat_bodies(fake: FakeOllama) -> List[Dict[str, Any]]:
    return [r["body"] for r in fake.requests if r["path"] == "/api/chat"]


def test_sends_deterministic_options_and_model_specific_overrides():
    fake = FakeOllama()
    p = make(fake, model_options={"qwen2.5-coder:7b": {"num_gpu": 999}})
    p.generate(req(system_prompt="sys"))
    p.generate(req(model="qwen2.5-coder:7b"))
    small, large = chat_bodies(fake)
    assert small["options"] == {"temperature": 0.0, "seed": 42, "num_predict": 128, "num_ctx": 4096}
    assert large["options"]["num_gpu"] == 999
    assert small["messages"][0] == {"role": "system", "content": "sys"}


def test_exact_tokens_latency_and_rates_come_from_ollama():
    r = make(FakeOllama()).generate(req())
    assert (r.input_tokens, r.output_tokens) == (120, 64)
    assert r.finish_reason == "stop" and r.text == f"answer from {MODEL}"
    assert r.extra["decode_tokens_per_s"] == pytest.approx(128.0)
    assert r.extra["prefill_tokens_per_s"] == pytest.approx(3000.0)
    assert r.latency_ms > 0


def test_cold_start_is_measured_separately_then_calls_are_warm():
    fake = FakeOllama()
    p = make(fake)
    first, second = p.generate(req()), p.generate(req())
    assert first.extra["cold_start"]["ollama_load_ms"] == pytest.approx(2500.0)
    assert first.extra["cold_start"]["energy"]["energy_j"] == 12.5
    assert second.extra["cold_start"] is None
    loads = [r for r in fake.requests if r["path"] == "/api/generate"]
    assert len(loads) == 1 and loads[0]["body"]["prompt"] == ""
    assert [c["cold_start"] for c in p.call_log] == [True, False]


def test_energy_measured_cost_derived_and_digest_recorded():
    r = make(FakeOllama()).generate(req())
    assert r.extra["energy_joules"] == 12.5
    assert r.extra["energy_reliability"] == "ok"
    assert r.extra["measurement_tiers"]["energy_joules"] == "MEASURED"
    assert r.extra["cost_usd"] == 0.0 and r.extra["measurement_tiers"]["cost_usd"] == "DERIVED"
    assert r.extra["model_digest"] == DIGEST


def test_short_energy_window_is_flagged():
    r = make(FakeOllama(), meter_factory=lambda: FakeMeter(energy_j=0.4, duration_s=0.3)).generate(req())
    assert r.extra["energy_reliability"] == "low_short_window"


def test_energy_unavailable_is_never_guessed():
    r = make(FakeOllama(), measure_energy=False).generate(req())
    assert r.extra["energy_joules"] is None
    assert r.extra["measurement_tiers"]["energy_joules"] == "UNAVAILABLE"


def test_missing_model_explains_how_to_pull():
    with pytest.raises(GenerationError, match="ollama pull qwen2.5-coder:99b"):
        make(FakeOllama()).generate(req(model="qwen2.5-coder:99b"))


def test_unreachable_server_is_reported_not_hidden():
    def down(request):
        raise httpx.ConnectError("refused", request=request)

    p = OllamaProvider(base_url="http://ollama.test", transport=httpx.MockTransport(down),
                       meter_factory=lambda: FakeMeter(), token_counter=FakeCounter())
    assert p.is_available() is False
    with pytest.raises(GenerationError, match="Cannot reach Ollama"):
        p.generate(req())


def test_prompt_that_would_be_truncated_is_refused_before_sending():
    fake = FakeOllama()
    p = make(fake, token_counter=FakeCounter(n=4000))  # 4000 + 128 > num_ctx 4096
    with pytest.raises(ContextOverflowError, match="silently truncate"):
        p.generate(req())
    assert chat_bodies(fake) == [], "nothing may be sent to Ollama"


def test_context_check_is_recorded_and_flags_unknown_tokenizers():
    r = make(FakeOllama()).generate(req())
    assert r.extra["context_check"] == {"prompt_tokens": 120, "num_ctx": 4096, "checked": True,
                                        "headroom_tokens": 4096 - 120 - 128}
    r2 = make(FakeOllama(), token_counter=FakeCounter(n=None)).generate(req())
    assert r2.extra["context_check"]["checked"] is False


# ---------------------------------------------------------------- live
def _live_skip_reason() -> str:
    p = OllamaProvider(measure_energy=False)
    if not p.is_available():
        return f"Ollama is not reachable at {p.base_url} (start the Ollama app)"
    if MODEL not in p.list_available_models():
        return f"{MODEL} is not pulled (run: ollama pull {MODEL})"
    return ""


@pytest.mark.integration
def test_live_ollama_is_deterministic_and_pinned():
    reason = _live_skip_reason()
    if reason:
        pytest.skip(reason)
    p = OllamaProvider()
    request = GenerationRequest(prompt="Reply with the single word: pong", model_id=MODEL,
                                max_tokens=8, temperature=0.0)
    a, b = p.generate(request), p.generate(request)
    assert a.text == b.text, "temperature 0 + fixed seed must reproduce the same output"
    assert a.input_tokens > 0 and a.output_tokens > 0
    assert a.extra["model_digest"] == DIGEST, "model changed: re-pin the digest in CLAUDE.md"
    assert b.extra["cold_start"] is None
    assert a.extra["context_check"]["prompt_tokens"] == a.input_tokens,         "pre-send token count must equal what Ollama evaluated"
