"""
Engineering Intelligence Hub — OpenAI LLM Provider
===================================================
Concrete implementation of BaseLLMProvider backed by the OpenAI API.
Also provides a MockLLMProvider for offline unit testing.
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional

import openai

from core.config import settings
from core.exceptions import (
    GenerationError,
    ProviderAuthenticationError,
    ProviderRateLimitError,
    ProviderTimeoutError,
)
from core.logging import get_logger
from generation.base import BaseLLMProvider, GenerationRequest, GenerationResponse

logger = get_logger(__name__)


class OpenAIProvider(BaseLLMProvider):
    """
    OpenAI API provider for models such as gpt-4o-mini, gpt-4o, gpt-3.5-turbo.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
    ) -> None:
        self.api_key = api_key or settings.secrets.openai_api_key or os.getenv("OPENAI_API_KEY")
        self.base_url = base_url
        self.timeout_seconds = timeout_seconds or settings.model.request_timeout_seconds
        self._client: Optional[openai.OpenAI] = None

    @property
    def provider_name(self) -> str:
        return "openai"

    def _get_client(self) -> openai.OpenAI:
        if self._client is None:
            if not self.api_key:
                raise ProviderAuthenticationError(
                    "OpenAI API key not configured. Set OPENAI_API_KEY environment variable.",
                    details="settings.secrets.openai_api_key is None",
                )
            self._client = openai.OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=float(self.timeout_seconds),
            )
        return self._client

    def is_available(self) -> bool:
        """Check if API key is present."""
        return bool(self.api_key)

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        """Synchronous generation using OpenAI Chat Completions."""
        client = self._get_client()

        # Build messages payload
        messages = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})

        if request.messages:
            messages.extend(request.messages)
        else:
            messages.append({"role": "user", "content": request.prompt})

        start_time = time.perf_counter()

        try:
            response = client.chat.completions.create(
                model=request.model_id,
                messages=messages,  # type: ignore[arg-type]
                max_tokens=request.max_tokens,
                temperature=request.temperature,
                stop=request.stop_sequences if request.stop_sequences else None,
                **request.extra_params,
            )
        except openai.AuthenticationError as e:
            raise ProviderAuthenticationError(f"OpenAI authentication failed: {e}") from e
        except openai.RateLimitError as e:
            raise ProviderRateLimitError(f"OpenAI rate limit exceeded: {e}") from e
        except openai.APITimeoutError as e:
            raise ProviderTimeoutError(f"OpenAI request timed out: {e}") from e
        except openai.APIError as e:
            raise GenerationError(f"OpenAI API error: {e}") from e
        except Exception as e:
            raise GenerationError(f"Unexpected generation error: {e}") from e

        latency_ms = (time.perf_counter() - start_time) * 1000.0

        choice = response.choices[0]
        text_output = choice.message.content or ""
        finish_reason = choice.finish_reason or "stop"

        input_tokens = response.usage.prompt_tokens if response.usage else len(request.prompt) // 4
        output_tokens = response.usage.completion_tokens if response.usage else len(text_output) // 4

        return GenerationResponse(
            text=text_output,
            model_id=request.model_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=round(latency_ms, 2),
            finish_reason=finish_reason,
            raw_response=response,
            extra={
                "provider": "openai",
                "system_fingerprint": response.system_fingerprint if hasattr(response, "system_fingerprint") else None,
            },
        )

    def list_available_models(self) -> List[str]:
        return ["gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo"]


class MockLLMProvider(BaseLLMProvider):
    """
    Deterministic Mock LLM Provider for hermetic testing and offline validation.
    """

    def __init__(self, canned_response: Optional[str] = None) -> None:
        self.canned_response = canned_response
        self.call_history: List[GenerationRequest] = []

    @property
    def provider_name(self) -> str:
        return "mock"

    def is_available(self) -> bool:
        return True

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        self.call_history.append(request)
        time.sleep(0.01)  # Simulate 10ms latency

        if self.canned_response is not None:
            text = self.canned_response
        elif "INSUFFICIENT EVIDENCE" in request.prompt or "missing" in request.prompt.lower():
            text = "INSUFFICIENT EVIDENCE: The provided repository context does not contain sufficient information to answer this question."
        elif "Flask" in request.prompt or "flask" in request.prompt.lower():
            text = (
                "SUPPORTED BY EVIDENCE:\n"
                "In Flask, routing is handled by the `route` decorator in `src/flask/app.py` "
                "which delegates to `add_url_rule` on the Flask application instance."
            )
        else:
            text = f"SUPPORTED BY EVIDENCE: Grounded response for prompt: {request.prompt[:50]}..."

        in_tokens = max(1, len(request.prompt) // 4)
        out_tokens = max(1, len(text) // 4)

        return GenerationResponse(
            text=text,
            model_id=request.model_id,
            input_tokens=in_tokens,
            output_tokens=out_tokens,
            latency_ms=10.0,
            finish_reason="stop",
            extra={"provider": "mock"},
        )
