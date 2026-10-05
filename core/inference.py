"""
Engineering Intelligence Hub — inference configuration loader
=============================================================
Loads `configs/inference.yaml`, the single source of truth for generation
settings (model, routing ladder, num_ctx, num_gpu, temperature, seed, output
limit) shared by Systems A–E and every routing tier. Nothing else defines
these values; everything that needs them imports `inference_config()`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

import yaml

INFERENCE_YAML = Path(__file__).resolve().parent.parent / "configs" / "inference.yaml"


@dataclass(frozen=True)
class InferenceConfig:
    provider: str
    fixed_model: str
    fallback_model: str
    routing_ladder: Dict[str, str]
    options: Dict[str, Any] = field(default_factory=dict)
    max_output_tokens: int = 1024
    keep_alive: str = "30m"

    @property
    def num_ctx(self) -> int:
        return int(self.options["num_ctx"])

    @property
    def seed(self) -> int:
        return int(self.options["seed"])

    @property
    def temperature(self) -> float:
        return float(self.options["temperature"])

    @property
    def num_gpu(self) -> int:
        return int(self.options["num_gpu"])

    def model_options(self) -> Dict[str, Dict[str, Any]]:
        """Per-model Ollama options: the same options for every model this config can call."""
        models = {self.fixed_model, self.fallback_model, *self.routing_ladder.values()}
        shared = {k: v for k, v in self.options.items() if k not in ("temperature", "seed", "num_ctx")}
        return {m: dict(shared) for m in models}


def load_inference_config(path: Path = INFERENCE_YAML) -> InferenceConfig:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    required = ("provider", "fixed_model", "fallback_model", "routing_ladder", "options")
    missing = [k for k in required if k not in data]
    if missing:
        raise ValueError(f"{path} is missing {missing}")
    for key in ("num_ctx", "num_gpu", "temperature", "seed"):
        if key not in data["options"]:
            raise ValueError(f"{path} options is missing '{key}'")
    return InferenceConfig(
        provider=data["provider"], fixed_model=data["fixed_model"], fallback_model=data["fallback_model"],
        routing_ladder=dict(data["routing_ladder"]), options=dict(data["options"]),
        max_output_tokens=int(data.get("max_output_tokens", 1024)), keep_alive=str(data.get("keep_alive", "30m")),
    )


@lru_cache(maxsize=1)
def inference_config() -> InferenceConfig:
    return load_inference_config()
