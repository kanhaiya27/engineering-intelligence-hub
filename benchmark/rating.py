"""
Blind human rating of answers (M1, Step 3c): the ground truth used to CHOOSE the correctness measure.

  benchmark/data/review/rating/<batch>.json      units shown to raters: blind id, question, reference
                                                 answer, the answer to rate, the evidence lines. No
                                                 system, trial or score is stored here.
  C:/EIH_keys/<batch>_key.json (outside git)     blind id -> task, system, trial. Only its sha256 is
                                                 committed, so the mapping is fixed in advance. Held by
                                                 the key holder, never on a rater's machine. (Until
                                                 2026-11-25 keys went to C:/EIH_backups, lost with the
                                                 SSD; WORK_PLAN C42.)
  benchmark/data/review/ratings/<rater>.jsonl    append-only ratings

Each unit is rated by two different reviewers (rotating pairs), so inter-rater agreement is
measurable. Rating is refused until the key holder has checked the key against `key_sha256`
(`review.py verify-key`), which stamps `key_verified_at` in the batch file (C42). Raters judge:
  correctness 1-5     does the answer state the reference's key facts without contradicting the code?
  completeness 1-5    does it cover everything the reference needs?
  accept yes/no       would you accept this answer as correct? Extra correct detail is fine.
"""

from __future__ import annotations

import hashlib
import json
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from pydantic import BaseModel, Field

from benchmark.review import REVIEW_DIR, ReviewError, ReviewStore

RATING_DIR = REVIEW_DIR / "rating"
RATINGS_DIR = REVIEW_DIR / "ratings"
KEY_DIR = Path("C:/EIH_keys")
# Every pair of the three reviewers once (reviewers.yaml, ASK_ME R3 / WORK_PLAN C36, C42). Batches built
# earlier keep the raters they record. tests/test_benchmark/test_rating.py checks this against the roster.
PAIRS = (("Avaneesh Kumar Verma", "Sanvi Bhardwaj"), ("Avaneesh Kumar Verma", "Aryan Gupta"),
         ("Sanvi Bhardwaj", "Aryan Gupta"))


class RatingUnit(BaseModel):
    blind_id: str
    query: str
    reference_answer: str
    answer: str
    evidence: List[Dict[str, object]]          # [{"file", "start_line", "end_line", "text"}]
    raters: List[str]


class RatingBatch(BaseModel):
    batch_id: str
    created_at: str
    purpose: str = "M1 correctness-measure selection (dev/val answers; blind)"
    key_sha256: str
    key_verified_at: Optional[str] = Field(
        default=None, description="Set by `review.py verify-key` once the key holder's key matches key_sha256; "
                                  "rating is refused until then")
    excluded_tasks: List[str] = Field(default_factory=list)
    exclusion_reason: str = ""
    units: List[RatingUnit]


class Rating(BaseModel):
    batch_id: str
    blind_id: str
    rater: str
    correctness: int = Field(ge=1, le=5)
    completeness: int = Field(ge=1, le=5)
    accept: bool
    note: Optional[str] = None
    rated_at: str


def build_batch(trials: Sequence[dict], tasks: Dict[str, dict], evidence: Dict[str, List[dict]], batch_id: str,
                n: int = 40, seed: int = 42, key_dir: Path = KEY_DIR, out_dir: Path = RATING_DIR,
                exclude_tasks: Sequence[str] = (), exclusion_reason: str = "") -> RatingBatch:
    """Blind batch of n non-refusal trial-0 answers, spread over SDLC stage x system (seeded)."""
    from experiments.m5.human_eval import sample_rating_units

    pool = [{"task_id": t["task_id"], "system_id": t["system_id"], "trial_index": t["trial_index"],
             "sdlc_stage": t["metadata"]["sdlc_stage"], "generated_answer": t["generated_answer"]}
            for t in trials if t["trial_index"] == 0 and not t["is_grounded_refusal"]
            and t["task_id"] not in set(exclude_tasks)]
    units = sample_rating_units(pool, n=n, seed=seed)
    key = {u["blind_id"]: {"task_id": u["task_id"], "system_id": u["system_id"], "trial_index": u["trial_index"]}
           for u in units}
    key_bytes = json.dumps(key, indent=2, sort_keys=True).encode("utf-8")
    key_dir.mkdir(parents=True, exist_ok=True)
    key_path = key_dir / f"{batch_id}_key.json"
    if key_path.exists():
        raise ReviewError(f"{key_path} exists; a rating key is never rewritten")
    key_path.write_bytes(key_bytes)
    rated = []
    for k, u in enumerate(units):
        t = tasks[u["task_id"]]
        rated.append(RatingUnit(blind_id=u["blind_id"], query=t["query"], reference_answer=t["ground_truth"],
                                answer=u["generated_answer"], evidence=evidence.get(u["task_id"], []),
                                raters=list(PAIRS[(k // max(1, n // len(PAIRS))) % len(PAIRS)])))
    batch = RatingBatch(batch_id=batch_id, created_at=datetime.now(timezone.utc).isoformat(),
                        key_sha256="sha256:" + hashlib.sha256(key_bytes).hexdigest(),
                        excluded_tasks=sorted(exclude_tasks), exclusion_reason=exclusion_reason, units=rated)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{batch_id}.json").write_text(batch.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return batch


class RatingStore:
    def __init__(self, review_dir: Path = REVIEW_DIR) -> None:
        self.rating_dir = review_dir / "rating"
        self.ratings_dir = review_dir / "ratings"
        self.review = ReviewStore(review_dir)

    def batches(self) -> List[RatingBatch]:
        if not self.rating_dir.exists():
            return []
        return [RatingBatch.model_validate_json(p.read_text(encoding="utf-8")) for p in sorted(self.rating_dir.glob("*.json"))]

    def ratings(self) -> List[Rating]:
        if not self.ratings_dir.exists():
            return []
        return [Rating.model_validate_json(l) for p in sorted(self.ratings_dir.glob("*.jsonl"))
                for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]

    def batch_path(self, batch_id: str) -> Path:
        return self.rating_dir / f"{batch_id}.json"

    def verify_key(self, batch_id: str, key_path: Path, now: Optional[datetime] = None) -> RatingBatch:
        """Key holder: check the key file against key_sha256 and stamp key_verified_at (nothing else is stored)."""
        path = self.batch_path(batch_id)
        if not path.exists():
            raise ReviewError(f"no rating batch '{batch_id}'")
        batch = RatingBatch.model_validate_json(path.read_text(encoding="utf-8"))
        got = "sha256:" + hashlib.sha256(Path(key_path).read_bytes()).hexdigest()
        if got != batch.key_sha256:
            raise ReviewError(f"key does not match {batch_id}'s key_sha256; rating stays blocked")
        batch.key_verified_at = (now or datetime.now(timezone.utc)).isoformat()
        path.write_text(batch.model_dump_json(indent=2) + "\n", encoding="utf-8")
        return batch

    def unverified(self) -> List[str]:
        return [b.batch_id for b in self.batches() if not b.key_verified_at]

    def next_unit(self, rater: str) -> Optional[tuple]:
        rater = self.review.resolve_reviewer(rater)
        done = {(r.batch_id, r.blind_id) for r in self.ratings() if r.rater == rater}
        for b in self.batches():
            if not b.key_verified_at:
                continue      # key not checked against key_sha256: no ratings yet
            for u in b.units:
                if rater in u.raters and (b.batch_id, u.blind_id) not in done:
                    return b, u
        return None

    def rate(self, blind_id: str, rater: str, correctness: int, completeness: int, accept: bool,
             note: Optional[str] = None, now: Optional[datetime] = None) -> Rating:
        rater = self.review.resolve_reviewer(rater)
        for b in self.batches():
            for u in b.units:
                if u.blind_id == blind_id:
                    if not b.key_verified_at:
                        raise ReviewError(f"batch {b.batch_id}'s key is not verified (review.py verify-key); "
                                          "no ratings until it is")
                    if rater not in u.raters:
                        raise ReviewError(f"{blind_id} is assigned to {u.raters}, not {rater}")
                    if any(r.rater == rater and r.blind_id == blind_id and r.batch_id == b.batch_id
                           for r in self.ratings()):
                        raise ReviewError(f"{rater} already rated {blind_id}")
                    rec = Rating(batch_id=b.batch_id, blind_id=blind_id, rater=rater, correctness=correctness,
                                 completeness=completeness, accept=accept, note=note,
                                 rated_at=(now or datetime.now(timezone.utc)).isoformat())
                    self.ratings_dir.mkdir(parents=True, exist_ok=True)
                    with (self.ratings_dir / f"{rater.split()[0].lower()}.jsonl").open("a", encoding="utf-8") as fh:
                        fh.write(rec.model_dump_json() + "\n")
                    return rec
        raise ReviewError(f"no rating unit '{blind_id}'")
