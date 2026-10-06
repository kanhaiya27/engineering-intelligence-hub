"""
Review queue command line (docs/REVIEW_GUIDE.md).

Reviewer commands (one command per decision):
  python scripts/review.py next    --reviewer Sanvi              show your next item, start its timer
  python scripts/review.py approve <task_id> --reviewer Sanvi    all four checks pass
  python scripts/review.py fix     <task_id> --reviewer Sanvi --failed answer_correct --note "..."
  python scripts/review.py reject  <task_id> --reviewer Sanvi --failed question_clear --note "..."

Lead commands:
  python scripts/review.py report  [--day 2026-10-06] [--json]   daily progress report
  python scripts/review.py kappa   <batch_id>                    day-one calibration agreement
  python scripts/review.py import-existing --batch <id> --purpose calibration --ids a,b,c
        --drafted-by "<who wrote them>" [--assign all]           queue existing dev/val tasks
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from benchmark.review import (  # noqa: E402
    CHECKS, ReviewBatch, ReviewError, ReviewStore, calibration_agreement, item_from_task, progress_report,
)

CHECK_HELP = ", ".join(CHECKS)


def show(batch, item, store: ReviewStore) -> str:
    done = store.current_decisions(item)
    out = [
        "=" * 78,
        f"{item.item_id}   batch {batch.batch_id}   split {store.effective_split(item)}   "
        f"needs {store.required_reviews(item)} review(s), has {len(done)}",
        f"repository {item.repository} @ {item.commit_sha[:12]}   ({item.status_note})",
        f"labels: stage={item.sdlc_stage}  type={item.task_type}  complexity={item.complexity}  "
        f"criticality={item.criticality}",
        "-" * 78, "QUESTION", item.query, "", "PROPOSED ANSWER", item.proposed_answer,
    ]
    if item.acceptable_alternatives:
        out += ["", "ALSO ACCEPTED"] + [f"  - {a}" for a in item.acceptable_alternatives]
    if not item.evidence:
        out += ["", "EVIDENCE  (none can be shown - see the note above)"]
    for e in item.evidence:
        out += ["", f"EVIDENCE  {e.file}  lines {e.start_line}-{e.end_line}"]
        out += [f"{n:>6} | {line}" for n, line in enumerate(e.text.splitlines(), start=e.start_line)]
    out += ["-" * 78, f"Check: {CHECK_HELP}",
            f"Then:  approve {item.item_id}  |  fix/reject {item.item_id} --failed <checks> --note \"...\""]
    return "\n".join(out)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--root", default=None, help=argparse.SUPPRESS)
    sub = p.add_subparsers(dest="cmd", required=True)

    n = sub.add_parser("next")
    n.add_argument("--reviewer", required=True)
    n.add_argument("--batch")
    for name in ("approve", "fix", "reject"):
        d = sub.add_parser(name)
        d.add_argument("item_id")
        d.add_argument("--reviewer", required=True)
        d.add_argument("--note", default=None)
        d.add_argument("--failed", default="", help=f"comma list of failed checks: {CHECK_HELP}")
        d.add_argument("--minutes", type=float, default=None, help="time spent, if you did not use `next`")
    r = sub.add_parser("report")
    r.add_argument("--day", default=None)
    r.add_argument("--json", action="store_true")
    k = sub.add_parser("kappa")
    k.add_argument("batch_id")
    imp = sub.add_parser("import-existing")
    imp.add_argument("--batch", required=True)
    imp.add_argument("--purpose", default="review", choices=["calibration", "review", "test_correctness_pass"])
    imp.add_argument("--ids", required=True)
    imp.add_argument("--drafted-by", required=True)
    imp.add_argument("--requested-by", default=None)
    imp.add_argument("--assign", default="", help="comma list of reviewers, or 'all'")
    args = p.parse_args(argv)

    store = ReviewStore(Path(args.root)) if args.root else ReviewStore()
    try:
        if args.cmd == "next":
            found = store.next_item(args.reviewer, args.batch)
            if not found:
                print("Nothing left for you in the queue.")
                return 0
            batch, item = found
            store.start(args.reviewer, item.item_id)
            print(show(batch, item, store))
        elif args.cmd in ("approve", "fix", "reject"):
            failed = [c.strip() for c in args.failed.split(",") if c.strip()]
            rec = store.decide(args.item_id, args.reviewer, args.cmd, failed=failed, note=args.note,
                               minutes=args.minutes)
            _, item = store.find(args.item_id)
            print(f"Recorded: {rec.reviewer} {rec.decision} {rec.item_id} ({rec.minutes_spent} min). "
                  f"Item is now {store.status(item)}.")
        elif args.cmd == "report":
            ledgers = sorted((REPO_ROOT / "experiments" / "results" / "queue").glob("*/*/results.jsonl"))
            rep = progress_report(store, args.day, ledgers, REPO_ROOT / "ASK_ME.md")
            if args.json:
                print(json.dumps(rep, indent=2))
            else:
                for key, val in rep.items():
                    print(f"{key:28} {val}")
                if rep["reject_alert"]:
                    print("\nALERT: reject rate above 30% - fix the drafting prompt; do not loosen approval.")
        elif args.cmd == "kappa":
            print(json.dumps(calibration_agreement(store, args.batch_id), indent=2))
        elif args.cmd == "import-existing":
            from benchmark import retrieval_labels as rl

            splits = json.loads(rl.SPLITS_PATH.read_text(encoding="utf-8"))["splits"]
            split_of = {t: s for s, ids in splits.items() for t in ids}
            ids = [i.strip() for i in args.ids.split(",") if i.strip()]
            test_ids = [i for i in ids if split_of.get(i) == "test"]
            if test_ids and args.purpose != "test_correctness_pass":
                raise ReviewError(f"held-out test tasks {test_ids} may be queued only with "
                                  "--purpose test_correctness_pass (two reviewers, before any tuning)")
            tasks = {t["task_id"]: t for t in json.loads(rl.TASKS_PATH.read_text(encoding="utf-8"))["tasks"]
                     if t["task_id"] in ids}
            missing = sorted(set(ids) - set(tasks))
            if missing:
                raise ReviewError(f"unknown task ids {missing}")
            labels = {l["task_id"]: l for l in json.loads(rl.LABELS_PATH.read_text(encoding="utf-8"))["labels"]}
            items = [item_from_task(tasks[i], split_of.get(i, "unassigned"), args.drafted_by, args.requested_by,
                                    labels.get(i), allow_evidence_defects=args.purpose == "test_correctness_pass")
                     for i in ids]
            assign = store.reviewers() if args.assign == "all" else [
                store.resolve_reviewer(a) for a in args.assign.split(",") if a.strip()]
            batch = ReviewBatch(batch_id=args.batch, created_at=datetime.now(timezone.utc).isoformat(),
                                purpose=args.purpose, assigned_to=assign, items=items)
            print(f"Queued {len(items)} items in {store.save_batch(batch)}")
    except ReviewError as exc:
        print(f"Refused: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
