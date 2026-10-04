"""
Engineering Intelligence Hub — LLM provider factory
===================================================
The single place providers are constructed.

There is deliberately NO silent fallback: an experiment that asks for the
default provider gets the real local Ollama, and if Ollama is down the call
fails loudly. The mock provider is returned only when explicitly requested
("mock"), which only unit tests do. Before this factory existed, pipelines
built without a provider silently used MockLLMProvider whenever no OpenAI key
was set, so a run could produce canned answers that looked like results.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from core.config import PROJECT_ROOT, settings
from generation.base import BaseLLMProvider

MODELS_YAML = PROJECT_ROOT / "configs" / "models.yaml"


def local_model_options(models_yaml: Path = MODELS_YAML) -> Dict[str, Dict[str, Any]]:
    """Per-model Ollama options from configs/models.yaml (e.g. num_gpu for the 7B)."""
    from routing.registry import ModelRegistry

    registry = ModelRegistry.from_yaml(str(models_yaml))
    return {
        p.model_id: dict((p.extra or {}).get("ollama_options") or {})
        for p in registry.list_all()
        if p.provider == "local"
    }


def build_provider(name: Optional[str] = None) -> BaseLLMProvider:
    """Construct the named provider (default: settings.model.default_provider)."""
    name = (name or settings.model.default_provider).strip().lower()
    if name == "ollama":
        from generation.providers.ollama import OllamaProvider

        return OllamaProvider(model_options=local_model_options())
    if name == "openai":
        from generation.providers.openai import OpenAIProvider

        return OpenAIProvider()
    if name == "mock":
        from generation.providers.openai import MockLLMProvider

        return MockLLMProvider()
    raise ValueError(f"Unknown LLM provider '{name}'. Use one of: ollama, openai, mock.")
