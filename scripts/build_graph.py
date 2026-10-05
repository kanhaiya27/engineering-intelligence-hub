"""
Engineering Intelligence Hub — Knowledge Graph Population (WORK_PLAN B3)
========================================================================
Builds the engineering knowledge graph for the corpus repositories, from the
SAME files at the SAME commit as the vector index, and verifies that the
graph-augmented retriever can actually reach it.

Per repository:
  1. Clone (or reuse) the checkout at its pinned tag — the clone logic of
     scripts/ingest_corpus.py, so both use `.corpus_cache/<repo_id>`.
  2. Read the commit the Qdrant collection holds for the repository and refuse
     to build if the checkout is at a different commit: a graph of other code
     would inject context that does not match the retrieved chunks.
  3. Load files with the ingestion loader (FileIngestionSource) and build the
     graph from its SourceFile artifacts with EngineeringGraphBuilder.
  4. Verify: every source-code file in the vector index must have a File node
     under the ID GraphAugmentedRetriever looks up (`file:{repo}:{path}`).
     Coverage below 100% is reported per repository, never hidden.

Results (counts, coverage, dropped edges, provenance) are written to
experiments/results/graph_build/<machine folder>/.

Usage (from repo root, Docker Neo4j + Qdrant running):
    python -m scripts.build_graph --wave 1
    python -m scripts.build_graph --repos flask,fastapi
    python -m scripts.build_graph --wave 1 --store memory   # dry build, no Neo4j writes
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from core.config import PROJECT_ROOT, settings
from core.logging import get_logger
from experiments.provenance import collect_provenance, write_json
from ingestion.loaders.file_loader import FileIngestionSource
from knowledge.graph.base import BaseGraphStore
from knowledge.graph.builder import EngineeringGraphBuilder
from knowledge.graph.ids import file_node_id
from knowledge.graph.in_memory import InMemoryGraphStore
from knowledge.graph.neo4j import Neo4jGraphStore
from knowledge.schemas.artifacts import SourceFile
from scripts.ingest_corpus import CACHE_DIR, clone_or_update, load_registry, resolve_commit

logger = get_logger(__name__)

SOURCE_CODE = "source_code"


def indexed_files(collection: str, repository: str) -> Tuple[Set[str], Set[str]]:
    """(commit SHAs, source-code file paths) the vector index holds for one repository."""
    from qdrant_client import QdrantClient
    from qdrant_client.http import models as qmodels

    client = QdrantClient(host=settings.vector_store.host, port=settings.vector_store.port)
    flt = qmodels.Filter(must=[
        qmodels.FieldCondition(key="repository", match=qmodels.MatchValue(value=repository)),
    ])
    commits: Set[str] = set()
    code_files: Set[str] = set()
    offset = None
    while True:
        points, offset = client.scroll(
            collection,
            scroll_filter=flt,
            limit=5000,
            offset=offset,
            with_payload=["artifact_type", "metadata.file_path", "metadata.commit_sha"],
            with_vectors=False,
        )
        for p in points:
            meta = p.payload.get("metadata", {})
            if meta.get("commit_sha"):
                commits.add(meta["commit_sha"])
            if p.payload.get("artifact_type") == SOURCE_CODE and meta.get("file_path"):
                code_files.add(meta["file_path"])
        if offset is None:
            break
    return commits, code_files


def existing_node_ids(store: BaseGraphStore, node_ids: List[str]) -> Set[str]:
    """Which of `node_ids` exist in the store (one query on Neo4j)."""
    if isinstance(store, Neo4jGraphStore):
        rows = store.query(
            "UNWIND $ids AS id MATCH (n:Entity {node_id: id}) RETURN n.node_id AS id",
            {"ids": node_ids},
        )
        return {r["id"] for r in rows}
    return {i for i in node_ids if store.get_node(i) is not None}


def repository_node_count(store: BaseGraphStore, repository: str) -> Optional[int]:
    if isinstance(store, Neo4jGraphStore):
        rows = store.query(
            "MATCH (n:Entity {repository: $repo}) RETURN count(n) AS cnt", {"repo": repository}
        )
        return rows[0]["cnt"] if rows else 0
    return None


def build_one(
    entry: Dict[str, Any],
    cache_dir: Path,
    collection: str,
    store: BaseGraphStore,
) -> Dict[str, Any]:
    repo_id = entry["repo_id"]
    repository = f"{entry['owner']}/{entry['name']}"
    result: Dict[str, Any] = {"repo_id": repo_id, "repository": repository}

    repo_path = clone_or_update(entry, cache_dir)
    if repo_path is None:
        return {**result, "status": "failed", "error": "clone failed"}
    commit = resolve_commit(repo_path)

    index_commits, index_code_files = indexed_files(collection, repository)
    result["checkout_commit"] = commit
    result["index_commits"] = sorted(index_commits)
    if index_commits != {commit}:
        return {
            **result,
            "status": "failed",
            "error": (
                f"checkout commit {commit} != commit(s) in '{collection}' "
                f"{sorted(index_commits)}; graph would not describe the indexed code"
            ),
        }

    already = repository_node_count(store, repository)
    if already:
        return {
            **result,
            "status": "failed",
            "error": (
                f"{already} nodes for {repository} already in the graph; "
                "a rebuild would leave stale nodes. Remove them first (ask before deleting)."
            ),
        }

    started = time.perf_counter()
    loader = FileIngestionSource(root_dir=repo_path, repository_id=repository, commit_sha=commit)
    artifacts = [a for a in loader.load() if isinstance(a, SourceFile)]
    metrics = EngineeringGraphBuilder(graph_store=store).build_repository_graph(
        repository=repository,
        artifacts=artifacts,
        commit_sha=commit,
        repository_url=entry.get("url"),
    )

    # Verification: can the retriever reach a File node for every indexed code file?
    wanted = sorted(file_node_id(repository, p) for p in index_code_files)
    found = existing_node_ids(store, wanted)
    missing = [w for w in wanted if w not in found]

    result.update({
        "status": "completed",
        "source_files_loaded": len(artifacts),
        "graph": {k: v for k, v in metrics.items() if k not in {"repository", "status"}},
        "persisted_nodes_for_repository": repository_node_count(store, repository),
        "retriever_coverage": {
            "indexed_code_files": len(wanted),
            "with_file_node": len(found),
            "fraction": round(len(found) / len(wanted), 4) if wanted else None,
            "missing_examples": missing[:10],
        },
        "elapsed_seconds": round(time.perf_counter() - started, 1),
    })
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Populate the EIH knowledge graph.")
    parser.add_argument("--wave", type=int, default=1, help="Registry wave to build")
    parser.add_argument("--repos", type=str, default=None, help="Comma-separated repo_ids")
    parser.add_argument("--collection", type=str, default=None, help="Qdrant collection")
    parser.add_argument("--cache-dir", type=str, default=str(CACHE_DIR))
    parser.add_argument("--store", choices=["neo4j", "memory"], default="neo4j")
    parser.add_argument("--out", type=str, default=None, help="Result JSON path")
    args = parser.parse_args()

    registry = load_registry()
    collection = args.collection or registry.get("default_collection", "eih_knowledge")
    only = {r.strip() for r in args.repos.split(",")} if args.repos else None
    targets = [
        e for e in registry["repositories"]
        if e.get("wave") == args.wave and (only is None or e["repo_id"] in only)
    ]
    if not targets:
        logger.error(f"No repositories matched wave={args.wave} repos={only}")
        return 1

    if args.store == "neo4j":
        store: BaseGraphStore = Neo4jGraphStore()
        if not store.is_available():
            logger.error(f"Neo4j not reachable at {store.uri} (check docker compose and .env)")
            return 1
        server = store.query("CALL dbms.components() YIELD name, versions, edition "
                             "RETURN name, versions[0] AS version, edition")
    else:
        store = InMemoryGraphStore()
        store.connect()
        server = None

    results: List[Dict[str, Any]] = []
    for entry in targets:
        print(f"[{entry['repo_id']}] building graph ...", flush=True)
        try:
            res = build_one(entry, Path(args.cache_dir), collection, store)
        except Exception as exc:  # noqa: BLE001 - one repo must not hide the others
            logger.exception(f"[{entry['repo_id']}] graph build failed")
            res = {"repo_id": entry["repo_id"], "status": "failed", "error": str(exc)}
        results.append(res)
        cov = res.get("retriever_coverage", {})
        print(
            f"[{entry['repo_id']}] {res['status']}: "
            f"nodes={res.get('graph', {}).get('total_nodes')} "
            f"edges={res.get('graph', {}).get('total_edges')} "
            f"coverage={cov.get('with_file_node')}/{cov.get('indexed_code_files')}"
            + (f" error={res['error']}" if res.get("error") else ""),
            flush=True,
        )

    machine = {"laptop-a": "machine_A", "laptop-b": "machine_B"}.get(settings.machine_id, settings.machine_id)
    out = Path(args.out) if args.out else (
        PROJECT_ROOT / "experiments" / "results" / "graph_build" / machine / f"graph_build_wave{args.wave}.json"
    )
    payload = {
        "study": "graph_build",
        "tier": "MEASURED (counts read back from the store)",
        "collection": collection,
        "store": args.store,
        "graph_server": server,
        "totals": {
            "nodes": sum(r.get("graph", {}).get("total_nodes", 0) for r in results),
            "edges": sum(r.get("graph", {}).get("total_edges", 0) for r in results),
            "store_node_count": store.count_nodes(),
            "store_edge_count": store.count_edges(),
        },
        "repositories": results,
        "provenance": collect_provenance(include_ollama=False),
    }
    if args.store == "neo4j":
        write_json(out, payload)
        print(f"\nResult written to {out}")
    else:
        print("\n(--store memory: nothing written to Neo4j, result file not written)")
    print(f"Store totals: {payload['totals']}")
    return 0 if all(r["status"] == "completed" for r in results) else 2


if __name__ == "__main__":
    sys.exit(main())
