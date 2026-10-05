"""
Engineering Intelligence Hub — Abstract LLM Provider Interface
==============================================================
All concrete LLM provider implementations must inherit from BaseLLMProvider.

This abstraction ensures the rest of the system (generation, verification,
experiment framework) is completely decoupled from any specific LLM API.

Phase-0: Interface only.
Phase-1 implementations (in generation/providers/):
  - OpenAIProvider   — OpenAI / Azure OpenAI
  - AnthropicProvider — Anthropic Claude
  - GoogleProvider   — Gemini via AI Studio / Vertex
  - LocalProvider    — Ollama / vLLM (self-hosted)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, Iterator, List, Optional


@dataclass
class GenerationRequest:
    """A single generation request to an LLM provider."""

    prompt: str
    model_id: str
    system_prompt: Optional[str] = None
    messages: Optional[List[Dict[str, str]]] = None  # For chat-format providers
    max_tokens: int = 1024
    temperature: float = 0.1
    stop_sequences: List[str] = field(default_factory=list)
    stream: bool = False
    extra_params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GenerationResponse:
    """The response from an LLM provider."""

    text: str
    model_id: str
    input_tokens: int
    output_tokens: int
    latency_ms: float
    finish_reason: str  # "stop" | "length" | "content_filter" | "error"
    raw_response: Optional[Any] = None  # Provider-specific response object
    extra: Dict[str, Any] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class BaseLLMProvider(ABC):
    """
    Abstract interface for LLM providers.

    Implementors must provide synchronous generate() at minimum.
    Streaming and async methods have default implementations that raise
    NotImplementedError, allowing gradual implementation.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable provider name (e.g. 'openai', 'anthropic')."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """
        Check if the provider is reachable and credentials are valid.
        Should not raise — return False on any failure.
        """
        ...

    @abstractmethod
    def generate(self, request: GenerationRequest) -> GenerationResponse:
        """
        Synchronous text generation.

        Parameters
        ----------
        request : GenerationRequest

        Returns
        -------
        GenerationResponse

        Raises
        ------
        ProviderAuthenticationError
            On invalid API credentials.
        ProviderRateLimitError
            On rate limit responses.
        ProviderTimeoutError
            On request timeout.
        GenerationError
            On any other provider error.
        """
        ...

    async def generate_async(self, request: GenerationRequest) -> GenerationResponse:
        """
        Asynchronous text generation.
        Default implementation raises NotImplementedError.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not implement generate_async()."
        )

    def stream(self, request: GenerationRequest) -> Iterator[str]:
        """
        Synchronous streaming generation. Yields text deltas.
        Default implementation raises NotImplementedError.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not implement stream()."
        )

    async def stream_async(self, request: GenerationRequest) -> AsyncIterator[str]:
        """
        Asynchronous streaming generation.
        Default implementation raises NotImplementedError.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not implement stream_async()."
        )
        # Required to make this an async generator syntactically
        yield  # type: ignore[misc]

    def list_available_models(self) -> List[str]:
        """
        Return a list of model IDs available from this provider.
        Default: return empty list (provider may not support enumeration).
        """
        return []
