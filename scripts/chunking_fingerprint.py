"""
Fingerprint how a corpus wave is chunked, without embedding or writing to Qdrant.

Chunks every repository of a wave exactly as `scripts.ingest_corpus` does (same loader,
normalizer and chunker selection) and hashes each chunk's id, content, line range and
metadata. Used to prove that a chunking change leaves a frozen wave byte-identical
(WORK_PLAN step 16, ASK_ME T16 option (a): wave 1 must not change).

    python -m scripts.chunking_fingerprint --wave 1 --out PATH
    python -m scripts.chunking_fingerprint --wave 1 --compare PATH   # exit 1 on any difference
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import yaml

from ingestion.loaders.file_loader import FileIngestionSource
from ingestion.processors.normalizer import ArtifactNormalizer


def fingerprint(wave: int, cache: Path = Path(".corpus_cache")) -> dict:
    from scripts.ingest_corpus import normalizer_for

    registry = yaml.safe_load(Path("datasets/registry.yaml").read_text(encoding="utf-8"))
    per_repo, total = {}, hashlib.sha256()
    for e in registry["repositories"]:
        if e.get("wave") != wave or not (cache / e["repo_id"] / ".git").exists():
            continue
        normalizer: ArtifactNormalizer = normalizer_for(e)
        h, n = hashlib.sha256(), 0
        src = FileIngestionSource(root_dir=cache / e["repo_id"], repository_id=f"{e['owner']}/{e['name']}",
                                  commit_sha=e.get("selected_commit") or "")
        for art in src.load():
            for c in normalizer.process_artifact(art):
                rec = json.dumps({"id": c.chunk_id, "content": c.content, "start": c.start_line, "end": c.end_line,
                                  "tokens": c.token_count, "meta": c.metadata}, sort_keys=True, default=str)
                h.update(rec.encode("utf-8"))
                n += 1
        per_repo[e["repo_id"]] = {"chunks": n, "sha256": h.hexdigest()}
        total.update(h.hexdigest().encode())
    return {"wave": wave, "repositories": per_repo, "total_chunks": sum(r["chunks"] for r in per_repo.values()),
            "sha256": total.hexdigest()}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wave", type=int, default=1)
    ap.add_argument("--out")
    ap.add_argument("--compare")
    args = ap.parse_args()
    fp = fingerprint(args.wave)
    print(json.dumps(fp, indent=2))
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(fp, indent=2) + "\n", encoding="utf-8")
    if args.compare:
        ref = json.loads(Path(args.compare).read_text(encoding="utf-8"))
        same = ref["sha256"] == fp["sha256"] and ref["repositories"] == fp["repositories"]
        print("IDENTICAL" if same else "DIFFERENT")
        return 0 if same else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
