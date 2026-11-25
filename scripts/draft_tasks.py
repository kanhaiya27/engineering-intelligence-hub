"""
EIH-SWE drafting command line (benchmark/drafting.py).

  python scripts/draft_tasks.py spans --repo pallets/flask --stage testing --n 4 --packet flask-testing-01
  python scripts/draft_tasks.py queue --drafts benchmark/data/drafting/drafts/batch-01.jsonl --prefix draft-01
  python scripts/draft_tasks.py apply                    # approved new tasks -> benchmark/data/eih_swe_tasks.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from benchmark import drafting as dr  # noqa: E402
from benchmark.review import ReviewError  # noqa: E402


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("spans")
    sp.add_argument("--repo", required=True)
    sp.add_argument("--stage", required=True, choices=dr.STAGES)
    sp.add_argument("--n", type=int, default=4)
    sp.add_argument("--packet", required=True)
    q = sub.add_parser("queue")
    q.add_argument("--drafts", required=True)
    q.add_argument("--prefix", required=True)
    q.add_argument("--requester-offset", type=int, default=0)
    sub.add_parser("apply")
    args = p.parse_args(argv)
    try:
        if args.cmd == "spans":
            spans = dr.sample_spans(args.repo, args.stage, args.n)
            print(f"{len(spans)} spans -> {dr.write_span_packet(spans, args.packet)}")
        elif args.cmd == "queue":
            drafts = [dr.Draft.from_json(json.loads(l)) for l in Path(args.drafts).read_text(encoding="utf-8").splitlines()
                      if l.strip()]
            print(json.dumps(dr.queue_drafts(drafts, args.prefix, requester_offset=args.requester_offset), indent=2))
        elif args.cmd == "apply":
            print("approved new tasks per split:", dr.write_approved())
    except ReviewError as exc:
        print(f"Refused: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
