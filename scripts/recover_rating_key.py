"""
One-off recovery of a lost blind-rating key (m1-rating-01, WORK_PLAN C42).

The key (blind id -> task, system, trial) was written by `benchmark.rating.build_batch` to
C:/EIH_backups/<batch>_key.json and lost with the SSD. The batch file keeps its sha256. This script
rebuilds the key from the trial results the batch was built from, in two independent ways, and keeps
it only if both agree AND the bytes hash to the stored `key_sha256`:

  A  deterministic re-sampling: the same pool filter as build_batch, then
     sample_rating_units(pool, n=len(units), seed=42). build_batch's input order was not recorded and
     the seeded shuffles depend on it, so a short FIXED list of plausible input orders is tried
     (ORDERS below). The checksum decides; nothing is tuned to it.
  B  content cross-check: each unit's `answer` must equal exactly one pool trial's `generated_answer`
     whose task query equals the unit's `query`.

BLINDNESS: the raters are on the team. This script never prints, logs or writes key contents anywhere
except the --out file (outside the repo), and refuses to overwrite it. It prints only MATCH / NO MATCH,
counts and checksums.

  python scripts/recover_rating_key.py --batch m1-rating-01 [--out C:/EIH_keys/m1-rating-01_key.json]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from benchmark.rating import RATING_DIR, RatingBatch  # noqa: E402

# The trial results m1-rating-01 was built from: Step 2c Mode Q dev/val, 2026-10-06 (PROGRESS-A
# 2026-10-06; batch created_at 2026-10-06T01:19:36Z; added in commit 22bc3f4).
RESULT_DIRS = (REPO_ROOT / "experiments/results/queue/machine_A/modeq-dev-2c-2026-10-06",
               REPO_ROOT / "experiments/results/queue/machine_A/modeq-val-2c-2026-10-06")
DEFAULT_OUT = Path("C:/EIH_keys")
SEED = 42


def key_bytes(key: Dict[str, dict]) -> bytes:
    """Exactly build_batch's serialisation."""
    return json.dumps(key, indent=2, sort_keys=True).encode("utf-8")


def checksum(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def load_trials(result_dirs: Sequence[Path] = RESULT_DIRS) -> List[dict]:
    """Trial result dicts in ledger order (dev file first, then val)."""
    out = []
    for d in result_dirs:
        for line in (Path(d) / "results.jsonl").read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                if rec.get("status") == "ok" and rec.get("result"):
                    out.append(rec["result"])
    return out


def build_pool(trials: Sequence[dict], exclude_tasks: Sequence[str]) -> List[dict]:
    """Exactly build_batch's filter: trial 0, non-refusal, not excluded."""
    ex = set(exclude_tasks)
    return [{"task_id": t["task_id"], "system_id": t["system_id"], "trial_index": t["trial_index"],
             "sdlc_stage": t["metadata"]["sdlc_stage"], "generated_answer": t["generated_answer"]}
            for t in trials if t["trial_index"] == 0 and not t["is_grounded_refusal"] and t["task_id"] not in ex]


def _key_of(units: Sequence[dict]) -> Dict[str, dict]:
    return {u["blind_id"]: {"task_id": u["task_id"], "system_id": u["system_id"], "trial_index": u["trial_index"]}
            for u in units}


# Fixed candidate input orders for method A (build_batch received a list; its order was not recorded).
ORDERS: Tuple[Tuple[str, Callable[[List[dict]], List[dict]]], ...] = (
    ("ledger order (dev, then val)", lambda p: list(p)),
    ("val, then dev", None),   # filled in by method_a (needs the split boundary)
    ("sorted by task, system", lambda p: sorted(p, key=lambda t: (t["task_id"], t["system_id"]))),
    ("sorted by system, task", lambda p: sorted(p, key=lambda t: (t["system_id"], t["task_id"]))),
)


def method_a(pools: Sequence[Tuple[str, List[dict]]], n: int, target: str) -> Tuple[Optional[Dict[str, dict]], str, int]:
    """Re-sample; return (key, order name, orders tried) for the first order whose bytes hash to target."""
    from experiments.m5.human_eval import sample_rating_units

    tried = 0
    for name, pool in pools:
        tried += 1
        try:
            key = _key_of(sample_rating_units(pool, n=n, seed=SEED))
        except ValueError:
            continue
        if checksum(key_bytes(key)) == target:
            return key, name, tried
    return None, "", tried


def method_b(pool: Sequence[dict], batch: RatingBatch, queries: Dict[str, str]) -> Tuple[Dict[str, dict], Dict[str, int]]:
    """Match each unit to pool trials by exact answer + query. Returns (key of unique matches, match counts)."""
    by_answer: Dict[str, List[dict]] = {}
    for t in pool:
        by_answer.setdefault(t["generated_answer"], []).append(t)
    key, counts = {}, {"units": len(batch.units), "exactly_one": 0, "none": 0, "several": 0}
    for u in batch.units:
        hits = [t for t in by_answer.get(u.answer, []) if queries.get(t["task_id"]) == u.query]
        if len(hits) == 1:
            counts["exactly_one"] += 1
            t = hits[0]
            key[u.blind_id] = {"task_id": t["task_id"], "system_id": t["system_id"], "trial_index": t["trial_index"]}
        elif not hits:
            counts["none"] += 1
        else:
            counts["several"] += 1
    return key, counts


def candidate_pools(trials_by_dir: Sequence[List[dict]], exclude: Sequence[str]) -> List[Tuple[str, List[dict]]]:
    flat = [t for ts in trials_by_dir for t in ts]
    base = build_pool(flat, exclude)
    out = []
    for name, fn in ORDERS:
        if fn is None:
            if len(trials_by_dir) < 2:
                continue
            out.append((name, build_pool([t for ts in reversed(trials_by_dir) for t in ts], exclude)))
        else:
            out.append((name, fn(base)))
    return out


def recover(batch: RatingBatch, trials_by_dir: Sequence[List[dict]], queries: Dict[str, str],
            out_path: Path) -> Dict[str, object]:
    """Run A and B; write the key to out_path only on a full match. Returns a report with counts only."""
    pools = candidate_pools(trials_by_dir, batch.excluded_tasks)
    pool = pools[0][1]
    key_a, order, tried = method_a(pools, len(batch.units), batch.key_sha256)
    key_b, counts = method_b(pool, batch, queries)
    if key_a is not None:   # how A's assignment relates to B's candidates (counts only)
        counts["a_agrees_on_unique"] = sum(1 for b, v in key_b.items() if key_a.get(b) == v)
        amb_in = 0
        for u in batch.units:
            if u.blind_id in key_b:
                continue
            a = key_a[u.blind_id]
            amb_in += any((t["task_id"], t["system_id"], t["trial_index"]) == (a["task_id"], a["system_id"], a["trial_index"])
                          and t["generated_answer"] == u.answer for t in pool)
        counts["a_pick_among_b_candidates_when_ambiguous"] = amb_in
    b_complete = counts["exactly_one"] == counts["units"]
    sum_b = checksum(key_bytes(key_b)) if b_complete else None
    rep: Dict[str, object] = {
        "batch": batch.batch_id, "pool_size": len(pool), "units": len(batch.units),
        "method_a_match": key_a is not None, "method_a_orders_tried": tried, "method_a_order": order or None,
        "method_b": counts, "method_b_checksum_match": sum_b == batch.key_sha256,
        "agree": key_a is not None and b_complete and key_a == key_b,
        "stored_checksum": batch.key_sha256, "written": None,
    }
    rep["result"] = "MATCH" if (rep["method_a_match"] and rep["method_b_checksum_match"] and rep["agree"]) else "NO MATCH"
    if rep["result"] == "MATCH":
        if out_path.exists():
            raise FileExistsError(f"{out_path} exists; a rating key is never overwritten")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        data = key_bytes(key_a)
        assert checksum(data) == batch.key_sha256
        out_path.write_bytes(data)
        rep["written"] = str(out_path)
    return rep


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--batch", default="m1-rating-01")
    p.add_argument("--out", default=None, help="key file to write (default C:/EIH_keys/<batch>_key.json)")
    args = p.parse_args(argv)
    out = Path(args.out) if args.out else DEFAULT_OUT / f"{args.batch}_key.json"
    if REPO_ROOT.resolve() in out.resolve().parents:
        print("Refused: the key must be written outside the repository", file=sys.stderr)
        return 2
    batch = RatingBatch.model_validate_json((RATING_DIR / f"{args.batch}.json").read_text(encoding="utf-8"))

    from benchmark.retrieval_labels import load_dev_val_tasks   # dev + val only; test records never loaded

    tasks, _ = load_dev_val_tasks()
    queries = {tid: t["query"] for tid, t in tasks.items()}
    rep = recover(batch, [load_trials([d]) for d in RESULT_DIRS], queries, out)
    # Counts and checksums only - never key contents.
    print(rep["result"])
    print(f"stored checksum   {rep['stored_checksum']}")
    print(f"units {rep['units']}   pool {rep['pool_size']}   method A matched: {rep['method_a_match']} "
          f"(orders tried {rep['method_a_orders_tried']}, order: {rep['method_a_order']})")
    b = rep["method_b"]
    print(f"method B: exactly one match {b['exactly_one']}, none {b['none']}, several {b['several']}; "
          f"checksum match: {rep['method_b_checksum_match']}; A and B agree: {rep['agree']}")
    if "a_agrees_on_unique" in b:
        print(f"A agrees with B on {b['a_agrees_on_unique']} of {b['exactly_one']} unique matches; A's pick is among "
              f"B's candidates on {b['a_pick_among_b_candidates_when_ambiguous']} of {b['several']} ambiguous units")
    print(f"written: {rep['written'] or 'nothing'}")
    return 0 if rep["result"] == "MATCH" else 1


if __name__ == "__main__":
    sys.exit(main())
