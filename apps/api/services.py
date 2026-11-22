"""
Shared, lazily-created services for the application routers (OKF workspaces, sync,
conversations, LLM, code retrieval).

Required services fail loudly: if Qdrant, Neo4j or Ollama is down the caller gets a 503
with the reason, never a silent in-memory stand-in or an invented answer. Tests replace
the module-level singletons directly.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from fastapi import HTTPException, status

from core.config import PROJECT_ROOT, settings
from core.logging import get_logger
from knowledge.okf.bundle import OKFBundle
from knowledge.okf.collaboration import KnowledgeWorkspace

logger = get_logger(__name__)

_lock = threading.RLock()
_workspaces: Dict[str, KnowledgeWorkspace] = {}
_vector_index = None
_graph_projection = None
_conversations = None
_llm = None
_code_retriever = None


def unavailable(what: str, exc: Exception | str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"{what} unavailable: {exc}")


def bundle_names() -> List[str]:
    root = Path(settings.okf.root)
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir() and not p.name.startswith("."))


def vector_index():
    global _vector_index
    with _lock:
        if _vector_index is None:
            from knowledge.okf.sync import OKFVectorIndex
            _vector_index = OKFVectorIndex()
        return _vector_index


def graph_projection():
    global _graph_projection
    with _lock:
        if _graph_projection is None:
            from knowledge.graph.neo4j import Neo4jGraphStore
            from knowledge.okf.sync import OKFGraphProjection
            store = Neo4jGraphStore()
            if not store.is_available():
                raise unavailable("Neo4j", "not reachable")
            _graph_projection = OKFGraphProjection(store)
        return _graph_projection


def _sync_listener(bundle: OKFBundle) -> Callable[[str, List[str]], None]:
    def sync(name: str, concept_ids: List[str]) -> None:
        errors = []
        try:
            vector_index().sync_concepts(bundle, name, concept_ids)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"qdrant: {exc}")
        try:
            graph_projection().sync_concepts(bundle, name, concept_ids)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"neo4j: {getattr(exc, 'detail', exc)}")
        if errors:
            raise RuntimeError("; ".join(errors))  # recorded by the workspace audit + returned to the caller
    return sync


def workspace(name: str) -> KnowledgeWorkspace:
    with _lock:
        if name not in _workspaces:
            root = Path(settings.okf.root) / name
            if not root.is_dir() or name.startswith("."):
                raise HTTPException(status_code=404, detail=f"bundle '{name}' not found")
            ws = KnowledgeWorkspace(OKFBundle(root), settings.okf.state_dir, name=name)
            ws.on_change(_sync_listener(ws.bundle))
            _workspaces[name] = ws
        return _workspaces[name]


def forget_workspace(name: str) -> None:
    with _lock:
        _workspaces.pop(name, None)


def conversations():
    global _conversations
    with _lock:
        if _conversations is None:
            from apps.api.storage import ConversationStore
            _conversations = ConversationStore(Path(settings.okf.state_dir) / "app.sqlite3")
        return _conversations


def llm():
    """The configured real provider (Ollama, configs/inference.yaml). No mock fallback."""
    global _llm
    with _lock:
        if _llm is None:
            from generation.providers.factory import build_provider
            _llm = build_provider()
        return _llm


warm_state: Dict[str, Any] = {"state": "not_started"}


def warm_up() -> None:
    """Load the embedder, the hybrid (BM25) index and the OKF index once, untimed."""
    import time as _t
    t0 = _t.perf_counter()
    warm_state.update(state="running")
    try:
        code_evidence("How is the application configured?", 1)
        try:
            vector_index().search("configuration", bundle=settings.okf.default_bundle, limit=1)
        except Exception as exc:  # noqa: BLE001 - OKF index may be absent; code path still warm
            logger.warning(f"OKF warm-up skipped: {exc}")
        warm_state.update(state="done", seconds=round(_t.perf_counter() - t0, 1))
    except Exception as exc:  # noqa: BLE001
        warm_state.update(state="failed", error=str(exc)[:200])
        logger.warning(f"warm-up failed: {exc}")


def code_evidence(question: str, k: int) -> List[Dict[str, Any]]:
    """Code/doc chunks from the research corpus with System B's fixed hybrid strategy
    (configs/retrieval.yaml 'hybrid'), read-only. The research systems are not changed."""
    global _code_retriever
    with _lock:
        if _code_retriever is None:
            from retrieval.hybrid import HybridRetriever
            from retrieval.router import RetrievalRouter
            strategy = RetrievalRouter.from_yaml(str(PROJECT_ROOT / "configs" / "retrieval.yaml")).list_strategies()["hybrid"]
            _code_retriever = (HybridRetriever(), strategy)
    retriever, strategy = _code_retriever
    strategy = strategy.model_copy(update={"top_k": max(k, 1), "max_context_chunks": max(k, 1)})
    result = retriever.retrieve(question, strategy, task_id="app-chat")
    out = []
    for ch in result.chunks[:k]:
        md = ch.metadata or {}
        out.append({"chunk_id": ch.chunk_id, "repository": ch.repository, "source_path": ch.source_path or md.get("file_path"),
                    "start_line": md.get("start_line"), "end_line": md.get("end_line"), "score": round(ch.score, 4),
                    "content": ch.content})
    return out
