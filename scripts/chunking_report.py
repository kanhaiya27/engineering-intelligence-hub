"""
Validate tree-sitter chunking on real repositories (WORK_PLAN step 16). No embedding, no
Qdrant writes; clones go to `.corpus_cache` at the registry's pinned tag.

For each repository and language it reports: files, chunks, how many chunks came from
tree-sitter symbol units vs the line window, parse-error fallbacks, the largest chunk in
embedding tokens (must be <= 512, the step-4 rule) and line coverage (every non-empty line
of every code file must be inside some chunk). The same files are also chunked with the
wave-1 line window for comparison.

    python -m scripts.chunking_report --repos gson,express,gin,cobra,serde,zstd
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import yaml

from core.config import PROJECT_ROOT
from experiments.provenance import collect_provenance, write_json
from ingestion.loaders.file_loader import FileIngestionSource
from ingestion.processors.chunker import CodeAwareChunker, UniversalChunker
from ingestion.processors.normalizer import ArtifactNormalizer
from ingestion.processors.syntax_chunker import CHUNKER_ID, TreeSitterService, language_id
from scripts.ingest_corpus import clone_or_update, resolve_commit

OUT = PROJECT_ROOT / "experiments" / "results" / "chunking"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repos", required=True)
    ap.add_argument("--out", default=str(OUT / "tree_sitter_report.json"))
    args = ap.parse_args()
    wanted = [r.strip() for r in args.repos.split(",") if r.strip()]
    registry = {e["repo_id"]: e for e in yaml.safe_load((PROJECT_ROOT / "datasets/registry.yaml").read_text(encoding="utf-8"))["repositories"]}
    results, t0 = {}, time.perf_counter()
    with TreeSitterService() as ts:
        for rid in wanted:
            e = registry[rid]
            path = clone_or_update(e, PROJECT_ROOT / ".corpus_cache")
            if path is None:
                results[rid] = {"error": "clone failed"}
                continue
            sha = resolve_commit(path)
            syn = ArtifactNormalizer(chunker=UniversalChunker(code_chunker=CodeAwareChunker(syntax=ts)))
            win = ArtifactNormalizer()
            per_lang = defaultdict(lambda: {"files": 0, "chunks": 0, "tree_sitter_chunks": 0, "window_chunks": 0,
                                            "fallback_no_definitions": 0, "fallback_other": 0, "files_with_parse_errors_kept": 0, "max_tokens": 0, "uncovered_lines": 0,
                                            "window_baseline_chunks": 0})
            for art in FileIngestionSource(root_dir=path, repository_id=f"{e['owner']}/{e['name']}", commit_sha=sha).load():
                lang = language_id(getattr(art, "language", None), art.source_path)
                if lang is None:
                    continue
                raw = art.raw_content
                chunks = syn.process_artifact(art)
                if not chunks:
                    continue
                art2 = art.model_copy(deep=True)
                art2.raw_content = raw
                art2.metadata = {}
                baseline = win.process_artifact(art2)
                s = per_lang[lang]
                s["files"] += 1
                s["chunks"] += len(chunks)
                s["window_baseline_chunks"] += len(baseline)
                s["tree_sitter_chunks"] += sum(c.metadata.get("chunker") == CHUNKER_ID for c in chunks)
                s["window_chunks"] += sum(c.metadata.get("chunker") != CHUNKER_ID for c in chunks)
                fb = art.metadata.get("syntax_fallback")
                s["fallback_no_definitions"] += int(fb == "no_definitions")
                s["fallback_other"] += int(fb is not None and fb != "no_definitions")
                s["files_with_parse_errors_kept"] += int(any(c.metadata.get("parse_errors") for c in chunks))
                s["max_tokens"] = max(s["max_tokens"], max(c.token_count or 0 for c in chunks))
                covered = set()
                for c in chunks:
                    covered.update(range(c.start_line, c.end_line + 1))
                lines = art.raw_content.splitlines()
                s["uncovered_lines"] += sum(1 for i, l in enumerate(lines, 1) if l.strip() and i not in covered)
            results[rid] = {"repository": f"{e['owner']}/{e['name']}", "tag": e.get("selected_tag"), "commit": sha,
                            "by_language": dict(per_lang)}
            print(rid, json.dumps(dict(per_lang)), flush=True)
    data = {"study": "tree_sitter_chunking_validation", "provenance": collect_provenance(include_ollama=False),
            "config": {"repos": wanted, "max_tokens_per_chunk": 512, "parser": "web-tree-sitter 0.27.2 (WASM)"},
            "results": results, "seconds": round(time.perf_counter() - t0, 1)}
    write_json(Path(args.out), data)
    bad = [(r, l) for r, v in results.items() for l, s in v.get("by_language", {}).items()
           if s["max_tokens"] > 512 or s["uncovered_lines"]]
    print("VIOLATIONS:", bad or "none")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
