"""
Engineering Intelligence Hub — build the knowledge graph for a corpus wave
==========================================================================
Builds the Neo4j knowledge graph (AST + Git history) for every repository of a wave in
`datasets/registry.yaml`, from the SAME files, normalised the SAME way, at the SAME
pinned commit as the Qdrant collection — so every retrieved chunk's file has a graph
node with matching line numbers.

Checks (the build fails loudly instead of producing a silently partial graph):
  * each checkout's HEAD equals the registry's pinned commit
  * every file indexed in Qdrant for the repository has a File node
  * counts in the report are read back from Neo4j after writing

Usage:
  python -m scripts.build_graph --wave 1 --reset
Output: experiments/results/graph_build/<machine>/graph_build_wave<N>.json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

import yaml

from core.config import PROJECT_ROOT, settings
from experiments.provenance import collect_provenance, write_json
from ingestion.loaders.file_loader import FileIngestionSource
from ingestion.processors.normalizer import ArtifactNormalizer
from knowledge.graph.base import NodeLabel, RelationshipType
from knowledge.graph.builder import EngineeringGraphBuilder
from knowledge.graph.extractor import file_node_id
from knowledge.graph.neo4j import Neo4jGraphStore
from scripts.job_queue import machine_dir

REGISTRY = PROJECT_ROOT / "datasets" / "registry.yaml"
CACHE = PROJECT_ROOT / ".corpus_cache"


def indexed_files(repository: str) -> Set[str]:
    """Distinct file paths Qdrant holds for this repository (payload metadata.file_path)."""
    url = f"http://{settings.vector_store.host}:{settings.vector_store.port}"
    coll = settings.vector_store.collection_name
    files: Set[str] = set()
    offset = None
    while True:
        body: Dict[str, Any] = {"limit": 5000, "with_payload": ["metadata.file_path"], "with_vector": False,
                                "filter": {"must": [{"key": "repository", "match": {"value": repository}}]}}
        if offset is not None:
            body["offset"] = offset
        req = urllib.request.Request(f"{url}/collections/{coll}/points/scroll", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            res = json.load(r)["result"]
        files.update(p["payload"]["metadata"]["file_path"] for p in res["points"])
        offset = res.get("next_page_offset")
        if offset is None:
            return files


def load_files(repo_dir: Path, repository: str, commit: str) -> List[Tuple[str, str]]:
    norm = ArtifactNormalizer()
    out = []
    for art in FileIngestionSource(root_dir=repo_dir, repository_id=repository, commit_sha=commit).load():
        text = norm.normalize_text(art.raw_content)
        if text.strip() and art.source_path:
            out.append((art.source_path, text))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wave", type=int, default=1)
    ap.add_argument("--reset", action="store_true", help="delete the whole graph first")
    ap.add_argument("--max-commits", type=int, default=500)
    ap.add_argument("--max-files-per-commit", type=int, default=30)
    args = ap.parse_args()

    registry = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    entries = [e for e in registry["repositories"] if e.get("wave") == args.wave and e.get("selected_commit")]
    store = Neo4jGraphStore()
    if not store.is_available():
        print("Neo4j is not reachable with the .env EIH_GRAPH_* settings", file=sys.stderr)
        return 2
    if args.reset:
        store.clear()
    builder = EngineeringGraphBuilder(store)
    per_repo, t0 = [], time.perf_counter()
    for e in entries:
        repo = f"{e['owner']}/{e['name']}"
        repo_dir = CACHE / e["repo_id"]
        head = subprocess.run(["git", "-C", str(repo_dir), "rev-parse", "HEAD"], capture_output=True,
                              text=True, check=True).stdout.strip()
        if head != e["selected_commit"]:
            raise SystemExit(f"{repo}: checkout {head} != pinned {e['selected_commit']}")
        files = load_files(repo_dir, repo, head)
        report = builder.build_repository_graph(repo, head, files, repo_dir=repo_dir,
                                                max_commits=args.max_commits,
                                                max_files_per_commit=args.max_files_per_commit)
        indexed = indexed_files(repo)
        missing = sorted(p for p in indexed if store.get_node(file_node_id(repo, p)) is None)
        report["qdrant_files"] = len(indexed)
        report["qdrant_files_without_graph_node"] = len(missing)
        report["missing_examples"] = missing[:10]
        per_repo.append(report)
        print(f"{repo}: {report['nodes_written']} nodes, {report['edges_written']} edges, "
              f"{len(missing)} of {len(indexed)} indexed files without a node", flush=True)
        if missing:
            raise SystemExit(f"{repo}: {len(missing)} indexed files have no graph node, e.g. {missing[:5]}")

    labels = [NodeLabel.REPOSITORY, NodeLabel.FILE, NodeLabel.CLASS, NodeLabel.FUNCTION, NodeLabel.METHOD,
              NodeLabel.TEST, NodeLabel.COMMIT]
    rels = [RelationshipType.CONTAINS, RelationshipType.IMPORTS, RelationshipType.CALLS,
            RelationshipType.TESTS, RelationshipType.MODIFIES]
    data = {
        "study": f"graph_build_wave{args.wave}",
        "provenance": collect_provenance(include_ollama=False),
        "config": {"wave": args.wave, "reset": args.reset, "max_commits": args.max_commits,
                   "max_files_per_commit": args.max_files_per_commit, "neo4j_uri": store.uri,
                   "qdrant_collection": settings.vector_store.collection_name},
        "results": {
            "read_back": {"nodes": store.count_nodes(), "edges": store.count_edges(),
                          "nodes_by_label": {lbl: store.count_nodes(lbl) for lbl in labels},
                          "edges_by_type": {r: store.count_edges(r) for r in rels}},
            "per_repository": per_repo,
            "seconds": round(time.perf_counter() - t0, 1),
        },
    }
    out = PROJECT_ROOT / "experiments" / "results" / "graph_build" / machine_dir() / f"graph_build_wave{args.wave}.json"
    write_json(out, data)
    print(json.dumps(data["results"]["read_back"], indent=1))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
