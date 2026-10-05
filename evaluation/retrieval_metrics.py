"""
Mode R retrieval metrics (original plan §7.4, §9.2): Recall@K, Precision@K, MRR, nDCG@K.

Scored against the retrieval labels (benchmark/data/retrieval_labels_v1.json) at two levels.

File level. The ranked list is the retrieved chunks' files, in rank order, keeping each file's
first occurrence. A file is relevant if it is in `relevant_files`. A near-identical variant
listed in `alternative_files` counts as its primary file, so retrieving one counts the same.

Span level. The ranked list is the retrieved chunks themselves. A chunk is relevant if it
overlaps a labelled evidence span (same file, line ranges intersect). Recall@K is the share of
labelled spans that some top-K chunk overlaps. Precision, MRR and nDCG treat chunks as the
documents: the ideal ranking puts min(K, R) relevant chunks first, where R is the number of
indexed chunks that overlap any labelled span (the label's `chunk_ids`).

Definitions (binary relevance, the standard IR forms):
  Recall@K    = relevant items found in the top K / all relevant items
                (files: distinct relevant files; spans: labelled spans)
  Precision@K = relevant retrieved items in the top K / K   (K, not the number returned, so a
                system is not rewarded for returning fewer items)
  MRR         = 1 / rank of the first relevant retrieved item (0 if none), averaged over tasks
  nDCG@K      = DCG@K / IDCG@K, gain 1 per relevant item (files: a file that finds a
                not-yet-found relevant file; chunks: a chunk overlapping a span), discount
                1/log2(rank + 1); IDCG puts min(K, #relevant) relevant items first

Graph-context chunks (System D/E) name files and relations but carry no source text. They count
at file level, because the model is pointed at that file. They are excluded at span level unless
`include_graph=True`. Both variants are reported.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

DEFAULT_KS: Tuple[int, ...] = (1, 3, 5, 10)


@dataclass(frozen=True)
class RetrievedItem:
    """One retrieved chunk, in rank order."""

    file: Optional[str]
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    is_graph: bool = False


@dataclass(frozen=True)
class Span:
    file: str
    start_line: int
    end_line: int


@dataclass
class Label:
    task_id: str
    relevant_files: List[str]
    spans: List[Span]
    alternative_files: List[str] = field(default_factory=list)
    n_relevant_chunks: Optional[int] = None  # indexed chunks overlapping any span

    @classmethod
    def from_json(cls, d: dict) -> "Label":
        chunk_ids = {c for e in d["required_evidence"] for c in e.get("chunk_ids", [])}
        return cls(task_id=d["task_id"], relevant_files=list(d["relevant_files"]),
                   spans=[Span(e["file"], e["start_line"], e["end_line"]) for e in d["required_evidence"]],
                   alternative_files=list(d.get("alternative_files", [])),
                   n_relevant_chunks=len(chunk_ids) or None)


def primary_of(alt: str, relevant_files: Sequence[str]) -> str:
    """The relevant file a near-identical variant stands for (same directory, stem + '_suffix').

    e.g. docs_src/x/tutorial004_an_py310.py -> docs_src/x/tutorial004.py
    """
    a = PurePosixPath(alt)
    hits = [f for f in relevant_files
            if PurePosixPath(f).parent == a.parent and a.stem.startswith(PurePosixPath(f).stem + "_")]
    if len(hits) != 1:
        raise ValueError(f"alternative {alt} maps to {len(hits)} relevant files: {hits}")
    return hits[0]


def _norm_path(path: Optional[str]) -> Optional[str]:
    if not path:
        return path
    path = path.replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    return path


def _dcg(gains: Sequence[int]) -> float:
    return sum(g / math.log2(i + 2) for i, g in enumerate(gains))


def _metrics_from_gains(first_hit_gains: Sequence[int], relevant_flags: Sequence[bool], n_relevant: int,
                        ks: Sequence[int]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    first_rel = next((i for i, r in enumerate(relevant_flags) if r), None)
    out["mrr"] = 0.0 if first_rel is None else 1.0 / (first_rel + 1)
    for k in ks:
        found = sum(first_hit_gains[:k])
        out[f"recall@{k}"] = found / n_relevant if n_relevant else 0.0
        out[f"precision@{k}"] = sum(relevant_flags[:k]) / k
        ideal = _dcg([1] * min(k, n_relevant))
        out[f"ndcg@{k}"] = _dcg(first_hit_gains[:k]) / ideal if ideal else 0.0
    return out


def file_level(items: Sequence[RetrievedItem], label: Label, ks: Sequence[int] = DEFAULT_KS) -> Dict[str, float]:
    """Metrics over the de-duplicated ranked list of files."""
    alt_map = {a: primary_of(a, label.relevant_files) for a in label.alternative_files}
    relevant = set(label.relevant_files)
    ranked: List[str] = []
    for it in items:
        f = _norm_path(it.file)
        if f and f not in ranked:
            ranked.append(f)
    found, gains, flags = set(), [], []
    for f in ranked:
        target = alt_map.get(f, f)
        hit = target in relevant
        flags.append(hit)
        gains.append(1 if hit and target not in found else 0)
        if hit:
            found.add(target)
    out = _metrics_from_gains(gains, flags, len(relevant), ks)
    out["n_ranked"] = float(len(ranked))
    return out


def _overlaps(it: RetrievedItem, label: Label) -> set:
    f = _norm_path(it.file)
    if it.start_line is None or it.end_line is None:
        return set()
    return {j for j, s in enumerate(label.spans)
            if f == s.file and it.start_line <= s.end_line and s.start_line <= it.end_line}


def span_level(items: Sequence[RetrievedItem], label: Label, ks: Sequence[int] = DEFAULT_KS,
               include_graph: bool = False) -> Dict[str, float]:
    """Metrics over the ranked list of chunks against the labelled evidence spans."""
    if not label.spans:
        raise ValueError(f"{label.task_id}: no evidence spans")
    ranked = [it for it in items if include_graph or not it.is_graph]
    hits = [_overlaps(it, label) for it in ranked]
    flags = [bool(h) for h in hits]
    n_rel = label.n_relevant_chunks or len(label.spans)
    out = _metrics_from_gains([int(f) for f in flags], flags, n_rel, ks)
    for k in ks:
        covered = set().union(*hits[:k]) if hits[:k] else set()
        out[f"recall@{k}"] = len(covered) / len(label.spans)
    out["n_ranked"] = float(len(ranked))
    return out


def mean_metrics(per_task: Iterable[Dict[str, float]]) -> Dict[str, float]:
    rows = list(per_task)
    if not rows:
        return {}
    return {k: sum(r[k] for r in rows) / len(rows) for k in rows[0]}


def items_from_chunks(chunks: Iterable) -> List[RetrievedItem]:
    """RetrievedItems from RetrievedChunk objects (knowledge.schemas.tasks), in order."""
    out = []
    for c in chunks:
        md = c.metadata or {}
        out.append(RetrievedItem(
            file=c.source_path or md.get("file_path") or md.get("source_path"),
            start_line=md.get("start_line"), end_line=md.get("end_line"),
            is_graph=bool(md.get("graph_context")),
        ))
    return out
