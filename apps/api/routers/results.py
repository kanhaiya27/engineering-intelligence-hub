"""
Read-only access to measured research results (experiments/results/**.json) for the
evaluation dashboard. The dashboard shows only files that real runs wrote, with their
provenance (machine, date, driver, git commit); it never computes or fills in numbers.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Query

from core.config import PROJECT_ROOT

router = APIRouter(prefix="/results", tags=["Research results"])

RESULTS = (PROJECT_ROOT / "experiments" / "results").resolve()
MAX_BYTES = 20 * 1024 * 1024


def _provenance(d: Dict[str, Any]) -> Dict[str, Any]:
    p = d.get("provenance") if isinstance(d.get("provenance"), dict) else {}
    gpu = p.get("gpu") if isinstance(p.get("gpu"), dict) else {}
    git = p.get("git") if isinstance(p.get("git"), dict) else {}
    return {"recorded_at_utc": p.get("recorded_at_utc"), "machine_id": p.get("machine_id"),
            "gpu_driver": gpu.get("driver"), "git_sha": (git.get("sha") or "")[:12] or None,
            "git_dirty": git.get("dirty")}


@router.get("")
def list_results(prefix: str = "") -> List[Dict[str, Any]]:
    out = []
    for p in sorted(RESULTS.rglob("*.json")):
        rel = p.relative_to(RESULTS).as_posix()
        if prefix and not rel.startswith(prefix):
            continue
        item: Dict[str, Any] = {"path": rel, "bytes": p.stat().st_size, "group": rel.split("/", 1)[0]}
        if p.stat().st_size <= MAX_BYTES:
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(d, dict):
                    item["study"] = d.get("study") or d.get("experiment") or d.get("name")
                    item["keys"] = list(d.keys())[:20]
                    item["provenance"] = _provenance(d)
            except (json.JSONDecodeError, UnicodeDecodeError):
                item["unreadable"] = True
        out.append(item)
    return out


@router.get("/file")
def get_result(path: str = Query(..., max_length=300)) -> Any:
    target = (RESULTS / path).resolve()
    if RESULTS not in target.parents or target.suffix != ".json" or not target.is_file():
        raise HTTPException(404, "result file not found")
    if target.stat().st_size > MAX_BYTES:
        raise HTTPException(413, "result file too large for the dashboard")
    return json.loads(target.read_text(encoding="utf-8"))
