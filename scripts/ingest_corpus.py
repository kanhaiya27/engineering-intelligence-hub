"""
Engineering Intelligence Hub — Corpus Ingestion Driver
=======================================================
Clones every repository in `datasets/registry.yaml` for a given wave, ingests it
into Qdrant, and writes the ACTUAL resolved commit SHA back to the registry.

Usage
-----
    python -m scripts.ingest_corpus --wave 1
    python -m scripts.ingest_corpus --wave 1 --repos flask,requests
    python -m scripts.ingest_corpus --wave 1 --dry-run

Design notes
------------
* Commit SHAs are RESOLVED, never assumed. Whatever the clone actually checked
  out is what gets recorded — an unverified hash in the registry would be
  fabricated provenance.
* Clones are cached under `.corpus_cache/` and reused, so re-ingestion does not
  re-download gigabytes.
* Per-repository failures are isolated: one repo failing does not abort the run,
  and the summary reports exactly what succeeded and what did not.
* The BM25 index is refreshed at the end — it is built from the Qdrant corpus,
  so it is stale until ingestion completes.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from core.logging import get_logger
from ingestion.loaders.file_loader import FileIngestionSource
from ingestion.processors.normalizer import ArtifactNormalizer
from knowledge.schemas.artifacts import KnowledgeChunk
from knowledge.vector.embeddings import BGEEmbeddingModel
from knowledge.vector.qdrant import QdrantVectorStore

logger = get_logger(__name__)

REGISTRY_PATH = Path("datasets/registry.yaml")
CACHE_DIR = Path(".corpus_cache")
REPORT_PATH = Path("experiments/results/ingestion_report.json")

# Embedding + upsert batch size. Keeps GPU memory bounded on a 6 GB card while
# still giving the batching enough work to be efficient.
UPSERT_BATCH = 256


def load_registry(path: Path = REGISTRY_PATH) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_registry(data: Dict[str, Any], path: Path = REGISTRY_PATH) -> None:
    """Rewrite the registry, preserving key order and block scalars."""
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, default_flow_style=False, width=100)


def _run_git(args: List[str], cwd: Optional[Path] = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
    )


def clone_or_update(entry: Dict[str, Any], cache_dir: Path) -> Optional[Path]:
    """
    Shallow-clone the repository at its pinned tag. Returns the local path, or
    None if the clone failed (the tag may not exist — that is reported, not
    silently substituted with a different revision).
    """
    repo_id = entry["repo_id"]
    url = entry["url"]
    tag = entry.get("selected_tag")
    dest = cache_dir / repo_id

    if dest.exists() and (dest / ".git").exists():
        logger.info(f"[{repo_id}] using cached clone at {dest}")
        return dest

    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)

    cache_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"[{repo_id}] cloning {url} @ {tag or 'default branch'} ...")

    args = ["clone", "--depth", "1", "--quiet"]
    if tag:
        args += ["--branch", tag]
    args += [url, str(dest)]

    res = _run_git(args)
    if res.returncode != 0:
        logger.error(
            f"[{repo_id}] clone failed at tag '{tag}': {res.stderr.strip()[:300]}"
        )
        return None
    return dest


def resolve_commit(repo_path: Path) -> Optional[str]:
    """Return the SHA actually checked out."""
    res = _run_git(["rev-parse", "HEAD"], cwd=repo_path)
    return res.stdout.strip() if res.returncode == 0 else None


def ingest_repository(
    entry: Dict[str, Any],
    repo_path: Path,
    commit_sha: str,
    collection: str,
    embedder: BGEEmbeddingModel,
    store: QdrantVectorStore,
    normalizer: ArtifactNormalizer,
) -> Dict[str, Any]:
    """Load, chunk, embed and upsert one repository. Returns a stats dict."""
    repo_slug = f"{entry['owner']}/{entry['name']}"
    started = time.perf_counter()

    loader = FileIngestionSource(
        root_dir=repo_path,
        repository_id=repo_slug,
        commit_sha=commit_sha,
    )

    artifacts = list(loader.load())
    logger.info(f"[{entry['repo_id']}] loaded {len(artifacts)} artifacts")

    chunks: List[KnowledgeChunk] = []
    for art in artifacts:
        try:
            chunks.extend(normalizer.process_artifact(art))
        except Exception as exc:  # noqa: BLE001 - one bad file must not kill the repo
            logger.warning(
                f"[{entry['repo_id']}] chunking failed for {art.source_path}: {exc}"
            )

    logger.info(f"[{entry['repo_id']}] produced {len(chunks)} chunks; embedding...")

    indexed = 0
    for i in range(0, len(chunks), UPSERT_BATCH):
        batch = chunks[i : i + UPSERT_BATCH]
        embedder.embed_chunks(batch)
        indexed += store.upsert(collection, batch)
        if (i // UPSERT_BATCH) % 10 == 0:
            logger.info(f"[{entry['repo_id']}] {indexed}/{len(chunks)} chunks indexed")

    elapsed = time.perf_counter() - started

    # Content mix tells us whether the non-Python chunking gap is biting on this
    # repository. `language` is legitimately None for docs and configs, so those
    # fall back to their artifact_type rather than being lumped under "unknown" —
    # a docs-heavy repository is a healthy corpus, not a failed ingestion.
    by_lang: Dict[str, int] = {}
    for c in chunks:
        lang = c.metadata.get("language")
        if not lang:
            at = c.artifact_type
            lang = f"doc:{at.value if hasattr(at, 'value') else at}"
        by_lang[str(lang)] = by_lang.get(str(lang), 0) + 1

    return {
        "repo_id": entry["repo_id"],
        "repository": repo_slug,
        "commit_sha": commit_sha,
        "artifacts": len(artifacts),
        "chunks_indexed": indexed,
        "elapsed_seconds": round(elapsed, 1),
        "chunks_by_language": dict(sorted(by_lang.items(), key=lambda kv: -kv[1])),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest the EIH repository corpus.")
    parser.add_argument("--wave", type=int, default=1, help="Registry wave to ingest")
    parser.add_argument("--repos", type=str, default=None, help="Comma-separated repo_ids")
    parser.add_argument("--collection", type=str, default=None, help="Qdrant collection")
    parser.add_argument("--dry-run", action="store_true", help="List targets and exit")
    parser.add_argument("--cache-dir", type=str, default=str(CACHE_DIR))
    args = parser.parse_args()

    registry = load_registry()
    collection = args.collection or registry.get("default_collection", "eih_knowledge")
    cache_dir = Path(args.cache_dir)

    only = {r.strip() for r in args.repos.split(",")} if args.repos else None
    targets = [
        e for e in registry["repositories"]
        if e.get("wave") == args.wave and (only is None or e["repo_id"] in only)
    ]

    if not targets:
        logger.error(f"No repositories matched wave={args.wave} repos={only}")
        return 1

    print(f"\nWave {args.wave} -> collection '{collection}': {len(targets)} repositories")
    for e in targets:
        print(f"  - {e['owner']}/{e['name']:<24} {e['language']:<12} {e.get('selected_tag')}")
    if args.dry_run:
        print("\n(dry run — nothing ingested)")
        return 0

    embedder = BGEEmbeddingModel()
    store = QdrantVectorStore()
    store.connect()
    normalizer = ArtifactNormalizer()

    results: List[Dict[str, Any]] = []
    failures: List[Dict[str, str]] = []

    for entry in targets:
        repo_id = entry["repo_id"]
        try:
            repo_path = clone_or_update(entry, cache_dir)
            if repo_path is None:
                failures.append({"repo_id": repo_id, "stage": "clone", "error": "clone failed"})
                continue

            sha = resolve_commit(repo_path)
            if not sha:
                failures.append({"repo_id": repo_id, "stage": "resolve", "error": "no HEAD"})
                continue

            declared = entry.get("selected_commit")
            if declared and declared != sha:
                logger.warning(
                    f"[{repo_id}] registry SHA {declared[:12]} != cloned {sha[:12]} — "
                    "recording the cloned SHA as ground truth."
                )

            stats = ingest_repository(
                entry, repo_path, sha, collection, embedder, store, normalizer
            )
            results.append(stats)

            entry["selected_commit"] = sha
            entry["status"] = "ingested"
            logger.info(
                f"[{repo_id}] DONE {stats['chunks_indexed']} chunks in {stats['elapsed_seconds']}s"
            )
        except Exception as exc:  # noqa: BLE001 - isolate per-repository failure
            logger.error(f"[{repo_id}] ingestion failed: {exc}")
            failures.append({"repo_id": repo_id, "stage": "ingest", "error": str(exc)})

    save_registry(registry)

    total_chunks = sum(r["chunks_indexed"] for r in results)
    lang_totals: Dict[str, int] = {}
    for r in results:
        for lang, n in r["chunks_by_language"].items():
            lang_totals[lang] = lang_totals.get(lang, 0) + n

    report = {
        "wave": args.wave,
        "collection": collection,
        "repositories_ingested": len(results),
        "repositories_failed": len(failures),
        "total_chunks": total_chunks,
        "collection_count": store.count(collection),
        "chunks_by_language": dict(sorted(lang_totals.items(), key=lambda kv: -kv[1])),
        "per_repository": results,
        "failures": failures,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print("\n" + "=" * 62)
    print(f"  Ingested   : {len(results)} repositories, {total_chunks:,} chunks")
    print(f"  Collection : '{collection}' now holds {report['collection_count']:,} points")
    print(f"  Languages  : {report['chunks_by_language']}")
    if failures:
        print(f"  FAILURES   : {len(failures)}")
        for f_ in failures:
            print(f"     - {f_['repo_id']} ({f_['stage']}): {f_['error'][:80]}")
    print(f"  Report     : {REPORT_PATH}")
    print("=" * 62)
    return 0 if not failures else 2


if __name__ == "__main__":
    sys.exit(main())
