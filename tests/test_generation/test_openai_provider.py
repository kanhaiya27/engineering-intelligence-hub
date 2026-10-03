"""
Tests for OpenAIProvider and MockLLMProvider
"""

import pytest

from core.exceptions import ProviderAuthenticationError
from generation.base import GenerationRequest
from generation.providers.openai import MockLLMProvider, OpenAIProvider


def test_mock_llm_provider_generation():
    provider = MockLLMProvider()
    assert provider.is_available() is True
    assert provider.provider_name == "mock"

    req = GenerationRequest(
        prompt="Explain how routing works in Flask",
        model_id="gpt-4o-mini",
    )
    resp = provider.generate(req)

    assert resp.text is not None
    assert "SUPPORTED BY EVIDENCE" in resp.text
    assert resp.model_id == "gpt-4o-mini"
    assert resp.input_tokens > 0
    assert resp.output_tokens > 0
    assert resp.latency_ms > 0


def test_openai_provider_missing_key_raises():
    provider = OpenAIProvider(api_key="")
    assert provider.is_available() is False

    req = GenerationRequest(prompt="test", model_id="gpt-4o-mini")
    with pytest.raises(ProviderAuthenticationError):
        provider.generate(req)
