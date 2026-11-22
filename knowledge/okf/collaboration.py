"""
Human-agent collaboration on an OKF bundle: proposals, review, approval, audit.

The bundle on disk is the single shared knowledge store for people and agents. The rules:

1. **Agents only propose.** An agent (actor `<producer>/<version>`, OKF §7) can never write
   to the bundle. It files a proposal: the full proposed frontmatter + body, a rationale,
   the evidence it used, and the content hash of the concept it read (`base_hash`).
2. **Only humans decide.** Approve / reject / direct edit require a `human:<id>` actor.
3. **No silent overwrite.** On approval the concept's current hash must still equal the
   proposal's `base_hash`; if a person (or another approval) changed it in between, the
   proposal becomes `conflict` and nothing is written. Creating a concept that already
   exists is also a conflict. Direct human edits use the same optimistic check.
4. **Trust is recorded in OKF terms** (§5.2-5.3). Approved agent content gets
   `generated: {by: <agent>, at}` and `verified: [{by: human:<reviewer>, at}]`
   (human-reviewed tier). If the reviewer edited the text before approving, the content
   is theirs: `generated.by` becomes the reviewer. Unapproved agent text never enters
   the bundle, so it can never pass for verified knowledge.
5. **Everything is audited**: every action is appended to an audit JSONL, and every
   change to the bundle gets a `log.md` entry (§9).

Proposals and the audit trail live outside the bundle directory (``<state_dir>``) so the
bundle stays a plain, portable OKF tree.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from knowledge.okf.bundle import OKFBundle, validate_concept_id
from knowledge.okf.document import OKFDocument, is_valid_actor, utc_now_iso

PENDING, APPROVED, REJECTED, CONFLICT = "pending", "approved", "rejected", "conflict"
KINDS = ("create", "update", "deprecate")


class CollaborationError(ValueError):
    """A request that the workflow rules forbid (wrong actor, wrong state, bad input)."""


class ConcurrentEditError(CollaborationError):
    """The concept changed since the caller read it (optimistic concurrency)."""


@dataclass
class Proposal:
    id: str
    bundle: str
    kind: str
    concept_id: str
    proposed_frontmatter: Dict[str, Any]
    proposed_body: str
    rationale: str
    proposed_by: str
    created_at: str
    base_hash: Optional[str] = None
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    conflicts_with: List[str] = field(default_factory=list)
    status: str = PENDING
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[str] = None
    review_note: Optional[str] = None
    applied_hash: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _require_human(actor: str) -> None:
    if not (actor or "").startswith("human:") or len(actor) <= len("human:"):
        raise CollaborationError(f"this action requires a human actor 'human:<id>', got {actor!r}")


def _require_agent(actor: str) -> None:
    if not is_valid_actor(actor) or actor.startswith(("human:", "process:")):
        raise CollaborationError(f"proposals must come from an agent actor '<producer>/<version>', got {actor!r}")


class KnowledgeWorkspace:
    """One bundle plus its proposal store, audit trail and change listeners."""

    def __init__(self, bundle: OKFBundle, state_dir: Path | str, name: Optional[str] = None):
        self.bundle = bundle
        self.name = name or bundle.root.name
        self.state_dir = Path(state_dir) / self.name
        self.proposals_dir = self.state_dir / "proposals"
        self.proposals_dir.mkdir(parents=True, exist_ok=True)
        self.audit_path = self.state_dir / "audit.jsonl"
        self._listeners: List[Callable[[str, List[str]], None]] = []

    # ------------------------------------------------------------------ listeners

    def on_change(self, fn: Callable[[str, List[str]], None]) -> None:
        """Register fn(bundle_name, changed_concept_ids), called after every bundle write
        (used for incremental Qdrant / Neo4j sync)."""
        self._listeners.append(fn)

    def _changed(self, concept_ids: List[str]) -> List[Dict[str, str]]:
        failures = []
        for fn in self._listeners:
            try:
                fn(self.name, concept_ids)
            except Exception as exc:  # noqa: BLE001 - the write already happened; report, don't hide
                failures.append({"listener": getattr(fn, "__qualname__", str(fn)), "error": str(exc)})
                self._audit("sync_failed", "process:eih-okf-sync", {"concepts": concept_ids, "error": str(exc)})
        return failures

    # ------------------------------------------------------------------ audit

    def _audit(self, action: str, actor: str, details: Dict[str, Any]) -> None:
        rec = {"at": utc_now_iso(), "bundle": self.name, "action": action, "actor": actor, **details}
        with open(self.audit_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def audit_trail(self, concept_id: Optional[str] = None, limit: int = 200) -> List[Dict[str, Any]]:
        if not self.audit_path.exists():
            return []
        rows = [json.loads(l) for l in self.audit_path.read_text(encoding="utf-8").splitlines() if l.strip()]
        if concept_id:
            rows = [r for r in rows if r.get("concept_id") == concept_id or concept_id in (r.get("concepts") or [])]
        return rows[-limit:][::-1]

    # ------------------------------------------------------------------ proposal store

    def _path(self, pid: str) -> Path:
        if not pid.isalnum():
            raise CollaborationError(f"invalid proposal id {pid!r}")
        return self.proposals_dir / f"{pid}.json"

    def _save(self, p: Proposal) -> None:
        path = self._path(p.id)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(p.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)

    def get_proposal(self, pid: str) -> Proposal:
        path = self._path(pid)
        if not path.exists():
            raise KeyError(pid)
        return Proposal(**json.loads(path.read_text(encoding="utf-8")))

    def list_proposals(self, status: Optional[str] = None, concept_id: Optional[str] = None) -> List[Proposal]:
        out = []
        for f in self.proposals_dir.glob("*.json"):
            p = Proposal(**json.loads(f.read_text(encoding="utf-8")))
            if (status is None or p.status == status) and (concept_id is None or p.concept_id == concept_id):
                out.append(p)
        return sorted(out, key=lambda p: p.created_at, reverse=True)

    # ------------------------------------------------------------------ agent side

    def propose(
        self,
        *,
        kind: str,
        concept_id: str,
        frontmatter: Optional[Dict[str, Any]],
        body: Optional[str],
        rationale: str,
        actor: str,
        base_hash: Optional[str] = None,
        evidence: Optional[List[Dict[str, Any]]] = None,
        conflicts_with: Optional[List[str]] = None,
    ) -> Proposal:
        _require_agent(actor)
        if kind not in KINDS:
            raise CollaborationError(f"kind must be one of {KINDS}")
        cid = validate_concept_id(concept_id)
        current = self.bundle.get(cid)
        if kind == "create":
            if current is not None:
                raise CollaborationError(f"concept '{cid}' exists; propose an update instead")
            base_hash = None
        else:
            if current is None:
                raise CollaborationError(f"concept '{cid}' does not exist")
            if base_hash is None:
                base_hash = current.doc.content_hash()
        if kind == "deprecate":
            fm = dict(current.doc.frontmatter)
            fm["status"] = "deprecated"
            frontmatter, body = fm, current.doc.body
        fm = dict(frontmatter or {})
        for k in ("generated", "verified"):  # trust fields are set by the workflow, not the proposer
            fm.pop(k, None)
        doc = OKFDocument(frontmatter=fm, body=body or "")
        errors = doc.validate()
        if errors:
            raise CollaborationError(f"proposed concept is not OKF-conformant: {errors}")
        if not rationale.strip():
            raise CollaborationError("a proposal needs a rationale")
        p = Proposal(
            id=uuid.uuid4().hex, bundle=self.name, kind=kind, concept_id=cid,
            proposed_frontmatter=fm, proposed_body=doc.body, rationale=rationale.strip(),
            proposed_by=actor, created_at=utc_now_iso(), base_hash=base_hash,
            evidence=list(evidence or []), conflicts_with=list(conflicts_with or []),
        )
        self._save(p)
        self._audit("propose", actor, {"proposal_id": p.id, "kind": kind, "concept_id": cid})
        return p

    # ------------------------------------------------------------------ human side

    def approve(
        self,
        pid: str,
        reviewer: str,
        note: str = "",
        edited_frontmatter: Optional[Dict[str, Any]] = None,
        edited_body: Optional[str] = None,
    ) -> Dict[str, Any]:
        _require_human(reviewer)
        p = self.get_proposal(pid)
        if p.status != PENDING:
            raise CollaborationError(f"proposal {pid} is {p.status}, not pending")

        current = self.bundle.get(p.concept_id)
        conflict = None
        if p.kind == "create" and current is not None:
            conflict = "the concept was created by someone else after this proposal"
        elif p.kind != "create":
            if current is None:
                conflict = "the concept was removed after this proposal"
            elif current.doc.content_hash() != p.base_hash:
                conflict = "the concept changed after this proposal was made"
        if conflict:
            p.status, p.reviewed_by, p.reviewed_at, p.review_note = CONFLICT, reviewer, utc_now_iso(), conflict
            self._save(p)
            self._audit("conflict", reviewer, {"proposal_id": pid, "concept_id": p.concept_id, "reason": conflict})
            return {"status": CONFLICT, "reason": conflict, "proposal": p.to_dict()}

        edited = edited_frontmatter is not None or edited_body is not None
        fm = dict(edited_frontmatter if edited_frontmatter is not None else p.proposed_frontmatter)
        body = edited_body if edited_body is not None else p.proposed_body
        now = utc_now_iso()
        fm.pop("verified", None)
        fm["generated"] = {"by": reviewer if edited else p.proposed_by, "at": now}
        fm["verified"] = [{"by": reviewer, "at": now}]
        doc = OKFDocument(frontmatter=fm, body=body)
        if doc.validate():
            raise CollaborationError(f"approved content is not OKF-conformant: {doc.validate()}")

        self.bundle.write_concept(p.concept_id, doc)
        verb = {"create": "Creation", "update": "Update", "deprecate": "Deprecation"}[p.kind]
        title = doc.title(p.concept_id.rsplit("/", 1)[-1])
        self.bundle.append_log([
            f"**{verb}**: [{title}](/{p.concept_id}.md) proposed by `{p.proposed_by}`, "
            f"{'edited and ' if edited else ''}approved by `{reviewer}` (proposal {p.id[:8]})."
        ])
        self.bundle.regenerate_indexes()

        p.status, p.reviewed_by, p.reviewed_at, p.review_note = APPROVED, reviewer, now, note or None
        p.applied_hash = doc.content_hash()
        self._save(p)
        self._audit("approve", reviewer, {"proposal_id": pid, "concept_id": p.concept_id,
                                          "edited_by_reviewer": edited, "applied_hash": p.applied_hash})
        failures = self._changed([p.concept_id])
        return {"status": APPROVED, "proposal": p.to_dict(), "sync_failures": failures}

    def reject(self, pid: str, reviewer: str, note: str) -> Proposal:
        _require_human(reviewer)
        if not note.strip():
            raise CollaborationError("a rejection needs a reason")
        p = self.get_proposal(pid)
        if p.status != PENDING:
            raise CollaborationError(f"proposal {pid} is {p.status}, not pending")
        p.status, p.reviewed_by, p.reviewed_at, p.review_note = REJECTED, reviewer, utc_now_iso(), note.strip()
        self._save(p)
        self._audit("reject", reviewer, {"proposal_id": pid, "concept_id": p.concept_id, "note": note.strip()})
        return p

    def human_edit(
        self,
        concept_id: str,
        frontmatter: Dict[str, Any],
        body: str,
        actor: str,
        base_hash: Optional[str],
        summary: str = "",
    ) -> Dict[str, Any]:
        """A person writes a concept directly (create when base_hash is None)."""
        _require_human(actor)
        cid = validate_concept_id(concept_id)
        current = self.bundle.get(cid)
        if current is None and base_hash is not None:
            raise ConcurrentEditError(f"concept '{cid}' no longer exists")
        if current is not None and current.doc.content_hash() != base_hash:
            raise ConcurrentEditError(f"concept '{cid}' changed since you opened it; reload and re-apply")
        fm = dict(frontmatter)
        now = utc_now_iso()
        fm["generated"] = {"by": actor, "at": now}
        # Hand-written content is human-reviewed by its author (§7: human: actors for
        # hand-authored content). Earlier verifications were of the old text.
        fm["verified"] = [{"by": actor, "at": now}]
        doc = OKFDocument(frontmatter=fm, body=body)
        self.bundle.write_concept(cid, doc)
        verb = "Creation" if current is None else "Update"
        self.bundle.append_log([f"**{verb}**: [{doc.title(cid)}](/{cid}.md) edited by `{actor}`"
                                + (f": {summary.strip()}" if summary.strip() else ".")])
        self.bundle.regenerate_indexes()
        self._audit("human_edit", actor, {"concept_id": cid, "created": current is None,
                                          "applied_hash": doc.content_hash(), "summary": summary})
        failures = self._changed([cid])
        return {"concept_id": cid, "hash": doc.content_hash(), "sync_failures": failures}
