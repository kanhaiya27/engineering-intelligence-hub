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


def _node_to_context_chunk(
    node: Any,
    seed_chunk_id: str,
    task_id: str,
    hop: int,
) -> RetrievedChunk:
    """
    Convert a graph neighbour node into a RetrievedChunk for context injection.

    The resulting chunk is clearly labelled as GRAPH_CONTEXT so
    evaluation pipelines can distinguish injected nodes from retrieved
    text chunks.  Score is set to 0.0 (below any score_threshold) but
    the chunk is always forwarded as it is explicitly selected by the
    graph expansion logic.
    """
    props = node.properties
    name = props.get("name") or props.get("symbol_name") or node.node_id
    path = props.get("path") or props.get("file_path") or ""
    start_l = props.get("start_line")
    end_l = props.get("end_line")
    commit = props.get("commit_sha", "")

    content_parts = [f"[GRAPH_CONTEXT | {node.label} | hop={hop}]"]
    content_parts.append(f"Name: {name}")
    if path:
        content_parts.append(f"Path: {path}")
    if start_l is not None and end_l is not None:
        content_parts.append(f"Lines: {start_l}-{end_l}")
    if commit:
        content_parts.append(f"Commit: {commit}")
    for k, v in props.items():
        if k not in {"name", "symbol_name", "path", "file_path", "start_line", "end_line", "commit_sha"}:
            content_parts.append(f"{k}: {v}")

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
            "graph_seed_chunk_id": seed_chunk_id,
            "start_line": start_l,
            "end_line": end_l,
            "commit_sha": commit,
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
        Expand graph neighbourhood for retrieved chunks.

        For each chunk, we look up the file path in the graph and traverse
        outbound + inbound edges up to `hop_depth` hops.  We bound the
        total injected chunks by `max_graph_chunks` to prevent context explosion.

        Returns
        -------
        (graph_context_chunks, total_nodes_visited)
        """
        if self._graph_store is None:
            return [], 0

        injected_chunks: List[RetrievedChunk] = []
        seen_node_ids: Set[str] = set()
        total_nodes_visited = 0

        for chunk in chunks:
            if len(injected_chunks) >= max_graph_chunks:
                break
            if total_nodes_visited >= _HEURISTIC_MAX_TOTAL_NODES:
                break

            # Build a deterministic node ID from the chunk's source path.
            # This mirrors the `file:{path}` URI convention used in M2.
            source_path = chunk.source_path or ""
            if not source_path:
                continue

            repo = chunk.repository or ""
            file_node_id = f"file:{repo}:{source_path}" if repo else f"file:{source_path}"

            try:
                node = self._graph_store.get_node(file_node_id)
                if node is None:
                    continue

                # Get neighbours up to hop_depth
                pairs = self._graph_store.get_neighbours(
                    node_id=file_node_id,
                    direction="both",
                    max_depth=hop_depth,
                )
                total_nodes_visited += len(pairs)

                for edge, neighbour in pairs:
                    if len(injected_chunks) >= max_graph_chunks:
                        break
                    if neighbour.node_id in seen_node_ids:
                        continue
                    seen_node_ids.add(neighbour.node_id)

                    hop = edge.properties.get("depth", 1)
                    ctx_chunk = _node_to_context_chunk(
                        node=neighbour,
                        seed_chunk_id=chunk.chunk_id,
                        task_id=task_id,
                        hop=hop,
                    )
                    injected_chunks.append(ctx_chunk)

            except Exception as exc:  # noqa: BLE001 — graceful degradation
                logger.warning(
                    f"Task {task_id}: graph expansion failed for node "
                    f"'{file_node_id}': {exc}"
                )
                continue

        return injected_chunks, total_nodes_visited
