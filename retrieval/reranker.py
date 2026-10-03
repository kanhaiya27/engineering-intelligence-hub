"""
Engineering Intelligence Hub — Cross-Encoder Reranking Stage
=============================================================
Real reranking implementation for the hybrid retrieval pipeline.

WHY THIS MODULE EXISTS
----------------------
`RetrievalStrategyConfig` has carried `enable_reranking`, `reranker_type` and
`reranker_top_n` since Phase-1, and `configs/retrieval.yaml` declares
`enable_reranking: true` for the `hybrid_reranked` and `graph_augmented_reranked`
strategies. Until this module existed, NO consumer read those fields — enabling
reranking silently produced plain fusion output. That defect corrupted two
research-critical paths:

  1. `verification/escalation.py` — the FINAL escalation rung sets
     `enable_reranking=True`. A no-op final rung means System E's most expensive
     attempt was quality-identical to the previous attempt while still paying its
     energy and latency cost, biasing the D->E ablation delta.
  2. `retrieval/policy.py` — HIGH and CRITICAL criticality tasks route to
     `*_reranked` strategies. The highest-stakes tasks silently received the
     weakest available treatment.

DESIGN CONTRACT — FAIL LOUD, NEVER SILENTLY
-------------------------------------------
A reranker that cannot run MUST NOT quietly degrade to pass-through. Every
`RerankOutcome` records `applied` and, on failure, `error`. Retrievers copy those
fields into `RetrievalResult.metadata`, so every experiment trace states plainly
whether reranking actually happened. Set `EIH_RETRIEVAL_STRICT_RERANKING=true` to
turn a load/inference failure into a raised `RetrievalError` instead.

MEASUREMENT NOTE
----------------
The cross-encoder runs LOCALLY on our own GPU, so unlike the API-hosted generator
its energy IS attributable to this system and IS measurable via NVML. Reranking is
a real energy cost traded for a real quality gain — quantifying that trade-off is
precisely the project's research question, so the outcome carries its own
measured energy and latency rather than folding invisibly into retrieval latency.

Model: cross-encoder/ms-marco-MiniLM-L-6-v2 (~22M params, 6 layers).
Chosen for a favourable quality/energy ratio on a 6 GB laptop GPU; it is the
standard MS MARCO passage-reranking baseline, which keeps the comparison legible
against published retrieval literature.
"""

from __future__ import annotations

import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from core.exceptions import RetrievalError
from core.logging import get_logger
from knowledge.schemas.tasks import RetrievedChunk
from retrieval.strategies import RerankerType, RetrievalStrategyConfig
from sustainability.energy.estimator import EnergyEstimate, EnergyEstimator

logger = get_logger(__name__)

# Default cross-encoder checkpoint. Overridable via EIH_RETRIEVAL_RERANKER_MODEL_ID.
DEFAULT_CROSS_ENCODER_MODEL_ID = "cross-encoder/ms-marco-MiniLM-L-6-v2"

# Cross-encoder inputs are truncated to this many characters per chunk before
# tokenisation. The model's own limit is 512 tokens; trimming first keeps GPU
# memory predictable on long code chunks and avoids silent tokeniser truncation
# of the query, which sits at the front of the pair.
MAX_CHUNK_CHARS_FOR_RERANK = 2000


@dataclass
class RerankOutcome:
    """
    Result of one reranking stage, including its own energy and latency cost.

    `applied` is the field that matters for research integrity: it is False
    whenever reranking did not actually run, and `error` then says why.
    """

    chunks: List[RetrievedChunk]
    applied: bool
    reranker_type: str = RerankerType.NONE.value
    model_id: Optional[str] = None
    device: Optional[str] = None
    latency_ms: float = 0.0
    candidates_in: int = 0
    returned: int = 0
    energy_joules: float = 0.0
    energy_method: Optional[str] = None
    cold_start_ms: float = 0.0
    error: Optional[str] = None

    def as_metadata(self) -> Dict[str, object]:
        """Flatten into RetrievalResult.metadata keys for experiment traces."""
        meta: Dict[str, object] = {
            "reranking_applied": self.applied,
            "reranker_type": self.reranker_type,
            "reranker_candidates_in": self.candidates_in,
            "reranker_returned": self.returned,
            "reranker_latency_ms": round(self.latency_ms, 2),
            "reranker_energy_joules": round(self.energy_joules, 6),
        }
        if self.model_id:
            meta["reranker_model_id"] = self.model_id
        if self.device:
            meta["reranker_device"] = self.device
        if self.energy_method:
            meta["reranker_energy_method"] = self.energy_method
        if self.cold_start_ms > 0.0:
            # One-off model load, reported separately so it is never mistaken
            # for per-query reranking cost.
            meta["reranker_cold_start_ms"] = round(self.cold_start_ms, 2)
        if self.error:
            meta["reranker_error"] = self.error
        return meta


class BaseReranker(ABC):
    """Abstract interface for a reranking stage."""

    @property
    @abstractmethod
    def reranker_name(self) -> str:
        """Human-readable name used in experiment logs."""
        ...

    @abstractmethod
    def rerank(
        self,
        query: str,
        chunks: Sequence[RetrievedChunk],
        top_n: int,
    ) -> RerankOutcome:
        """Re-score `chunks` against `query` and return the best `top_n`."""
        ...


class CrossEncoderReranker(BaseReranker):
    """
    Cross-encoder reranker backed by sentence-transformers.

    A bi-encoder (our BGE retriever) embeds query and document independently, so
    it never sees them together. A cross-encoder scores the (query, chunk) PAIR in
    a single forward pass and therefore models term interaction directly. That is
    what recovers precision@k lost to fusion — and it is why it costs a forward
    pass per candidate rather than a single vector lookup.

    The model is loaded lazily and cached per (model_id, device) across instances:
    loading is seconds, scoring is milliseconds, and reranking is invoked once per
    escalation across hundreds of benchmark trials.
    """

    _model_cache: Dict[Tuple[str, str], object] = {}
    _cache_lock = threading.Lock()

    def __init__(
        self,
        model_id: Optional[str] = None,
        device: Optional[str] = None,
        batch_size: int = 32,
        energy_estimator: Optional[EnergyEstimator] = None,
    ) -> None:
        from core.config import settings

        self.model_id = (
            model_id
            or getattr(settings.retrieval, "reranker_model_id", None)
            or DEFAULT_CROSS_ENCODER_MODEL_ID
        )
        self.batch_size = batch_size
        self.device = device or self._resolve_device()
        self._energy_estimator = energy_estimator or EnergyEstimator(
            cpu_tdp_watts=settings.sustainability.cpu_tdp_watts,
            gpu_tdp_watts=settings.sustainability.gpu_tdp_watts,
        )

    @staticmethod
    def _resolve_device() -> str:
        """Prefer CUDA when available, fall back to CPU."""
        try:
            import torch

            if torch.cuda.is_available():
                return "cuda:0"
        except Exception:  # noqa: BLE001 - torch absent or CUDA probe failed
            pass
        return "cpu"

    @property
    def reranker_name(self) -> str:
        return f"cross_encoder:{self.model_id}"

    def _ensure_loaded(self):
        """Lazy-load and cache the CrossEncoder for this (model_id, device)."""
        key = (self.model_id, self.device)
        cached = self._model_cache.get(key)
        if cached is not None:
            return cached

        with self._cache_lock:
            # Re-check: another thread may have loaded it while we waited.
            cached = self._model_cache.get(key)
            if cached is not None:
                return cached

            from sentence_transformers import CrossEncoder

            logger.info(
                f"Loading cross-encoder reranker '{self.model_id}' on device '{self.device}'..."
            )
            load_start = time.perf_counter()
            model = CrossEncoder(self.model_id, device=self.device, max_length=512)
            load_ms = (time.perf_counter() - load_start) * 1000.0
            logger.info(
                f"Loaded cross-encoder '{self.model_id}' on {self.device} in {load_ms:.0f}ms"
            )
            self._model_cache[key] = model
            return model

    def rerank(
        self,
        query: str,
        chunks: Sequence[RetrievedChunk],
        top_n: int,
    ) -> RerankOutcome:
        """
        Score every (query, chunk) pair with the cross-encoder and keep the top_n.

        The original fused score is preserved in `metadata["pre_rerank_score"]` and
        the pre-rerank position in `metadata["pre_rerank_rank"]`, so rank movement
        stays auditable for the ablation study.
        """
        candidates = list(chunks)
        if not candidates:
            return RerankOutcome(
                chunks=[],
                applied=False,
                reranker_type=RerankerType.CROSS_ENCODER.value,
                model_id=self.model_id,
                device=self.device,
                candidates_in=0,
                returned=0,
                error="no_candidates_to_rerank",
            )

        # Load OUTSIDE the measured region. First-call model load is a one-off
        # cold start (tens of seconds including any HF download); billing it to a
        # single query would inflate that query's reranking energy by orders of
        # magnitude and poison the energy comparison. Amortised load cost is
        # reported separately via `cold_start_ms` for transparency.
        was_loaded = (self.model_id, self.device) in self._model_cache
        load_start = time.perf_counter()
        model = self._ensure_loaded()
        cold_start_ms = 0.0 if was_loaded else (time.perf_counter() - load_start) * 1000.0

        pairs = [
            (query, (chunk.content or "")[:MAX_CHUNK_CHARS_FOR_RERANK])
            for chunk in candidates
        ]

        # Measure ONLY the forward pass — this is the per-query reranking cost.
        start = time.perf_counter()
        raw_scores = model.predict(
            pairs,
            batch_size=self.batch_size,
            show_progress_bar=False,
        )
        latency_ms = (time.perf_counter() - start) * 1000.0

        scored: List[Tuple[RetrievedChunk, float]] = []
        for rank, (chunk, raw_score) in enumerate(zip(candidates, raw_scores)):
            score = float(raw_score)
            chunk.metadata["pre_rerank_score"] = chunk.score
            chunk.metadata["pre_rerank_rank"] = rank
            chunk.metadata["rerank_score"] = round(score, 6)
            scored.append((chunk, score))

        # Sort by cross-encoder score, then keep the requested depth.
        scored.sort(key=lambda item: item[1], reverse=True)
        kept = scored[: max(1, top_n)]

        final_chunks: List[RetrievedChunk] = []
        for new_rank, (chunk, score) in enumerate(kept):
            chunk.metadata["post_rerank_rank"] = new_rank
            # Surface the cross-encoder score as the chunk's ranking score so
            # downstream consumers order by the reranked judgement.
            chunk.score = round(score, 6)
            final_chunks.append(chunk)

        # The cross-encoder runs on our own hardware, so its energy is measurable
        # and attributable — is_local_model=True selects the NVML/GPU path.
        energy: EnergyEstimate = self._energy_estimator.estimate(
            latency_ms=latency_ms,
            input_tokens=0,
            output_tokens=0,
            model_id=self.model_id,
            is_local_model=True,
        )

        logger.debug(
            f"Cross-encoder reranked {len(candidates)} -> {len(final_chunks)} chunks "
            f"in {latency_ms:.1f}ms on {self.device}"
        )

        return RerankOutcome(
            chunks=final_chunks,
            applied=True,
            reranker_type=RerankerType.CROSS_ENCODER.value,
            model_id=self.model_id,
            device=self.device,
            latency_ms=latency_ms,
            candidates_in=len(candidates),
            returned=len(final_chunks),
            energy_joules=energy.energy_joules,
            energy_method=energy.method.value,
            cold_start_ms=cold_start_ms,
        )


# ---------------------------------------------------------------------------
# Factory + pipeline entry point
# ---------------------------------------------------------------------------

_RERANKER_CACHE: Dict[str, BaseReranker] = {}
_FACTORY_LOCK = threading.Lock()


def get_reranker(reranker_type: str) -> Optional[BaseReranker]:
    """
    Return a cached reranker for `reranker_type`, or None if the type is
    unsupported. `RerankerType.NONE` legitimately maps to None.

    `COHERE_RERANK` is declared in the enum but deliberately NOT implemented: it
    is a paid hosted API whose energy draw happens on someone else's hardware and
    is therefore unmeasurable within our declared system boundary. Requesting it
    returns None and the caller records an explicit error rather than silently
    substituting a different reranker.
    """
    if reranker_type in (RerankerType.NONE.value, None, ""):
        return None

    cached = _RERANKER_CACHE.get(reranker_type)
    if cached is not None:
        return cached

    with _FACTORY_LOCK:
        cached = _RERANKER_CACHE.get(reranker_type)
        if cached is not None:
            return cached

        if reranker_type == RerankerType.CROSS_ENCODER.value:
            reranker: BaseReranker = CrossEncoderReranker()
        else:
            return None

        _RERANKER_CACHE[reranker_type] = reranker
        return reranker


def reset_reranker_cache() -> None:
    """Clear cached rerankers and loaded models (used by tests)."""
    with _FACTORY_LOCK:
        _RERANKER_CACHE.clear()
    with CrossEncoderReranker._cache_lock:
        CrossEncoderReranker._model_cache.clear()


def apply_reranking(
    query: str,
    chunks: Sequence[RetrievedChunk],
    strategy: RetrievalStrategyConfig,
    reranker: Optional[BaseReranker] = None,
) -> RerankOutcome:
    """
    Single choke point every retriever calls after candidate generation.

    Returns an outcome whose `chunks` are safe to use regardless of success: on
    any failure the original candidate order is preserved and `applied` is False
    with `error` populated, so a broken reranker degrades to honest hybrid output
    rather than a silent lie.

    Raises
    ------
    RetrievalError
        Only when `EIH_RETRIEVAL_STRICT_RERANKING=true` and reranking was
        requested but could not be performed. Recommended for final experiment
        runs, where a silently skipped reranker would invalidate the results.
    """
    from core.config import settings

    candidates = list(chunks)
    strict = bool(getattr(settings.retrieval, "strict_reranking", False))

    if not strategy.enable_reranking:
        return RerankOutcome(
            chunks=candidates,
            applied=False,
            reranker_type=RerankerType.NONE.value,
            candidates_in=len(candidates),
            returned=len(candidates),
        )

    reranker_type = strategy.reranker_type
    if hasattr(reranker_type, "value"):
        reranker_type = reranker_type.value

    active = reranker if reranker is not None else get_reranker(reranker_type)

    if active is None:
        msg = (
            f"Strategy '{strategy.strategy_name}' requested enable_reranking=True with "
            f"reranker_type='{reranker_type}', which has no available implementation. "
            "Retrieval proceeded WITHOUT reranking."
        )
        logger.error(msg)
        if strict:
            raise RetrievalError(message=msg)
        return RerankOutcome(
            chunks=candidates,
            applied=False,
            reranker_type=str(reranker_type),
            candidates_in=len(candidates),
            returned=len(candidates),
            error=f"unsupported_reranker_type:{reranker_type}",
        )

    try:
        outcome = active.rerank(query=query, chunks=candidates, top_n=strategy.reranker_top_n)
    except Exception as exc:  # noqa: BLE001 - model load / inference failure
        msg = (
            f"Reranker '{getattr(active, 'reranker_name', reranker_type)}' failed for "
            f"strategy '{strategy.strategy_name}': {exc}. "
            "Retrieval proceeded WITHOUT reranking."
        )
        logger.error(msg)
        if strict:
            raise RetrievalError(message=msg) from exc
        return RerankOutcome(
            chunks=candidates,
            applied=False,
            reranker_type=str(reranker_type),
            candidates_in=len(candidates),
            returned=len(candidates),
            error=f"{type(exc).__name__}: {exc}",
        )

    if not outcome.applied and strict and outcome.error != "no_candidates_to_rerank":
        raise RetrievalError(
            message=(
                f"Reranking did not run for strategy '{strategy.strategy_name}': "
                f"{outcome.error}"
            )
        )

    return outcome
