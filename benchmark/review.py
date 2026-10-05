"""
Benchmark review queue (EIH-SWE human approval, plan §8.2; master prompt 2026-10-05 review rules).

Every task needs a named human approval against the pinned code before it counts. This module
holds the review queue and the decisions:

  benchmark/data/review/reviewers.yaml          the roster (only these names may decide)
  benchmark/data/review/queue/<batch>.json      batches of <= 25 items, each with the exact
                                                file+line snippets the reviewer checks
  benchmark/data/review/decisions/<who>.jsonl   append-only, one file per reviewer, so
                                                reviewers never edit the same file

Four checks per item: the question is clear, the answer is correct against the pinned code,
the evidence file+line is right, the stage/type labels fit. Outcomes: approve (all four pass),
fix (with a note), reject (with a reason).

Rules enforced here, not by convention:
  * no self-approval: whoever drafted or requested an item can never decide on it;
  * held-out items (test split, EIH-Fresh, external held-out) need two different reviewers;
  * a decision is bound to the sha256 of what was shown, so editing an item voids old decisions;
  * every decision records reviewer, minutes spent and timestamp.
"""

from __future__ import annotations

import hashlib
import itertools
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

REPO_ROOT = Path(__file__).resolve().parents[1]
REVIEW_DIR = REPO_ROOT / "benchmark" / "data" / "review"
BATCH_SIZE = 25
REJECT_ALERT_RATE = 0.30
HELD_OUT_SPLITS = ("test", "fresh", "external_heldout")
CHECKS = ("question_clear", "answer_correct", "evidence_correct", "labels_fit")
DECISIONS = ("approve", "fix", "reject")


class ReviewError(ValueError):
    """A decision or queue operation that breaks a review rule."""


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class EvidenceSnippet(BaseModel):
    file: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    text: str = Field(description="The exact lines at the pinned commit, as shown to the reviewer")
    span_sha256: str


class ReviewItem(BaseModel):
    item_id: str = Field(description="Task id")
    kind: str = Field(description="new_task | existing_task")
    split: str = Field(description="dev | val | test | fresh | external_heldout | unassigned")
    repository: str
    commit_sha: str
    sdlc_stage: str
    task_type: str
    complexity: Optional[str] = None
    criticality: Optional[str] = None
    query: str
    proposed_answer: str
    acceptable_alternatives: List[str] = Field(default_factory=list)
    evidence: List[EvidenceSnippet]
    drafted_by: str = Field(description="Person or tool that wrote the item")
    requested_by: Optional[str] = Field(default=None, description="Person who asked for the draft")
    status_note: str = Field(default="drafted", description="LLM drafts stay 'drafted' until approved")

    @property
    def required_reviews(self) -> int:
        return 2 if self.split in HELD_OUT_SPLITS else 1

    def content_sha(self) -> str:
        """sha256 of exactly what the reviewer judges (not who drafted it)."""
        shown = self.model_dump(include={"repository", "commit_sha", "sdlc_stage", "task_type", "complexity",
                                         "criticality", "query", "proposed_answer", "acceptable_alternatives",
                                         "evidence"})
        return "sha256:" + hashlib.sha256(json.dumps(shown, sort_keys=True).encode("utf-8")).hexdigest()


class ReviewBatch(BaseModel):
    batch_id: str
    created_at: str
    purpose: str = Field(description="calibration | review | test_correctness_pass")
    assigned_to: List[str] = Field(default_factory=list)
    items: List[ReviewItem]

    @field_validator("items")
    @classmethod
    def _size(cls, items: List[ReviewItem]) -> List[ReviewItem]:
        if not 0 < len(items) <= BATCH_SIZE:
            raise ValueError(f"a batch holds 1..{BATCH_SIZE} items, got {len(items)}")
        if len({i.item_id for i in items}) != len(items):
            raise ValueError("duplicate item_id in batch")
        return items


class Decision(BaseModel):
    item_id: str
    batch_id: str
    item_sha: str
    reviewer: str
    decision: str
    checks: Dict[str, bool]
    note: Optional[str] = None
    minutes_spent: float = Field(gt=0)
    decided_at: str

    @model_validator(mode="after")
    def _consistent(self) -> "Decision":
        if self.decision not in DECISIONS:
            raise ValueError(f"decision must be one of {DECISIONS}")
        if set(self.checks) != set(CHECKS):
            raise ValueError(f"checks must be exactly {CHECKS}")
        if self.decision == "approve" and not all(self.checks.values()):
            raise ValueError("approve means all four checks pass; use fix or reject otherwise")
        if self.decision != "approve":
            if not (self.note or "").strip():
                raise ValueError(f"'{self.decision}' needs a note saying what is wrong")
            if all(self.checks.values()):
                raise ValueError(f"'{self.decision}' must name at least one failed check")
        return self


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


def _norm(name: str) -> str:
    return " ".join(name.lower().split())


def is_author(reviewer: str, item: "ReviewItem") -> bool:
    """True if the reviewer drafted or requested the item (full or first name match)."""
    who = {_norm(x) for x in (item.drafted_by, item.requested_by or "") if x}
    r = _norm(reviewer)
    return r in who or r.split()[0] in {w.split()[0] for w in who}


class ReviewStore:
    def __init__(self, root: Path = REVIEW_DIR) -> None:
        self.root = Path(root)

    # --- paths
    @property
    def queue_dir(self) -> Path:
        return self.root / "queue"

    @property
    def decisions_dir(self) -> Path:
        return self.root / "decisions"

    @property
    def sessions_dir(self) -> Path:
        return self.root / ".sessions"

    # --- roster
    def reviewers(self) -> List[str]:
        path = self.root / "reviewers.yaml"
        if not path.exists():
            return []
        return list((yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("reviewers", []))

    def resolve_reviewer(self, name: str) -> str:
        """Roster name matching `name` (case-insensitive, full name or first name)."""
        hits = [r for r in self.reviewers() if _norm(r) == _norm(name) or _norm(r).split()[0] == _norm(name)]
        if len(hits) != 1:
            raise ReviewError(f"'{name}' is not exactly one reviewer in reviewers.yaml: {self.reviewers()}")
        return hits[0]

    # --- batches
    def batches(self) -> List[ReviewBatch]:
        if not self.queue_dir.exists():
            return []
        return [ReviewBatch.model_validate_json(p.read_text(encoding="utf-8"))
                for p in sorted(self.queue_dir.glob("*.json"))]

    def save_batch(self, batch: ReviewBatch, overwrite: bool = False) -> Path:
        self.queue_dir.mkdir(parents=True, exist_ok=True)
        path = self.queue_dir / f"{batch.batch_id}.json"
        if path.exists() and not overwrite:
            raise ReviewError(f"batch {batch.batch_id} already exists")
        queued = {i.item_id: b.batch_id for b in self.batches() if b.batch_id != batch.batch_id for i in b.items}
        clash = [i.item_id for i in batch.items if i.item_id in queued]
        if clash:
            raise ReviewError(f"already queued in another batch: {clash}")
        path.write_text(batch.model_dump_json(indent=2) + "\n", encoding="utf-8")
        return path

    def find(self, item_id: str) -> Tuple[ReviewBatch, ReviewItem]:
        for b in self.batches():
            for i in b.items:
                if i.item_id == item_id:
                    return b, i
        raise ReviewError(f"no queued item '{item_id}'")

    # --- decisions
    def decisions(self) -> List[Decision]:
        if not self.decisions_dir.exists():
            return []
        out: List[Decision] = []
        for p in sorted(self.decisions_dir.glob("*.jsonl")):
            out += [Decision.model_validate_json(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
        return out

    def current_decisions(self, item: ReviewItem) -> Dict[str, Decision]:
        """Latest decision per reviewer on the item's CURRENT content."""
        sha, latest = item.content_sha(), {}
        for d in self.decisions():
            if d.item_id == item.item_id and d.item_sha == sha:
                latest[d.reviewer] = d
        return latest

    def decide(self, item_id: str, reviewer: str, decision: str, failed: Sequence[str] = (),
               note: Optional[str] = None, minutes: Optional[float] = None,
               now: Optional[datetime] = None) -> Decision:
        reviewer = self.resolve_reviewer(reviewer)
        batch, item = self.find(item_id)
        if is_author(reviewer, item):
            raise ReviewError(f"{reviewer} drafted or requested {item_id}; no self-approval")
        if batch.assigned_to and reviewer not in batch.assigned_to:
            raise ReviewError(f"batch {batch.batch_id} is assigned to {batch.assigned_to}, not {reviewer}")
        bad = set(failed) - set(CHECKS)
        if bad:
            raise ReviewError(f"unknown checks {sorted(bad)}; use {CHECKS}")
        now = now or datetime.now(timezone.utc)
        if minutes is None:
            minutes = self._session_minutes(reviewer, item_id, now)
        rec = Decision(item_id=item_id, batch_id=batch.batch_id, item_sha=item.content_sha(), reviewer=reviewer,
                       decision=decision, checks={c: c not in failed for c in CHECKS}, note=note,
                       minutes_spent=round(minutes, 2), decided_at=now.isoformat())
        self.decisions_dir.mkdir(parents=True, exist_ok=True)
        path = self.decisions_dir / f"{_norm(reviewer).replace(' ', '_')}.jsonl"
        with path.open("a", encoding="utf-8") as fh:
            fh.write(rec.model_dump_json() + "\n")
        self._clear_session(reviewer)
        return rec

    # --- review timer (local only; .sessions is git-ignored)
    def start(self, reviewer: str, item_id: str, now: Optional[datetime] = None) -> None:
        reviewer = self.resolve_reviewer(reviewer)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        (self.sessions_dir / f"{_norm(reviewer).replace(' ', '_')}.json").write_text(json.dumps(
            {"item_id": item_id, "started_at": (now or datetime.now(timezone.utc)).isoformat()}), encoding="utf-8")

    def _session_minutes(self, reviewer: str, item_id: str, now: datetime) -> float:
        path = self.sessions_dir / f"{_norm(reviewer).replace(' ', '_')}.json"
        if path.exists():
            s = json.loads(path.read_text(encoding="utf-8"))
            if s["item_id"] == item_id:
                return max(0.1, (now - datetime.fromisoformat(s["started_at"])).total_seconds() / 60.0)
        raise ReviewError("no timer for this item: open it with `review.py next` first, or pass --minutes")

    def _clear_session(self, reviewer: str) -> None:
        path = self.sessions_dir / f"{_norm(reviewer).replace(' ', '_')}.json"
        if path.exists():
            path.unlink()

    # --- status
    def status(self, item: ReviewItem) -> str:
        cur = self.current_decisions(item)
        kinds = Counter(d.decision for d in cur.values())
        if kinds["reject"]:
            return "rejected"
        if kinds["fix"]:
            return "needs_fix"
        if kinds["approve"] >= item.required_reviews:
            return "approved"
        return "partially_approved" if kinds["approve"] else "pending"

    def next_item(self, reviewer: str, batch_id: Optional[str] = None) -> Optional[Tuple[ReviewBatch, ReviewItem]]:
        """First item the reviewer may decide on, has not decided on, and that still needs a review."""
        reviewer = self.resolve_reviewer(reviewer)
        for b in self.batches():
            if batch_id and b.batch_id != batch_id:
                continue
            if b.assigned_to and reviewer not in b.assigned_to:
                continue
            for i in b.items:
                if is_author(reviewer, i):
                    continue
                cur = self.current_decisions(i)
                if reviewer in cur:
                    continue
                if b.purpose != "calibration" and self.status(i) in ("approved", "rejected", "needs_fix"):
                    continue
                return b, i
        return None


# ---------------------------------------------------------------------------
# Agreement (day-one calibration, reported in the paper)
# ---------------------------------------------------------------------------


def cohen_kappa(a: Sequence[str], b: Sequence[str]) -> Optional[float]:
    """Cohen's kappa for two raters over the same items (None if undefined)."""
    if len(a) != len(b) or not a:
        raise ValueError("two equal-length, non-empty rating lists required")
    n = len(a)
    po = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / (n * n)
    if pe == 1.0:
        return None  # both raters used one identical category throughout: kappa undefined
    return (po - pe) / (1 - pe)


def fleiss_kappa(ratings: Sequence[Sequence[str]]) -> Optional[float]:
    """Fleiss' kappa; ratings[i] = the category each rater gave item i (same rater count per item)."""
    if not ratings:
        raise ValueError("no items")
    m = len(ratings[0])
    if m < 2 or any(len(r) != m for r in ratings):
        raise ValueError("every item needs the same number (>= 2) of ratings")
    cats = sorted({c for r in ratings for c in r})
    n = len(ratings)
    counts = [Counter(r) for r in ratings]
    p_i = [(sum(c[k] ** 2 for k in cats) - m) / (m * (m - 1)) for c in counts]
    p_bar = sum(p_i) / n
    p_j = [sum(c[k] for c in counts) / (n * m) for k in cats]
    pe = sum(p ** 2 for p in p_j)
    if pe == 1.0:
        return None
    return (p_bar - pe) / (1 - pe)


def calibration_agreement(store: ReviewStore, batch_id: str) -> Dict[str, object]:
    """Pairwise Cohen's kappa and Fleiss' kappa on a calibration batch's decisions."""
    batch = next((b for b in store.batches() if b.batch_id == batch_id), None)
    if batch is None:
        raise ReviewError(f"no batch '{batch_id}'")
    by_item = {i.item_id: store.current_decisions(i) for i in batch.items}
    raters = sorted({r for d in by_item.values() for r in d})
    pairs = {}
    for r1, r2 in itertools.combinations(raters, 2):
        common = [i for i, d in by_item.items() if r1 in d and r2 in d]
        if common:
            k = cohen_kappa([by_item[i][r1].decision for i in common], [by_item[i][r2].decision for i in common])
            pairs[f"{r1} vs {r2}"] = {"items": len(common), "kappa": None if k is None else round(k, 3)}
    complete = [i for i, d in by_item.items() if raters and set(raters) <= set(d)]
    fk = fleiss_kappa([[by_item[i][r].decision for r in raters] for i in complete]) if len(raters) >= 2 and complete else None
    defined = [p["kappa"] for p in pairs.values() if p["kappa"] is not None]
    return {
        "batch_id": batch_id, "raters": raters, "items": len(batch.items), "items_rated_by_all": len(complete),
        "pairwise_cohen_kappa": pairs,
        "mean_pairwise_cohen_kappa": round(sum(defined) / len(defined), 3) if defined else None,
        "fleiss_kappa": None if fk is None else round(fk, 3),
        "categories": list(DECISIONS),
    }


# ---------------------------------------------------------------------------
# Daily progress report
# ---------------------------------------------------------------------------


def progress_report(store: ReviewStore, day: Optional[str] = None,
                    gpu_ledgers: Iterable[Path] = (), ask_me: Optional[Path] = None) -> Dict[str, object]:
    """Approved per stage / repo / reviewer, reject rate, minutes, GPU hours used, open blockers."""
    items = [(b, i) for b in store.batches() for i in b.items]
    status = {i.item_id: store.status(i) for _, i in items}
    approved = [i for _, i in items if status[i.item_id] == "approved"]
    decisions = store.decisions()
    today = [d for d in decisions if day is None or d.decided_at.startswith(day)]
    per_rev: Dict[str, Counter] = defaultdict(Counter)
    minutes: Dict[str, float] = defaultdict(float)
    for d in today:
        per_rev[d.reviewer][d.decision] += 1
        minutes[d.reviewer] += d.minutes_spent
    n_dec = len(today)
    reject_rate = sum(1 for d in today if d.decision == "reject") / n_dec if n_dec else None
    gpu_s = 0.0
    for ledger in gpu_ledgers:
        for line in Path(ledger).read_text(encoding="utf-8").splitlines():
            rec = json.loads(line) if line.strip() else {}
            trial = rec.get("trial") or rec.get("result") or {}
            if (day is None or str(rec.get("finished_utc", rec.get("timestamp", ""))).startswith(day)) and "latency_ms" in trial:
                gpu_s += trial["latency_ms"] / 1000.0
    blockers = []
    if ask_me and Path(ask_me).exists():
        blockers = [l.strip()[6:] for l in Path(ask_me).read_text(encoding="utf-8").splitlines()
                    if l.strip().startswith("- [ ] ")]
    return {
        "day": day or "all time",
        "approved_total": len(approved),
        "approved_per_stage": dict(Counter(i.sdlc_stage for i in approved)),
        "approved_per_repo": dict(Counter(i.repository for i in approved)),
        "status_counts": dict(Counter(status.values())),
        "decisions_per_reviewer": {r: dict(c) for r, c in sorted(per_rev.items())},
        "minutes_per_reviewer": {r: round(m, 1) for r, m in sorted(minutes.items())},
        "mean_minutes_per_decision": round(sum(minutes.values()) / n_dec, 2) if n_dec else None,
        "reject_rate": None if reject_rate is None else round(reject_rate, 3),
        "reject_alert": bool(reject_rate is not None and reject_rate > REJECT_ALERT_RATE),
        "gpu_hours_used": round(gpu_s / 3600.0, 2),
        "open_blockers": blockers,
    }


# ---------------------------------------------------------------------------
# Building items from the existing benchmark (dev / val; test only for the correctness pass)
# ---------------------------------------------------------------------------


WHOLE_FILE_MAX_LINES = 400


def _pinned_lines(repository: str, file: str) -> List[str]:
    from benchmark import retrieval_labels as rl

    return (rl.repo_dir(repository) / file).read_text(encoding="utf-8").splitlines()


def snippet(repository: str, file: str, start: int, end: int) -> EvidenceSnippet:
    """Exact lines from the pinned checkout in .corpus_cache (refuses an unpinned checkout)."""
    from benchmark import retrieval_labels as rl
    from experiments.m5.manifest import wave1_repository_pins

    want = wave1_repository_pins().get(repository)
    have = rl.checkout_sha(repository)
    if want is None or have != want:
        raise ReviewError(f"{repository}: checkout {have} is not the pinned commit {want}")
    lines = (rl.repo_dir(repository) / file).read_text(encoding="utf-8").splitlines()
    if end > len(lines):
        raise ReviewError(f"{repository}:{file} has {len(lines)} lines; evidence ends at {end}")
    text = "\n".join(lines[start - 1:end])
    return EvidenceSnippet(file=file, start_line=start, end_line=end, text=text,
                           span_sha256="sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest())


def item_from_task(task: dict, split: str, drafted_by: str, requested_by: Optional[str] = None,
                   label: Optional[dict] = None, allow_evidence_defects: bool = False) -> ReviewItem:
    """Review item for an existing task, showing the exact lines its evidence cites.

    Some pilot tasks cite a documentation file without line numbers. For those, the lines
    come from the task's retrieval label (benchmark/data/retrieval_labels_v1.json) for the
    same file, and the item says so, so the reviewer checks those lines too.
    """
    from experiments.m5.manifest import wave1_repository_pins

    if allow_evidence_defects:
        # Correctness pass: a task whose cited evidence cannot be shown is still reviewed; the
        # defect is stated and the reviewer opens the pinned file (two reviewers, fix or reject).
        try:
            return item_from_task(task, split, drafted_by, requested_by, label)
        except (ReviewError, OSError) as exc:
            cited = [f"{e.get('file_path')} L{e.get('line_start')}-L{e.get('line_end')}"
                     for e in task.get("source_evidence", [])]
            return ReviewItem(
                item_id=task["task_id"], kind="existing_task", split=split, repository=task["repository"],
                commit_sha=wave1_repository_pins()[task["repository"]], sdlc_stage=task["sdlc_stage"],
                task_type=task["task_type"], complexity=task.get("complexity"), criticality=task.get("criticality"),
                query=task["query"], proposed_answer=task["ground_truth"],
                acceptable_alternatives=task.get("acceptable_alternatives", []), evidence=[],
                drafted_by=drafted_by, requested_by=requested_by,
                status_note=(f"EVIDENCE DEFECT: {exc}. Cited: {cited}. Open the file at the pinned commit "
                             "yourself; evidence_correct fails - use fix (name the right lines) or reject."))

    ev, from_label, whole = [], [], []
    for e in task.get("source_evidence", []):
        if not e.get("file_path"):
            continue
        if e.get("line_start"):
            ev.append(snippet(task["repository"], e["file_path"], e["line_start"], e.get("line_end") or e["line_start"]))
            continue
        spans = [s for s in (label or {}).get("required_evidence", []) if s["file"] == e["file_path"]]
        if not spans:
            # No label (e.g. a test task, labelled only right before the final run): show the whole
            # file if it is short enough to read, and the reviewer names the lines in a `fix`.
            n_lines = len(_pinned_lines(task["repository"], e["file_path"]))
            if n_lines > WHOLE_FILE_MAX_LINES:
                raise ReviewError(f"{task['task_id']}: evidence file has no line numbers and is too long "
                                  f"({n_lines} lines) to show whole")
            ev.append(snippet(task["repository"], e["file_path"], 1, n_lines))
            whole.append(e["file_path"])
            continue
        ev += [snippet(task["repository"], s["file"], s["start_line"], s["end_line"]) for s in spans]
        from_label.append(e["file_path"])
    if not ev:
        raise ReviewError(f"{task['task_id']} has no file+line evidence to review")
    note = "existing benchmark task"
    if from_label:
        note += f"; task cites {from_label} without lines - lines shown are from its draft retrieval label"
    if whole:
        note += (f"; task cites {whole} without lines - the WHOLE file is shown: if the answer is right, "
                 "use `fix` with evidence_correct failed and name the exact lines in the note")
    return ReviewItem(item_id=task["task_id"], kind="existing_task", split=split, repository=task["repository"],
                      commit_sha=wave1_repository_pins()[task["repository"]], sdlc_stage=task["sdlc_stage"],
                      task_type=task["task_type"], complexity=task.get("complexity"),
                      criticality=task.get("criticality"), query=task["query"],
                      proposed_answer=task["ground_truth"],
                      acceptable_alternatives=task.get("acceptable_alternatives", []), evidence=ev,
                      drafted_by=drafted_by, requested_by=requested_by, status_note=note)
