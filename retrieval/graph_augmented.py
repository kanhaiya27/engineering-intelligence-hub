"""
Engineering Intelligence Hub — Graph-Augmented Retriever (M3)
==============================================================
Implements graph context injection on top of hybrid (dense + BM25) retrieval.

Architecture:
    1. Run hybrid retrieval to get initial chunks
    2. For each chunk, map source path → graph node URI
    3. Expand the graph neighbourhood up to `graph_hop_depth` hops
    4. Synthesise neighbour properties into graph context strings
    5. Inject graph context strings as additional chunks (bounded)

IMPORTANT RESEARCH NOTE:
Graph context injection bounds (MAX_GRAPH_CHUNKS, max_hop_depth) are
HEURISTIC starting points for M3.  They will be tuned empirically in
Phase-2 M5 controlled evaluation.  Do NOT claim these as optimal values.

Graceful Degradation:
    If no graph store is provided (offline or test mode) the retriever
    falls back transparently to HybridRetriever — no exception is raised.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, List, Optional, Set

from core.logging import get_logger
from knowledge.graph.base import BaseGraphStore
from knowledge.schemas.tasks import RetrievedChunk, RetrievalResult, TaskClassification
from retrieval.base import BaseRetriever
from retrieval.strategies import RetrievalStrategyConfig

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)

# Heuristic: maximum number of graph context chunks to inject per retrieval call
# Tuned empirically in Phase-2 M5 evaluation.
_HEURISTIC_MAX_GRAPH_CHUNKS = 4
# Heuristic: maximum total nodes to expand across all seed nodes per call
_HEURISTIC_MAX_TOTAL_NODES = 20


# Which structural relations are most informative to inject first (lower = earlier).
_RELATION_PRIORITY = {"TESTS": 0, "IMPORTS": 1, "CALLS": 2, "CONTAINS": 3}
# Per retrieved file: at most this many structural + co-change neighbours.
_PER_SEED = 2


def _short(node_id: str) -> str:
    """Readable name from a node id: file path, or path::Symbol."""
    kind, _, rest = node_id.partition(":")
    if kind == "file":
        return rest.split(":", 1)[-1] if ":" in rest else rest
    if kind == "sym":
        parts = rest.split(":")
        return f"{parts[-2]}::{parts[-1]}" if len(parts) >= 3 else rest
    return node_id


def _describe(path: List[tuple]) -> str:
    return " ; ".join(f"{_short(src)} --{rel}--> {_short(tgt)}" for rel, src, tgt in path)


def _node_to_context_chunk(
    node: Any,
    seed_chunk_id: str,
    task_id: str,
    hop: int,
    relation: str,
    relation_text: str,
) -> RetrievedChunk:
    """
    Convert a graph neighbour into a RetrievedChunk for context injection.

    The chunk states HOW the neighbour is related to the retrieved evidence
    (e.g. "src/flask/app.py --IMPORTS--> src/flask/ctx.py"): that relation is the
    structural context System D adds (RQ2). It is labelled GRAPH_CONTEXT so the
    evaluation can tell injected nodes from retrieved text; score 0.0.
    """
    props = node.properties
    name = props.get("name") or props.get("symbol_name") or node.node_id
    path = props.get("file_path") or props.get("path") or ""
    start_l = props.get("start_line")
    end_l = props.get("end_line")

    content_parts = [f"[GRAPH_CONTEXT | {relation} | hop={hop}]", f"Relation: {relation_text}",
                     f"{node.label}: {name}"]
    if path and path != name:
        content_parts.append(f"Path: {path}")
    if start_l is not None and end_l is not None:
        content_parts.append(f"Lines: {start_l}-{end_l}")

    return RetrievedChunk(
        chunk_id=f"graph_ctx:{node.node_id}:{seed_chunk_id}",
        content="\n".join(content_parts),
        source_path=path,
        score=0.0,
        repository=props.get("repository", ""),
        metadata={
            "graph_context": True,
            "graph_node_id": node.node_id,
            "graph_node_label": node.label,
            "graph_hop": hop,
            "graph_relation": relation,
            "graph_seed_chunk_id": seed_chunk_id,
            "start_line": start_l,
            "end_line": end_l,
            "commit_sha": props.get("commit_sha", ""),
        },
    )


class GraphAugmentedRetriever(BaseRetriever):
    """
    Hybrid retriever with engineering knowledge graph context injection.

    When `strategy.include_graph_context` is True:
      1. Executes hybrid dense + BM25 retrieval
      2. For each retrieved chunk, looks up matching nodes in the graph store
         keyed by (source_path, start_line)
      3. Expands the graph neighbourhood up to `strategy.graph_hop_depth`
      4. Converts neighbour nodes to context chunks (bounded by
         _HEURISTIC_MAX_GRAPH_CHUNKS per call)
      5. Appends graph context chunks to the retrieval result

    When `strategy.include_graph_context` is False or graph_store is None,
    the retriever delegates to HybridRetriever without graph augmentation.
    """

    def __init__(
        self,
        dense_retriever: Optional[Any] = None,
        sparse_retriever: Optional[Any] = None,
        graph_store: Optional[BaseGraphStore] = None,
    ) -> None:
        from retrieval.hybrid import HybridRetriever
        # Pass retrievers through as-is (possibly None) and let HybridRetriever
        # apply its own defaults — it wires a corpus-backed BM25, which a bare
        # BM25Retriever() here would not.
        self._hybrid = HybridRetriever(
            dense_retriever=dense_retriever,
            sparse_retriever=sparse_retriever,
        )
        self._graph_store: Optional[BaseGraphStore] = graph_store

    @property
    def retriever_name(self) -> str:
        return "graph_augmented"

    def retrieve(
        self,
        query: str,
        strategy: RetrievalStrategyConfig,
        classification: Optional[TaskClassification] = None,
        task_id: str = "adhoc",
    ) -> RetrievalResult:
        start_time = time.perf_counter()

        # 1. Execute hybrid retrieval (dense + BM25 fusion)
        hybrid_result = self._hybrid.retrieve(
            query=query,
            strategy=strategy,
            classification=classification,
            task_id=task_id,
        )

        graph_chunks: List[RetrievedChunk] = []
        graph_nodes_visited = 0
        graph_augmented = False

        # 2. Graph expansion — only if enabled and store is available
        if strategy.include_graph_context and self._graph_store is not None:
            graph_chunks, graph_nodes_visited = self._expand_graph_context(
                chunks=hybrid_result.chunks,
                hop_depth=strategy.graph_hop_depth,
                max_graph_chunks=_HEURISTIC_MAX_GRAPH_CHUNKS,
                task_id=task_id,
            )
            graph_augmented = True
        elif strategy.include_graph_context and self._graph_store is None:
            logger.warning(
                f"Task {task_id}: graph_context requested but no graph_store configured. "
                "Falling back to hybrid retrieval without graph augmentation."
            )

        # 3. Combine chunks — retrieved first, then bounded graph context.
        #
        # Note on reranking: the hybrid stage above has already applied the
        # cross-encoder when strategy.enable_reranking is set, so retrieved
        # evidence arrives here in reranked order. Graph context chunks are
        # deliberately EXEMPT from reranking — they are included for structural
        # provenance (callers, imports, tested-by edges), not topical similarity
        # to the query, so scoring them against the query would penalise exactly
        # the structural context they exist to supply and would let the reranker
        # discard the graph contribution the D-vs-C ablation is measuring.
        all_chunks = list(hybrid_result.chunks) + graph_chunks

        # 4. Respect max_context_chunks
        max_ctx = strategy.max_context_chunks + (
            _HEURISTIC_MAX_GRAPH_CHUNKS if graph_augmented else 0
        )
        final_chunks = all_chunks[:max_ctx]

        latency_ms = (time.perf_counter() - start_time) * 1000.0

        return RetrievalResult(
            task_id=task_id,
            strategy_used=strategy.strategy_name,
            chunks=final_chunks,
            total_retrieved=len(final_chunks),
            retrieval_latency_ms=round(latency_ms, 2),
            metadata={
                **hybrid_result.metadata,
                "graph_augmented": graph_augmented,
                "graph_chunks_injected": len(graph_chunks),
                "graph_nodes_visited": graph_nodes_visited,
                "graph_hop_depth": strategy.graph_hop_depth,
                "note": (
                    "Graph context bounds are heuristic starting points "
                    "— not validated as optimal (Phase-2 M5 pending)."
                ),
            },
        )

    def _expand_graph_context(
        self,
        chunks: List[RetrievedChunk],
        hop_depth: int,
        max_graph_chunks: int,
        task_id: str,
    ) -> tuple[List[RetrievedChunk], int]:
        """
        Structural + co-change context for the retrieved files.

        For each retrieved file (in retrieval order, each file once), up to _PER_SEED
        neighbours are injected: first structural neighbours in OTHER files reached
        within `hop_depth` hops without passing through hub nodes (Repository,
        Commit), nearest first, then TESTS > IMPORTS > CALLS > CONTAINS; then the
        files most strongly co-changed in Git history (cosine of shared commits, so a
        changelog that changes with everything does not dominate). Bounded by
        `max_graph_chunks` overall.

        Returns (graph_context_chunks, nodes_considered).
        """
        if self._graph_store is None:
            return [], 0

        injected: List[RetrievedChunk] = []
        seen_nodes: Set[str] = set()
        seen_files: Set[str] = set()
        considered = 0

        for chunk in chunks:
            if len(injected) >= max_graph_chunks or considered >= _HEURISTIC_MAX_TOTAL_NODES * 10:
                break
            source_path = chunk.source_path or ""
            if not source_path or chunk.metadata.get("graph_context"):
                continue
            seed = f"file:{chunk.repository}:{source_path}" if chunk.repository else f"file:{source_path}"
            if seed in seen_files:
                continue
            seen_files.add(seed)
            seen_nodes.add(seed)
            try:
                if self._graph_store.get_node(seed) is None:
                    continue
                candidates = self._graph_store.expand(seed, max_depth=hop_depth, limit=60)
                considered += len(candidates)
                # Other files first (what the retrieved text cannot show), then structure
                # inside the same file; within each, by relation priority and distance.
                for c in candidates:  # the most informative of the shortest connections
                    c["path"] = min(c.get("paths") or [c["path"]],
                                    key=lambda p: min(_RELATION_PRIORITY.get(r[0], 9) for r in p))
                ranked = sorted(
                    candidates,
                    key=lambda c: (
                        (c["node"].properties.get("file_path") or c["node"].properties.get("path")
                         or "") in ("", source_path),
                        c["hop"], min(_RELATION_PRIORITY.get(r[0], 9) for r in c["path"]), c["node"].node_id),
                )
                picked = 0
                for c in ranked:
                    if picked >= _PER_SEED or len(injected) >= max_graph_chunks:
                        break
                    node = c["node"]
                    if node.node_id in seen_nodes:
                        continue
                    seen_nodes.add(node.node_id)
                    relation = min((r[0] for r in c["path"]), key=lambda t: _RELATION_PRIORITY.get(t, 9))
                    injected.append(_node_to_context_chunk(node, chunk.chunk_id, task_id, c["hop"],
                                                           relation, _describe(c["path"])))
                    picked += 1
                for other, n_commits in self._graph_store.co_changed(seed, limit=_PER_SEED):
                    if len(injected) >= max_graph_chunks or picked >= _PER_SEED + 1:
                        break
                    if other.node_id in seen_nodes:
                        continue
                    seen_nodes.add(other.node_id)
                    injected.append(_node_to_context_chunk(
                        other, chunk.chunk_id, task_id, 2, "CO_CHANGED",
                        f"{source_path} and {_short(other.node_id)} changed together in {n_commits} commits"))
                    picked += 1
            except Exception as exc:  # noqa: BLE001 — graceful degradation, but visible
                logger.warning(f"Task {task_id}: graph expansion failed for node '{seed}': {exc}")
                continue

        return injected, considered
