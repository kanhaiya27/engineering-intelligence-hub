"""
Engineering Intelligence Hub — Ollama (local) LLM Provider
==========================================================
Runs the local model ladder (Qwen2.5-Coder 1.5B / 3B / 7B) through Ollama's HTTP
API and returns, for every call:

  * exact token counts from Ollama's tokenizer (prompt_eval_count / eval_count)
  * wall-clock latency of the generation itself, with any model load reported
    separately (cold start is never billed to the query)
  * GPU energy for the generation, MEASURED with the NVML energy counter
    (read at start and end only; see sustainability/energy/nvml_meter.py)
  * monetary cost 0.0, DERIVED (local inference has no per-token price)
  * the sha256 digest of the model that answered

Determinism: temperature 0 and a fixed seed are sent on every call unless the
request overrides them. Ollama options (num_ctx, num_gpu, ...) can be set per
model via `model_options`.

Cold vs warm: if the model is not resident (`/api/ps`), the provider first loads
it with an empty request and measures that load as a separate cold-start record
(`extra["cold_start"]`). The measured generation that follows is therefore a
warm call.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional

import httpx

from core.config import settings
from core.exceptions import GenerationError, ProviderTimeoutError
from core.inference import inference_config
from core.logging import get_logger
from generation.base import BaseLLMProvider, GenerationRequest, GenerationResponse
from generation.tokens import ChatTokenCounter
from sustainability.energy.nvml_meter import NvmlEnergyMeter

logger = get_logger(__name__)

DEFAULT_BASE_URL = "http://localhost:11434"
# From configs/inference.yaml (single source of truth); kept as module names
# because tests, scripts and the manifest import them.
DEFAULT_SEED = inference_config().seed
# One context window for every model and system, so Systems A-E differ only in
# what they retrieve. 12,288 holds the p99 prompt of the widest escalation rung
# (~9K tokens) plus the 1,024-token output budget, and the 7B stays fully on the
# 6 GB GPU at ~35 tok/s; at 16K VRAM is full and from 20K the driver spills to
# system RAM (5-7x slower). Measured: experiments/results/phase1/machine_A/
# long_context_sizes.md and long_context_probe.md.
DEFAULT_NUM_CTX = inference_config().num_ctx
# The NVML energy counter advances in ~100 ms steps on the dev laptop, so energy
# for windows shorter than this is flagged as low reliability.
MIN_RELIABLE_ENERGY_WINDOW_S = 1.0


class ContextOverflowError(GenerationError):
    """The prompt plus the output budget does not fit the model's context window.

    Raised instead of sending: Ollama would silently truncate the prompt and the
    model would answer from cut-off evidence.
    """


class OllamaProvider(BaseLLMProvider):
    """Local LLM provider backed by an Ollama server."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        keep_alive: Optional[str] = None,
        seed: int = DEFAULT_SEED,
        num_ctx: int = DEFAULT_NUM_CTX,
        model_options: Optional[Dict[str, Dict[str, Any]]] = None,
        measure_energy: bool = True,
        transport: Optional[httpx.BaseTransport] = None,
        meter_factory: Optional[Callable[[], Any]] = None,
        token_counter: Optional[ChatTokenCounter] = None,
    ) -> None:
        self.base_url = (base_url or settings.secrets.local_model_base_url or DEFAULT_BASE_URL).rstrip("/")
        self.timeout_seconds = float(timeout_seconds or settings.model.request_timeout_seconds)
        self.keep_alive = keep_alive or inference_config().keep_alive
        self.seed = seed
        self.num_ctx = num_ctx
        self.model_options = model_options or {}
        self.measure_energy = measure_energy
        self._meter_factory = meter_factory or NvmlEnergyMeter
        self._client = httpx.Client(base_url=self.base_url, timeout=self.timeout_seconds, transport=transport)
        self.token_counter = token_counter or ChatTokenCounter()
        self._digests: Dict[str, Optional[str]] = {}
        # Every call, in order — lets tests and experiment logs prove which model ran.
        self.call_log: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------ basics
    @property
    def provider_name(self) -> str:
        return "ollama"

    def is_available(self) -> bool:
        try:
            return self._client.get("/api/version").status_code == 200
        except Exception:  # noqa: BLE001 - must not raise
            return False

    def list_available_models(self) -> List[str]:
        try:
            models = self._client.get("/api/tags").json().get("models", [])
        except Exception:  # noqa: BLE001
            return []
        for m in models:
            self._digests[m["name"]] = m.get("digest")
        return [m["name"] for m in models]

    def model_digest(self, model_id: str) -> Optional[str]:
        if model_id not in self._digests:
            self.list_available_models()
        return self._digests.get(model_id)

    def is_resident(self, model_id: str) -> bool:
        try:
            loaded = self._client.get("/api/ps").json().get("models", [])
        except Exception:  # noqa: BLE001
            return False
        return any(m.get("name") == model_id or m.get("model") == model_id for m in loaded)

    def residency(self, model_id: str) -> Optional[Dict[str, Any]]:
        """Ollama's own report of how much of the model is on the GPU."""
        try:
            for m in self._client.get("/api/ps").json().get("models", []):
                if m.get("name") == model_id or m.get("model") == model_id:
                    size, vram = m.get("size") or 0, m.get("size_vram") or 0
                    return {"size_bytes": size, "size_vram_bytes": vram,
                            "fraction_on_gpu": (vram / size) if size else None,
                            "context_length": m.get("context_length")}
        except Exception:  # noqa: BLE001
            pass
        return None

    # ------------------------------------------------------------------ options
    def _options(self, request: GenerationRequest) -> Dict[str, Any]:
        opts: Dict[str, Any] = {
            "temperature": request.temperature,
            "seed": self.seed,
            "num_predict": request.max_tokens,
            "num_ctx": self.num_ctx,
        }
        opts.update(self.model_options.get(request.model_id, {}))
        if request.stop_sequences:
            opts["stop"] = list(request.stop_sequences)
        opts.update(request.extra_params.get("options", {}))
        return opts

    def _measure(self, fn: Callable[[], httpx.Response]):
        if not self.measure_energy:
            return fn(), None
        meter = self._meter_factory()
        with meter:
            response = fn()
        return response, meter.result

    # ------------------------------------------------------------------ calls
    def _post(self, path: str, body: Dict[str, Any]) -> httpx.Response:
        try:
            resp = self._client.post(path, json=body)
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(f"Ollama request timed out after {self.timeout_seconds}s: {exc}") from exc
        except httpx.HTTPError as exc:
            raise GenerationError(f"Cannot reach Ollama at {self.base_url}: {exc}") from exc
        if resp.status_code == 404:
            raise GenerationError(
                f"Ollama model not found: {body.get('model')}. Pull it with `ollama pull {body.get('model')}`."
            )
        if resp.status_code != 200:
            raise GenerationError(f"Ollama error {resp.status_code}: {resp.text[:300]}")
        return resp

    def load(self, model_id: str, options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Load a model into memory (empty request) and measure it as a cold start."""
        body = {"model": model_id, "prompt": "", "keep_alive": self.keep_alive, "stream": False}
        if options:
            body["options"] = options
        t0 = time.perf_counter()
        resp, energy = self._measure(lambda: self._post("/api/generate", body))
        wall_ms = (time.perf_counter() - t0) * 1000.0
        data = resp.json()
        return {
            "wall_ms": round(wall_ms, 2),
            "ollama_load_ms": round((data.get("load_duration") or 0) / 1e6, 2),
            "energy": energy.to_dict() if energy else None,
            "residency": self.residency(model_id),
        }

    def check_context(self, model_id: str, messages: List[Dict[str, str]], options: Dict[str, Any]) -> Dict[str, Any]:
        """Count the prompt exactly and refuse it if prompt + output budget exceeds num_ctx."""
        num_ctx = int(options.get("num_ctx", self.num_ctx))
        budget = int(options.get("num_predict", 0) or 0)
        prompt_tokens = self.token_counter.count(model_id, messages)
        if prompt_tokens is None:
            return {"prompt_tokens": None, "num_ctx": num_ctx, "checked": False}
        if prompt_tokens + budget > num_ctx:
            raise ContextOverflowError(
                f"Prompt is {prompt_tokens} tokens + {budget} output tokens > num_ctx {num_ctx} for "
                f"{model_id}; Ollama would silently truncate it. Shorten the evidence or raise num_ctx."
            )
        return {"prompt_tokens": prompt_tokens, "num_ctx": num_ctx, "checked": True,
                "headroom_tokens": num_ctx - prompt_tokens - budget}

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        options = self._options(request)

        messages: List[Dict[str, str]] = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        messages.extend(request.messages or [{"role": "user", "content": request.prompt}])
        context_check = self.check_context(request.model_id, messages, options)

        cold_start = None
        if not self.is_resident(request.model_id):
            cold_start = self.load(request.model_id, options)
            logger.info(f"Ollama cold start for {request.model_id}: {cold_start['wall_ms']:.0f} ms")

        body = {"model": request.model_id, "messages": messages, "stream": False,
                "options": options, "keep_alive": self.keep_alive}

        t0 = time.perf_counter()
        resp, energy = self._measure(lambda: self._post("/api/chat", body))
        latency_ms = (time.perf_counter() - t0) * 1000.0
        data = resp.json()

        text = (data.get("message") or {}).get("content", "")
        in_tok = int(data.get("prompt_eval_count") or 0)
        out_tok = int(data.get("eval_count") or 0)
        eval_s = (data.get("eval_duration") or 0) / 1e9
        prompt_s = (data.get("prompt_eval_duration") or 0) / 1e9
        load_ms_inside = (data.get("load_duration") or 0) / 1e6

        energy_dict = energy.to_dict() if energy else None
        reliability = None
        if energy is not None and energy.energy_j is not None:
            reliability = "ok" if energy.duration_s >= MIN_RELIABLE_ENERGY_WINDOW_S else "low_short_window"

        extra = {
            "provider": "ollama",
            "model_digest": self.model_digest(request.model_id),
            "options": options,
            "context_check": context_check,
            "cold_start": cold_start,
            "load_ms_inside_call": round(load_ms_inside, 2),
            "decode_tokens_per_s": (out_tok / eval_s) if out_tok and eval_s else None,
            "prefill_tokens_per_s": (in_tok / prompt_s) if in_tok and prompt_s else None,
            "energy": energy_dict,
            "energy_joules": energy.energy_j if energy else None,
            "energy_reliability": reliability,
            "residency": self.residency(request.model_id),
            "cost_usd": 0.0,
            "measurement_tiers": {
                "energy_joules": "MEASURED" if energy and energy.energy_j is not None else "UNAVAILABLE",
                "cost_usd": "DERIVED",
                "tokens": "MEASURED",
                "latency_ms": "MEASURED",
            },
        }
        self.call_log.append({"model_id": request.model_id, "input_tokens": in_tok, "output_tokens": out_tok,
                              "latency_ms": round(latency_ms, 2), "cold_start": cold_start is not None})

        return GenerationResponse(
            text=text,
            model_id=request.model_id,
            input_tokens=in_tok,
            output_tokens=out_tok,
            latency_ms=round(latency_ms, 2),
            finish_reason=data.get("done_reason") or ("stop" if data.get("done") else "error"),
            raw_response=data,
            extra=extra,
        )

    def unload(self, model_id: str) -> None:
        """Release a model from memory (keep_alive 0)."""
        self._post("/api/generate", {"model": model_id, "keep_alive": 0})
