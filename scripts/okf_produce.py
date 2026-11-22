"""
Produce, validate and sync OKF bundles (WORK_PLAN step 24a, change C33).

    python -m scripts.okf_produce produce            # build/refresh okf_bundles/eih from wave-1 + contract + docs
    python -m scripts.okf_produce validate PATH      # conformance report for any bundle (external ones too)
    python -m scripts.okf_produce sync [--bundle eih]   # full re-projection into Qdrant (eih_okf) and Neo4j
    python -m scripts.okf_produce import PATH [--name NAME]  # copy an external bundle in, validate, sync

The research collection and the engineering graph are never written (see knowledge/okf/sync.py).
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from core.config import PROJECT_ROOT, settings
from knowledge.okf.bundle import OKFBundle

# Project documents mirrored into the bundle (the agent can then answer about EIH itself).
DOCS = ["README.md", "docs/PROJECT_REPORT.md", "docs/API_CONTRACT.md", "docs/retrieval.md",
        "docs/knowledge_graph.md", "docs/quality_verification.md", "docs/sustainability_measurement.md",
        "docs/task_intelligence.md", "docs/ingestion.md", "docs/evaluation.md", "docs/okf.md"]


def _sync(bundle: OKFBundle, name: str) -> dict:
    from knowledge.okf.sync import OKFGraphProjection, OKFVectorIndex

    out = {"qdrant": OKFVectorIndex().sync_bundle(bundle, name)}
    out["neo4j"] = OKFGraphProjection().sync_bundle(bundle, name)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("produce")
    p.add_argument("--bundle", default=settings.okf.default_bundle)
    p.add_argument("--wave", type=int, default=1)
    p.add_argument("--no-sync", action="store_true")
    v = sub.add_parser("validate")
    v.add_argument("path")
    s = sub.add_parser("sync")
    s.add_argument("--bundle", default=settings.okf.default_bundle)
    i = sub.add_parser("import")
    i.add_argument("path")
    i.add_argument("--name")
    i.add_argument("--no-sync", action="store_true")
    args = ap.parse_args()

    if args.cmd == "validate":
        rep = OKFBundle(args.path).conformance().to_dict()
        print(json.dumps(rep, indent=2))
        return 0 if rep["conformant"] else 1

    if args.cmd == "produce":
        from knowledge.okf.producer import produce_eih_bundle

        docs = [PROJECT_ROOT / d for d in DOCS if (PROJECT_ROOT / d).exists()]
        bundle, rep = produce_eih_bundle(settings.okf.root / args.bundle, PROJECT_ROOT,
                                         PROJECT_ROOT / "datasets" / "registry.yaml",
                                         PROJECT_ROOT / ".corpus_cache", args.wave, docs)
        conf = bundle.conformance()
        print(json.dumps({"produce": rep.to_dict(), "concepts": conf.concepts, "conformant": conf.conformant,
                          "errors": len(conf.errors), "broken_links": len(conf.broken_links),
                          "edges": len(bundle.concept_edges()), "types": bundle.types()}, indent=2))
        if not conf.conformant:
            return 1
        if not args.no_sync:
            print(json.dumps(_sync(bundle, args.bundle), indent=2))
        return 0

    if args.cmd == "sync":
        bundle = OKFBundle(settings.okf.root / args.bundle)
        print(json.dumps(_sync(bundle, args.bundle), indent=2))
        return 0

    if args.cmd == "import":
        src = Path(args.path).resolve()
        name = args.name or src.name
        dest = settings.okf.root / name
        if dest.exists():
            print(f"refusing to overwrite existing bundle '{name}' at {dest}", file=sys.stderr)
            return 2
        rep = OKFBundle(src).conformance()
        shutil.copytree(src, dest, ignore=shutil.ignore_patterns(".git"))
        bundle = OKFBundle(dest)
        print(json.dumps(rep.to_dict() | {"imported_as": name}, indent=2))
        if not args.no_sync:
            print(json.dumps(_sync(bundle, name), indent=2))
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
