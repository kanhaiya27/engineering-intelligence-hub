"""
Independent outcome measures for Mode Q (master prompt Step 1e/1f; plan C3 "retrieval and
generation scored independently").

Why: System E's quality gate uses four evaluators (citation grounding, relevance, coverage,
consistency) that judge an answer against the chunks the system itself retrieved. Scoring the
outcome with the same evaluators makes RQ3 circular, because E is optimised to pass them. These
measures use only the answer text and the human-checked retrieval labels (the evidence spans in
the pinned source). They never see the retrieved chunks or any gate signal.

Per answer:
  refusal               the answer says INSUFFICIENT EVIDENCE (reported separately, never a success)
  line_citations        citations of the form [path:Lx-Ly] / [path:Lx], parsed strictly here
                        (not with the gate's own parser)
  cited_span_precision  share of line citations that overlap a labelled evidence span
                        (None if the answer has no line citation)
  cited_span_recall     share of labelled spans overlapped by at least one line citation
  cited_file_recall     share of the label's relevant files cited at all (with or without lines)
  supported             non-refusal answer with at least one line citation inside a labelled span;
                        False otherwise (including answers that cite nothing). None for refusals.
  unsupported           not supported (None for refusals). The RQ3 outcome is the unsupported-answer
                        rate over non-refusal answers, reported together with the refusal rate.

With no label for the task (test labels not yet made, external sets), every span measure is None,
and the trial is counted as "no label". Nothing is filled in.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from evaluation.retrieval_metrics import Label, primary_of

REFUSAL_MARKER = "INSUFFICIENT EVIDENCE"

# [path:L12-L30], [`path:L12-30`], [path:L7], [path:12-30]; path needs a file extension.
_LINE_CITATION = re.compile(
    r"\[\s*`?(?P<path>[A-Za-z0-9_\-./]+\.[A-Za-z0-9]+):L?(?P<start>\d+)(?:\s*-\s*L?(?P<end>\d+))?`?\s*\]"
)
# File-only citations: [path] / [`path`] with an extension and at least one slash or a known suffix.
_FILE_CITATION = re.compile(r"\[\s*`?(?P<path>[A-Za-z0-9_\-./]+/[A-Za-z0-9_\-.]+\.[A-Za-z0-9]+)`?\s*\]")


def parse_citations(answer: str) -> Tuple[List[Tuple[str, int, int]], List[str]]:
    """(line citations as (path, start, end), file-only citation paths) in order of appearance."""
    text = re.sub(r"```[\s\S]*?```", "", answer or "")
    lines = []
    for m in _LINE_CITATION.finditer(text):
        start = int(m.group("start"))
        end = int(m.group("end")) if m.group("end") else start
        if end < start:
            start, end = end, start
        lines.append((_norm(m.group("path")), start, end))
    files = [_norm(m.group("path")) for m in _FILE_CITATION.finditer(text)]
    return lines, files


def _norm(path: str) -> str:
    path = path.replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    return path


@dataclass
class Outcome:
    refusal: bool
    has_label: bool
    line_citations: int
    file_only_citations: int
    cited_span_precision: Optional[float]
    cited_span_recall: Optional[float]
    cited_file_recall: Optional[float]
    supported: Optional[bool]
    unsupported: Optional[bool]

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


def outcome(answer: str, label: Optional[Label]) -> Outcome:
    refusal = REFUSAL_MARKER in (answer or "")
    lines, files = parse_citations(answer)
    if label is None:
        return Outcome(refusal, False, len(lines), len(files), None, None, None, None, None)

    def in_span(path: str, s: int, e: int) -> set:
        return {j for j, sp in enumerate(label.spans) if path == sp.file and s <= sp.end_line and sp.start_line <= e}

    hits = [in_span(*c) for c in lines]
    precision = (sum(1 for h in hits if h) / len(lines)) if lines else None
    covered = set().union(*hits) if hits else set()
    recall = len(covered) / len(label.spans) if label.spans else None

    alt = {a: primary_of(a, label.relevant_files) for a in label.alternative_files}
    cited_files = {alt.get(p, p) for p in [c[0] for c in lines] + files}
    file_recall = len(cited_files & set(label.relevant_files)) / len(label.relevant_files) if label.relevant_files else None

    supported = None if refusal else bool(covered)
    return Outcome(refusal, True, len(lines), len(files), precision, recall, file_recall, supported,
                   None if supported is None else not supported)


@dataclass
class OutcomeRates:
    trials: int
    no_label: int
    refusals: int
    refusal_rate: float
    answered_with_label: int
    unsupported: int
    unsupported_rate: Optional[float]          # over non-refusal answers that have a label
    mean_cited_span_precision: Optional[float]  # over answers with >= 1 line citation
    answers_with_line_citations: int
    mean_cited_span_recall: Optional[float]     # over non-refusal answers with a label

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


def rates(outcomes: Sequence[Outcome]) -> OutcomeRates:
    n = len(outcomes)
    labelled = [o for o in outcomes if o.has_label]
    answered = [o for o in labelled if not o.refusal]
    with_lines = [o for o in answered if o.cited_span_precision is not None]
    unsup = sum(1 for o in answered if o.unsupported)
    refusals = sum(1 for o in outcomes if o.refusal)
    return OutcomeRates(
        trials=n, no_label=n - len(labelled), refusals=refusals,
        refusal_rate=refusals / n if n else 0.0,
        answered_with_label=len(answered), unsupported=unsup,
        unsupported_rate=unsup / len(answered) if answered else None,
        mean_cited_span_precision=(sum(o.cited_span_precision for o in with_lines) / len(with_lines)
                                   if with_lines else None),
        answers_with_line_citations=len(with_lines),
        mean_cited_span_recall=(sum(o.cited_span_recall for o in answered) / len(answered) if answered else None),
    )
