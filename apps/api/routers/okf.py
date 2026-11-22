"""
OKF knowledge API: the shared bundle that people (through the UI) and the agent both use.

Read: bundles, concepts, search (lexical over files; semantic via Qdrant), links,
backlinks, graph, conformance, log, audit. Write (humans only, `human:<id>`): edit /
create concepts with optimistic concurrency, approve / reject agent proposals.
Import (zip upload) / export (zip download) for portability. No endpoint lets the agent
write to a bundle directly.
"""

from __future__ import annotations

import io
import re
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from apps.api import services
from core.config import settings
from knowledge.okf.bundle import OKFBundle, OKFPathError
from knowledge.okf.collaboration import CollaborationError, ConcurrentEditError

router = APIRouter(prefix="/okf", tags=["OKF Knowledge"])

_ACTOR = r"^human:[A-Za-z0-9_.@\-]{1,64}$"
_NAME_RX = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.\-]{0,63}$")
MAX_IMPORT_BYTES = 50 * 1024 * 1024


class EditRequest(BaseModel):
    frontmatter: Dict[str, Any]
    body: str = Field(default="", max_length=500_000)
    base_hash: Optional[str] = Field(default=None, description="content_hash you edited; null to create")
    actor: str = Field(pattern=_ACTOR)
    summary: str = Field(default="", max_length=500)


class ReviewRequest(BaseModel):
    reviewer: str = Field(pattern=_ACTOR)
    note: str = Field(default="", max_length=2000)
    edited_frontmatter: Optional[Dict[str, Any]] = None
    edited_body: Optional[str] = Field(default=None, max_length=500_000)


def _summary(c) -> Dict[str, Any]:
    d = c.doc
    return {"id": c.id, "title": c.title, "type": d.type, "description": d.description, "tags": d.tags,
            "status": d.status, "trust_tier": d.trust_tier, "stale": d.is_stale(),
            "generated_by": d.generated_by, "generated_at": d.generated_at}


# ---------------------------------------------------------------------- bundles


@router.get("/bundles")
def list_bundles() -> List[Dict[str, Any]]:
    out = []
    for name in services.bundle_names():
        ws = services.workspace(name)
        rep = ws.bundle.conformance()
        out.append({"name": name, "concepts": rep.concepts, "conformant": rep.conformant,
                    "errors": len(rep.errors), "broken_links": len(rep.broken_links),
                    "declared_okf_version": rep.declared_version, "types": ws.bundle.types(),
                    "pending_proposals": len(ws.list_proposals(status="pending")),
                    "default": name == settings.okf.default_bundle})
    return out


@router.get("/bundles/{bundle}/conformance")
def conformance(bundle: str) -> Dict[str, Any]:
    ws = services.workspace(bundle)
    ws.bundle.reload()
    return ws.bundle.conformance().to_dict()


@router.post("/bundles/{bundle}/reload")
def reload_bundle(bundle: str) -> Dict[str, Any]:
    """Re-read the files (after edits made outside EIH, e.g. in a text editor or git pull)."""
    ws = services.workspace(bundle)
    before = {cid: c.doc.content_hash() for cid, c in ws.bundle.concepts.items()}
    ws.bundle.reload()
    after = {cid: c.doc.content_hash() for cid, c in ws.bundle.concepts.items()}
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    failures = ws._changed(changed) if changed else []
    return {"changed": changed, "sync_failures": failures}


@router.get("/bundles/{bundle}/tree")
def tree(bundle: str) -> Dict[str, Any]:
    """Directory hierarchy with concept summaries (progressive disclosure, OKF §8)."""
    ws = services.workspace(bundle)
    root: Dict[str, Any] = {"name": bundle, "path": "", "dirs": {}, "concepts": []}
    for c in sorted(ws.bundle.concepts.values(), key=lambda c: c.id):
        node = root
        parts = c.id.split("/")
        for i, part in enumerate(parts[:-1]):
            node = node["dirs"].setdefault(part, {"name": part, "path": "/".join(parts[: i + 1]), "dirs": {},
                                                  "concepts": []})
        node["concepts"].append({"id": c.id, "title": c.title, "type": c.doc.type, "trust_tier": c.doc.trust_tier,
                                 "status": c.doc.status})

    def finish(n):
        n["dirs"] = [finish(d) for _, d in sorted(n["dirs"].items())]
        n["count"] = len(n["concepts"]) + sum(d["count"] for d in n["dirs"])
        return n
    return finish(root)


@router.get("/bundles/{bundle}/concepts")
def search_concepts(bundle: str, q: str = "", type: Optional[str] = None, tag: Optional[str] = None,
                    limit: int = Query(50, ge=1, le=500)) -> Dict[str, Any]:
    ws = services.workspace(bundle)
    hits = ws.bundle.search(q, limit=limit, type_filter=type, tag=tag)
    return {"query": q, "mode": "lexical", "total": len(hits),
            "results": [_summary(c) | {"score": s} for c, s in hits],
            "types": ws.bundle.types(), "tags": ws.bundle.tags()}


@router.get("/bundles/{bundle}/semantic")
def semantic_search(bundle: str, q: str = Query(..., min_length=2), limit: int = Query(10, ge=1, le=50)):
    services.workspace(bundle)
    try:
        hits = services.vector_index().search(q, bundle=bundle, limit=limit)
    except Exception as exc:  # noqa: BLE001
        raise services.unavailable("Qdrant", exc)
    seen, out = set(), []
    for h in hits:
        if h["concept_id"] in seen:
            continue
        seen.add(h["concept_id"])
        out.append({"id": h["concept_id"], "title": h.get("title"), "type": h.get("type"),
                    "section": h.get("section"), "trust_tier": h.get("trust_tier"), "score": round(h["score"], 4)})
    return {"query": q, "mode": "semantic", "results": out}


@router.get("/bundles/{bundle}/concept/{concept_id:path}")
def get_concept(bundle: str, concept_id: str) -> Dict[str, Any]:
    ws = services.workspace(bundle)
    c = ws.bundle.get(concept_id)
    if c is None:
        raise HTTPException(404, f"concept '{concept_id}' not found")
    d = c.doc
    out = [{"text": l.text, "target": l.target_raw, "resolved": l.target, "external": l.external, "broken": l.broken}
           for l in ws.bundle.outgoing(c.id)]
    back = sorted({l.source for l in ws.bundle.backlinks(c.id)})
    return {
        **_summary(c), "frontmatter": d.frontmatter, "body": d.body, "content_hash": d.content_hash(),
        "path": c.path.relative_to(ws.bundle.root).as_posix(),
        "warnings": d.warnings(), "errors": d.validate(),
        "links": out, "backlinks": [_summary(ws.bundle.get(b)) for b in back if ws.bundle.get(b)],
        "sources": d.frontmatter.get("sources") or [],
        "pending_proposals": [p.id for p in ws.list_proposals(status="pending", concept_id=c.id)],
        "history": ws.audit_trail(concept_id=c.id, limit=50),
    }


@router.put("/bundles/{bundle}/concept/{concept_id:path}")
def edit_concept(bundle: str, concept_id: str, req: EditRequest) -> Dict[str, Any]:
    ws = services.workspace(bundle)
    try:
        return ws.human_edit(concept_id, req.frontmatter, req.body, req.actor, req.base_hash, req.summary)
    except ConcurrentEditError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    except (CollaborationError, OKFPathError, ValueError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.get("/bundles/{bundle}/graph")
def concept_graph(bundle: str, center: Optional[str] = None, hops: int = Query(1, ge=1, le=3),
                  limit: int = Query(400, ge=1, le=3000)) -> Dict[str, Any]:
    """Concept link graph from the bundle files (the source of truth)."""
    ws = services.workspace(bundle)
    b = ws.bundle
    if center:
        if b.get(center) is None:
            raise HTTPException(404, f"concept '{center}' not found")
        ids = set([center] + b.neighbours(center, hops=hops))
    else:
        degree: Dict[str, int] = {}
        for a, t in b.concept_edges():
            degree[a] = degree.get(a, 0) + 1
            degree[t] = degree.get(t, 0) + 1
        ids = set(sorted(b.concepts, key=lambda c: (-degree.get(c, 0), c))[:limit])
    edges = [{"source": a, "target": t} for a, t in b.concept_edges() if a in ids and t in ids]
    nodes = [_summary(b.get(i)) for i in sorted(ids)][:limit]
    return {"center": center, "nodes": nodes, "edges": edges, "total_concepts": len(b.concepts)}


@router.get("/bundles/{bundle}/log")
def bundle_log(bundle: str) -> Dict[str, Any]:
    ws = services.workspace(bundle)
    p = ws.bundle.root / "log.md"
    return {"log": p.read_text(encoding="utf-8") if p.exists() else "", "audit": ws.audit_trail(limit=200)}


# ---------------------------------------------------------------------- proposals


@router.get("/bundles/{bundle}/proposals")
def list_proposals(bundle: str, status_filter: Optional[str] = Query(None, alias="status")):
    ws = services.workspace(bundle)
    return [p.to_dict() for p in ws.list_proposals(status=status_filter)]


@router.get("/bundles/{bundle}/proposals/{pid}")
def get_proposal(bundle: str, pid: str) -> Dict[str, Any]:
    ws = services.workspace(bundle)
    try:
        p = ws.get_proposal(pid)
    except (KeyError, CollaborationError):
        raise HTTPException(404, "proposal not found")
    cur = ws.bundle.get(p.concept_id)
    return {"proposal": p.to_dict(),
            "current": None if cur is None else {"frontmatter": cur.doc.frontmatter, "body": cur.doc.body,
                                                 "content_hash": cur.doc.content_hash()},
            "stale": cur is not None and p.base_hash is not None and cur.doc.content_hash() != p.base_hash}


@router.post("/bundles/{bundle}/proposals/{pid}/approve")
def approve(bundle: str, pid: str, req: ReviewRequest) -> Dict[str, Any]:
    ws = services.workspace(bundle)
    try:
        return ws.approve(pid, req.reviewer, req.note, req.edited_frontmatter, req.edited_body)
    except KeyError:
        raise HTTPException(404, "proposal not found")
    except (CollaborationError, ValueError) as exc:
        raise HTTPException(400, str(exc))


@router.post("/bundles/{bundle}/proposals/{pid}/reject")
def reject(bundle: str, pid: str, req: ReviewRequest) -> Dict[str, Any]:
    ws = services.workspace(bundle)
    try:
        return ws.reject(pid, req.reviewer, req.note).to_dict()
    except KeyError:
        raise HTTPException(404, "proposal not found")
    except CollaborationError as exc:
        raise HTTPException(400, str(exc))


# ---------------------------------------------------------------------- sync / portability


@router.post("/bundles/{bundle}/sync")
def sync_bundle(bundle: str) -> Dict[str, Any]:
    ws = services.workspace(bundle)
    ws.bundle.reload()
    try:
        q = services.vector_index().sync_bundle(ws.bundle, bundle)
    except Exception as exc:  # noqa: BLE001
        raise services.unavailable("Qdrant", exc)
    g = services.graph_projection().sync_bundle(ws.bundle, bundle)
    return {"qdrant": q, "neo4j": g}


@router.get("/bundles/{bundle}/export")
def export_bundle(bundle: str) -> StreamingResponse:
    """The bundle as a plain zip of markdown files: readable without EIH (OKF §3)."""
    ws = services.workspace(bundle)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(ws.bundle.root.rglob("*")):
            if p.is_file() and not any(part.startswith(".") for part in p.relative_to(ws.bundle.root).parts):
                zf.write(p, f"{bundle}/{p.relative_to(ws.bundle.root).as_posix()}")
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/zip",
                             headers={"Content-Disposition": f'attachment; filename="{bundle}.okf.zip"'})


@router.post("/import")
async def import_bundle(name: str = Query(..., pattern=_NAME_RX.pattern), file: UploadFile = File(...),
                        sync: bool = True) -> Dict[str, Any]:
    """Import an externally produced OKF bundle (zip). Validated, never merged into an existing bundle."""
    dest = Path(settings.okf.root) / name
    if dest.exists():
        raise HTTPException(409, f"bundle '{name}' already exists")
    data = await file.read(MAX_IMPORT_BYTES + 1)
    if len(data) > MAX_IMPORT_BYTES:
        raise HTTPException(413, "bundle archive larger than 50 MB")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp).resolve()
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                for info in zf.infolist():
                    target = (tmp_root / info.filename).resolve()
                    if tmp_root not in target.parents and target != tmp_root:
                        raise HTTPException(400, f"unsafe path in archive: {info.filename}")
                zf.extractall(tmp_root)
        except zipfile.BadZipFile:
            raise HTTPException(400, "not a zip archive")
        entries = [p for p in tmp_root.iterdir() if not p.name.startswith(("__MACOSX", "."))]
        src = entries[0] if len(entries) == 1 and entries[0].is_dir() else tmp_root
        if not any(src.rglob("*.md")):
            raise HTTPException(400, "archive contains no markdown files")
        report = OKFBundle(src).conformance().to_dict()
        Path(settings.okf.root).mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dest, ignore=shutil.ignore_patterns(".git", "__MACOSX"))
    services.forget_workspace(name)
    ws = services.workspace(name)
    synced = None
    if sync:
        try:
            synced = {"qdrant": services.vector_index().sync_bundle(ws.bundle, name),
                      "neo4j": services.graph_projection().sync_bundle(ws.bundle, name)}
        except HTTPException as exc:
            synced = {"error": exc.detail}
        except Exception as exc:  # noqa: BLE001
            synced = {"error": str(exc)}
    return {"imported_as": name, "conformance": report, "sync": synced}
