"""
EIH-SWE task drafting (Step 3a; plan §8.2, spec §1: 400-500 human-verified tasks).

Pipeline:
  1. sample_spans(): candidate evidence spans per (repository, SDLC stage) from the pinned
     checkouts, chosen deterministically (seed 42) so the drafter does not cherry-pick.
  2. A drafter writes a candidate task per span: question, answer, evidence lines, labels.
     The drafter is Claude (decision 2026-10-05: Claude drafts, humans verify). The evaluated
     local models never draft questions they will later be scored on.
  3. validate_draft(): fails the draft unless every evidence span exists at the pinned commit
     with start <= end <= end of file. Evidence is never shown as present when it is not.
  4. queue_drafts(): review batches of <= 25, with the requester rotating per batch (R2).
     LLM drafts stay "drafted" until approved.
  5. Split (S1): a fixed stratified 40/20/40 dev/val/test split, seed 42, assigned when a task first
     gets an approval. Within each stratum (repository x stage), the k-th approved task takes slot k
     of a seeded permutation of [dev, dev, val, test, test], repeated. Nobody chooses where a task
     lands. A test slot needs a second, different reviewer before the task counts.
  6. Lock (Step 3e): lock_sets() fingerprints the approved sets on 12 Oct. Tasks approved later
     go to a NEW held-out set and are never merged into the paper's test set.
"""

from __future__ import annotations

import ast
import hashlib
import json
import random
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from benchmark.review import (
    BATCH_SIZE, EvidenceSnippet, ReviewBatch, ReviewError, ReviewItem, ReviewStore, snippet,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "benchmark" / "data"
SPANS_DIR = DATA_DIR / "drafting" / "spans"
DRAFTS_DIR = DATA_DIR / "drafting" / "drafts"
SPLIT_ASSIGNMENTS = DATA_DIR / "review" / "split_assignments.json"
LOCKS_DIR = DATA_DIR / "locks"
EIH_SWE_TASKS = DATA_DIR / "eih_swe_tasks.json"
SEED = 42
DRAFTER = "Claude Opus 5.5 (EIH drafting tool)"
REQUESTERS = ("Avaneesh Kumar Verma", "Sanvi", "Aayan", "Radhesh")   # rotate per batch (R2)
STAGES = ("requirements", "architecture", "development", "testing", "code_review", "maintenance")
SLOT_BLOCK = ("dev", "dev", "val", "test", "test")                   # 40 / 20 / 40

STAGE_TYPES = {
    "requirements": {"requirement_understanding", "requirement_retrieval"},
    "architecture": {"architecture_qa", "dependency_understanding", "architecture_decision_support",
                     "code_explanation"},
    "development": {"code_generation", "code_explanation", "repository_assistance"},
    "testing": {"test_generation", "test_explanation", "test_failure_analysis"},
    "code_review": {"defect_detection", "risk_identification", "review_assistance"},
    "maintenance": {"change_understanding", "error_analysis", "root_cause_assistance",
                    "change_impact_analysis", "historical_reasoning", "technical_debt_analysis"},
}

# Where each repository keeps its package source, tests, docs and changelog (pinned checkouts).
LAYOUT = {
    "pallets/flask": {"src": ["src/flask"], "tests": ["tests"], "docs": ["docs"], "changes": ["CHANGES.rst"]},
    "fastapi/fastapi": {"src": ["fastapi"], "tests": ["tests"], "docs": ["docs/en/docs"],
                        "changes": ["docs/en/docs/release-notes.md"]},
    "psf/requests": {"src": ["src/requests"], "tests": ["tests"], "docs": ["docs"], "changes": ["HISTORY.md"]},
    "pytest-dev/pytest": {"src": ["src/_pytest"], "tests": ["testing"], "docs": ["doc/en"],
                          "changes": ["doc/en/changelog.rst"]},
    "sphinx-doc/sphinx": {"src": ["sphinx"], "tests": ["tests"], "docs": ["doc"], "changes": ["CHANGES.rst"]},
    "pylint-dev/pylint": {"src": ["pylint"], "tests": ["tests"], "docs": ["doc"],
                          "changes": ["doc/whatsnew/3"]},
}
MAX_SPAN_LINES = 80


@dataclass(frozen=True)
class Span:
    span_id: str
    repository: str
    file: str
    start_line: int
    end_line: int
    kind: str          # function | class | test | doc_section | changelog_entry | raise
    stage: str
    name: str


# ---------------------------------------------------------------------------------- sampling


def _repo_path(repository: str) -> Path:
    from benchmark import retrieval_labels as rl

    return rl.repo_dir(repository)


def _rel(repository: str, path: Path) -> str:
    return path.relative_to(_repo_path(repository)).as_posix()


def _py_units(repository: str, roots: Sequence[str], tests: bool) -> List[Tuple[str, int, int, str, str]]:
    """(file, start, end, kind, qualname) for functions/classes, AST-exact line ranges."""
    base = _repo_path(repository)
    out = []
    for root in roots:
        for f in sorted((base / root).rglob("*.py")):
            try:
                tree = ast.parse(f.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                continue
            rel = _rel(repository, f)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    start = min([node.lineno] + [d.lineno for d in getattr(node, "decorator_list", [])])
                    end = node.end_lineno or node.lineno
                    is_test = node.name.startswith("test")
                    if tests != is_test and not (tests and isinstance(node, ast.ClassDef) and node.name.startswith("Test")):
                        continue
                    if node.name.startswith("_") and not tests:
                        continue
                    kind = "test" if tests else ("class" if isinstance(node, ast.ClassDef) else "function")
                    if 4 <= end - start + 1 <= MAX_SPAN_LINES:
                        out.append((rel, start, end, kind, node.name))
    return out


def _raises(repository: str, roots: Sequence[str]) -> List[Tuple[str, int, int, str, str]]:
    """Functions that raise an exception with a literal message (error-diagnosis material)."""
    base = _repo_path(repository)
    out = []
    for root in roots:
        for f in sorted((base / root).rglob("*.py")):
            try:
                tree = ast.parse(f.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                continue
            rel = _rel(repository, f)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    msgs = [n for n in ast.walk(node) if isinstance(n, ast.Raise) and n.exc is not None
                            and any(isinstance(a, ast.Constant) and isinstance(a.value, str) and len(a.value) > 15
                                    for a in ast.walk(n.exc))]
                    start, end = node.lineno, node.end_lineno or node.lineno
                    if msgs and 4 <= end - start + 1 <= MAX_SPAN_LINES:
                        out.append((rel, start, end, "raise", node.name))
    return out


_MD_HEAD = re.compile(r"^(#{1,4})\s+(.+)$")


def _doc_sections(repository: str, roots: Sequence[str]) -> List[Tuple[str, int, int, str, str]]:
    """Markdown / reStructuredText sections, header to the line before the next header."""
    base = _repo_path(repository)
    out = []
    for root in roots:
        files = sorted(list((base / root).rglob("*.md")) + list((base / root).rglob("*.rst")))
        for f in files:
            lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
            heads = []
            for i, line in enumerate(lines):
                if f.suffix == ".md":
                    m = _MD_HEAD.match(line)
                    if m:
                        heads.append((i + 1, m.group(2).strip()))
                elif i + 1 < len(lines) and line.strip() and re.fullmatch(r"[=\-~^]{3,}", lines[i + 1].strip()) \
                        and len(lines[i + 1].strip()) >= len(line.strip()) - 2:
                    heads.append((i + 1, line.strip()))
            for (s, title), nxt in zip(heads, heads[1:] + [(len(lines) + 1, "")]):
                e = nxt[0] - 1
                while e > s and not lines[e - 1].strip():
                    e -= 1
                if 5 <= e - s + 1 <= MAX_SPAN_LINES:
                    out.append((_rel(repository, f), s, e, "doc_section", title))
    return out


def candidates(repository: str, stage: str) -> List[Tuple[str, int, int, str, str]]:
    lay = LAYOUT[repository]
    if stage == "requirements":
        # Changelogs are maintenance material (fix after round 1: two pytest changelog sections
        # were sampled as requirements spans and had to be skipped).
        changes = {c for c in lay["changes"]}
        return [c for c in _doc_sections(repository, lay["docs"])
                if not any(c[0] == ch or c[0].startswith(ch.rstrip("/") + "/") for ch in changes)
                and "changelog" not in c[0].lower() and "release-notes" not in c[0].lower()
                and "whatsnew" not in c[0].lower()]
    if stage == "architecture":
        return [c for c in _py_units(repository, lay["src"], tests=False) if c[3] == "class"]
    if stage == "development":
        return [c for c in _py_units(repository, lay["src"], tests=False) if c[3] == "function"]
    if stage == "testing":
        return _py_units(repository, lay["tests"], tests=True)
    if stage == "code_review":
        return [c for c in _py_units(repository, lay["src"], tests=False) if c[3] == "function"]
    if stage == "maintenance":
        return _doc_sections(repository, lay["changes"]) + _raises(repository, lay["src"])
    raise ValueError(f"unknown stage {stage}")


def sample_spans(repository: str, stage: str, n: int, seed: int = SEED,
                 exclude: Iterable[Tuple[str, int, int]] = ()) -> List[Span]:
    """n candidate spans for (repository, stage), seeded and reproducible; overlapping excluded spans skipped."""
    pool = sorted(set(candidates(repository, stage)))
    rng = random.Random(f"{seed}:{repository}:{stage}")
    rng.shuffle(pool)
    excl = list(exclude)
    out: List[Span] = []
    for file, s, e, kind, name in pool:
        if any(f == file and s <= ee and ss <= e for f, ss, ee in excl):
            continue
        sid = "span-" + hashlib.sha256(f"{repository}:{file}:{s}:{e}".encode()).hexdigest()[:12]
        out.append(Span(sid, repository, file, s, e, kind, stage, name))
        if len(out) == n:
            break
    return out


def write_span_packet(spans: Sequence[Span], name: str) -> Path:
    """The span list + exact text the drafter works from (JSON lines)."""
    SPANS_DIR.mkdir(parents=True, exist_ok=True)
    path = SPANS_DIR / f"{name}.jsonl"
    with path.open("w", encoding="utf-8") as fh:
        for sp in spans:
            sn = snippet(sp.repository, sp.file, sp.start_line, sp.end_line)
            fh.write(json.dumps({**asdict(sp), "text": sn.text, "span_sha256": sn.span_sha256}) + "\n")
    return path


# ---------------------------------------------------------------------------------- drafts


@dataclass
class Draft:
    span_id: str
    repository: str
    sdlc_stage: str
    task_type: str
    complexity: str
    criticality: str
    query: str
    answer: str
    evidence: List[Dict[str, object]]          # [{"file", "start_line", "end_line"}]
    acceptable_alternatives: List[str]
    difficulty: str = "medium"

    @classmethod
    def from_json(cls, d: dict) -> "Draft":
        return cls(**{k: d[k] for k in ("span_id", "repository", "sdlc_stage", "task_type", "complexity",
                                         "criticality", "query", "answer", "evidence")},
                   acceptable_alternatives=list(d.get("acceptable_alternatives", [])),
                   difficulty=d.get("difficulty", "medium"))


_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]{3,}")


def validate_draft(d: Draft) -> List[EvidenceSnippet]:
    """Evidence snippets for a valid draft, or ReviewError. Never accepts missing or out-of-file lines."""
    from experiments.m5.manifest import wave1_repository_pins

    if d.repository not in wave1_repository_pins():
        raise ReviewError(f"{d.span_id}: {d.repository} is not a pinned wave-1 repository")
    if d.sdlc_stage not in STAGE_TYPES or d.task_type not in STAGE_TYPES[d.sdlc_stage]:
        raise ReviewError(f"{d.span_id}: task type {d.task_type} does not belong to stage {d.sdlc_stage}")
    if d.complexity not in ("low", "medium", "high") or d.criticality not in ("low", "medium", "high", "critical"):
        raise ReviewError(f"{d.span_id}: complexity/criticality out of range")
    if not (15 <= len(d.query) <= 600) or not (20 <= len(d.answer) <= 3000):
        raise ReviewError(f"{d.span_id}: question or answer length out of range")
    if not d.evidence:
        raise ReviewError(f"{d.span_id}: no evidence")
    snippets = []
    for e in d.evidence:
        file, s, t = str(e["file"]), int(e["start_line"]), int(e["end_line"])
        if s < 1 or t < s:
            raise ReviewError(f"{d.span_id}: evidence {file} L{s}-{t} is not a valid range")
        path = _repo_path(d.repository) / file
        if not path.is_file():
            raise ReviewError(f"{d.span_id}: evidence file {file} does not exist at the pinned commit")
        snippets.append(snippet(d.repository, file, s, t))   # raises if t is past the end of the file
    # Grounding sanity check: the answer must share at least one identifier-like token with its evidence.
    ev_tokens = {w.lower() for sn in snippets for w in _IDENT.findall(sn.text)}
    if not ({w.lower() for w in _IDENT.findall(d.answer)} & ev_tokens):
        raise ReviewError(f"{d.span_id}: the answer shares no identifier with its evidence")
    return snippets


def queue_drafts(drafts: Sequence[Draft], batch_prefix: str, store: Optional[ReviewStore] = None,
                 requester_offset: int = 0) -> Dict[str, object]:
    """Validate and queue drafts in batches of <= 25. Invalid drafts are reported, never queued."""
    from experiments.m5.manifest import wave1_repository_pins

    store = store or ReviewStore()
    queued = {i.item_id for b in store.batches() for i in b.items}
    ok, failed = [], []
    for d in drafts:
        try:
            ev = validate_draft(d)
        except (ReviewError, OSError) as exc:
            failed.append({"span_id": d.span_id, "reason": str(exc)})
            continue
        tid = "eih-swe-" + hashlib.sha256(f"{d.repository}|{d.query}".encode()).hexdigest()[:10]
        if tid in queued:
            failed.append({"span_id": d.span_id, "reason": "duplicate question"})
            continue
        ok.append(ReviewItem(item_id=tid, kind="new_task", split="unassigned", repository=d.repository,
                             commit_sha=wave1_repository_pins()[d.repository], sdlc_stage=d.sdlc_stage,
                             task_type=d.task_type, complexity=d.complexity, criticality=d.criticality,
                             query=d.query, proposed_answer=d.answer,
                             acceptable_alternatives=d.acceptable_alternatives, evidence=ev,
                             drafted_by=DRAFTER, requested_by=None,
                             status_note=f"drafted (LLM draft, not verified); span {d.span_id}"))
        queued.add(tid)
    batches = []
    for k in range(0, len(ok), BATCH_SIZE):
        requester = REQUESTERS[(requester_offset + k // BATCH_SIZE) % len(REQUESTERS)]
        items = [i.model_copy(update={"requested_by": requester}) for i in ok[k:k + BATCH_SIZE]]
        others = [r for r in store.reviewers() if r.split()[0].lower() != requester.split()[0].lower()]
        batch = ReviewBatch(batch_id=f"{batch_prefix}-{k // BATCH_SIZE + 1:02d}",
                            created_at=datetime.now(timezone.utc).isoformat(), purpose="review",
                            assigned_to=others, items=items)
        store.save_batch(batch)
        batches.append({"batch_id": batch.batch_id, "items": len(items), "requested_by": requester,
                        "assigned_to": others})
    return {"queued": len(ok), "failed": failed, "batches": batches}


# ---------------------------------------------------------------------------------- split (S1)


def _slot_order(stratum: str) -> List[str]:
    block = list(SLOT_BLOCK)
    random.Random(f"{SEED}:{stratum}").shuffle(block)
    return block


def load_assignments(path: Path = SPLIT_ASSIGNMENTS) -> Dict[str, dict]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def assign_split(item: ReviewItem, path: Path = SPLIT_ASSIGNMENTS, now: Optional[datetime] = None) -> dict:
    """Assign (once) the next slot of the item's stratum. Called at the item's first approval."""
    assignments = load_assignments(path)
    if item.item_id in assignments:
        return assignments[item.item_id]
    stratum = f"{item.repository}|{item.sdlc_stage}"
    k = sum(1 for a in assignments.values() if a["stratum"] == stratum)
    split = _slot_order(stratum)[k % len(SLOT_BLOCK)]
    lock = current_lock()
    rec = {"split": split, "stratum": stratum, "slot": k, "assigned_at": (now or datetime.now(timezone.utc)).isoformat(),
           "set": lock["next_set"] if lock else "eih-swe-v2"}
    assignments[item.item_id] = rec
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(assignments, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return rec


# ---------------------------------------------------------------------------------- lock (3e)


def current_lock() -> Optional[dict]:
    if not LOCKS_DIR.exists():
        return None
    locks = sorted(LOCKS_DIR.glob("lock_*.json"))
    return json.loads(locks[-1].read_text(encoding="utf-8")) if locks else None


def task_fingerprint(query: str, repository: str, commit: str, answer: str) -> str:
    """Spec §6.2: sha256(query || repository || base_commit || ground_truth_answer)."""
    return "sha256:" + hashlib.sha256("‖".join([query, repository, commit, answer]).encode("utf-8")).hexdigest()


def lock_sets(approved: Sequence[dict], lock_date: str, dry_run: bool = True) -> dict:
    """Fingerprint every split of the approved tasks. After the lock, new approvals go to a new set."""
    by_split: Dict[str, List[str]] = {}
    for t in approved:
        by_split.setdefault(t["split"], []).append(t["fingerprint"])
    sets = {s: {"tasks": len(v), "sha256": "sha256:" + hashlib.sha256("\n".join(sorted(v)).encode()).hexdigest()}
            for s, v in sorted(by_split.items())}
    pilot = {name: "sha256:" + hashlib.sha256((DATA_DIR / name).read_bytes()).hexdigest()
             for name in ("meib_phase1_tasks.json", "splits_v1.0.json") if (DATA_DIR / name).exists()}
    lock = {"lock_date": lock_date, "created_utc": datetime.now(timezone.utc).isoformat(), "sets": sets,
            "pilot_files": pilot,
            "paper_test_set": "pilot test split (splits_v1.0.json) + new tasks with split 'test' in the locked set",
            "locked_set": "eih-swe-v2", "next_set": f"eih-swe-post-lock-{lock_date}",
            "rule": "Tasks approved after this lock form a new held-out set and are never merged into "
                    "the paper's test set."}
    if not dry_run:
        LOCKS_DIR.mkdir(parents=True, exist_ok=True)
        path = LOCKS_DIR / f"lock_{lock_date}.json"
        if path.exists():
            raise ReviewError(f"{path} already exists; a lock is never rewritten")
        path.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")
    return lock


# ---------------------------------------------------------------------------------- approved -> tasks


def approved_tasks(store: Optional[ReviewStore] = None) -> List[dict]:
    """Benchmark task records for every approved NEW task (split + set from the assignment)."""
    store = store or ReviewStore()
    assignments = load_assignments(store.assignments_path)
    out = []
    for b in store.batches():
        for i in b.items:
            if i.kind != "new_task" or store.status(i) != "approved":
                continue
            dec = store.current_decisions(i)
            approvers = sorted(r for r, d in dec.items() if d.decision == "approve")
            a = assignments[i.item_id]
            out.append({
                "task_id": i.item_id, "version": "2.0", "repository": i.repository, "commit_sha": i.commit_sha,
                "sdlc_stage": i.sdlc_stage, "task_type": i.task_type, "complexity": i.complexity,
                "criticality": i.criticality, "query": i.query, "ground_truth": i.proposed_answer,
                "acceptable_alternatives": i.acceptable_alternatives,
                "source_evidence": [{"evidence_type": "documentation" if e.file.endswith((".md", ".rst", ".txt"))
                                     else "source_file", "repository": i.repository, "file_path": e.file,
                                     "line_start": e.start_line, "line_end": e.end_line,
                                     "span_sha256": e.span_sha256} for e in i.evidence],
                "status": "approved", "drafted_by": i.drafted_by, "requested_by": i.requested_by,
                "human_approved_by": "; ".join(approvers),
                "human_approved_at": max(d.decided_at for d in dec.values())[:10],
                "review_minutes": round(sum(d.minutes_spent for d in dec.values()), 1),
                "split": a["split"], "set": a["set"], "stratum": a["stratum"],
                "fingerprint": task_fingerprint(i.query, i.repository, i.commit_sha, i.proposed_answer),
            })
    return sorted(out, key=lambda t: t["task_id"])


def write_approved(store: Optional[ReviewStore] = None, path: Path = EIH_SWE_TASKS) -> dict:
    tasks = approved_tasks(store)
    doc = {"benchmark": "EIH-SWE", "version": "2.0", "written_utc": datetime.now(timezone.utc).isoformat(),
           "note": "Approved new tasks only (the 60 pilot tasks stay in meib_phase1_tasks.json).",
           "counts": {s: sum(1 for t in tasks if t["split"] == s) for s in ("dev", "val", "test")},
           "tasks": tasks}
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return doc["counts"]
