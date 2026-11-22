"""
OKF bundles: discovery, link resolution, conformance, search, index and log files.

A bundle is a directory tree of markdown files (OKF v0.2 §3). Every non-reserved `.md`
file is a concept whose ID is its bundle-relative path without `.md` (§2). `index.md`
and `log.md` are reserved at every level (§3.1).

The consumer is deliberately permissive, exactly as §11 requires: it never rejects a
bundle for missing optional fields, unknown types or keys, broken links or missing
indexes. It *reports* non-conformant files (no frontmatter, no `type`) instead of
silently dropping them, so a human can see and fix them.

Writes go through `write_concept` / `append_log` / `regenerate_indexes`, which refuse
any path that would escape the bundle root.
"""

from __future__ import annotations

import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Dict, Iterable, List, Optional, Set, Tuple

from knowledge.okf.document import OKF_VERSION, OKFDocument, OKFParseError

_SEGMENT_RX = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.\-]*$")
# [text](target) but not images ![alt](src); target stops at whitespace or ')'.
_LINK_RX = re.compile(r"(?<!!)\[([^\]]*)\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
_SCHEME_RX = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*:")
_LOG_DATE_RX = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SKIP_DIRS = {".git", ".eih", "node_modules", "__pycache__"}


class OKFPathError(ValueError):
    """A concept ID or link target that is invalid or escapes the bundle."""


def validate_concept_id(concept_id: str) -> str:
    """Normalise and validate a concept ID ('tables/orders'); refuse traversal."""
    cid = concept_id.strip().strip("/")
    if cid.endswith(".md"):
        cid = cid[:-3]
    parts = cid.split("/")
    if not cid or any(not _SEGMENT_RX.match(p) or p in (".", "..") for p in parts):
        raise OKFPathError(f"invalid concept id: {concept_id!r}")
    if parts[-1] in ("index", "log"):
        raise OKFPathError(f"'{parts[-1]}.md' is a reserved filename (§3.1)")
    return cid


@dataclass
class Link:
    source: str  # concept id
    text: str
    target_raw: str
    target: Optional[str]  # resolved concept id, or directory id ending in '/', or None
    external: bool
    broken: bool


@dataclass
class Issue:
    path: str
    severity: str  # "error" (non-conformant, §11) | "warning" (soft guidance)
    message: str


@dataclass
class Concept:
    id: str
    path: Path
    doc: OKFDocument

    @property
    def title(self) -> str:
        return self.doc.title(fallback=self.id.rsplit("/", 1)[-1].replace("-", " ").replace("_", " "))


@dataclass
class ConformanceReport:
    concepts: int
    index_files: int
    log_files: int
    errors: List[Issue] = field(default_factory=list)
    warnings: List[Issue] = field(default_factory=list)
    broken_links: List[Link] = field(default_factory=list)
    declared_version: Optional[str] = None

    @property
    def conformant(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict:
        return {
            "conformant": self.conformant,
            "declared_okf_version": self.declared_version,
            "concepts": self.concepts,
            "index_files": self.index_files,
            "log_files": self.log_files,
            "errors": [vars(i) for i in self.errors],
            "warnings": [vars(i) for i in self.warnings],
            "broken_links": [
                {"source": l.source, "target": l.target_raw, "text": l.text} for l in self.broken_links
            ],
        }


class OKFBundle:
    """A bundle on disk. Load once, then query; call `reload()` after external edits."""

    def __init__(self, root: Path | str):
        self.root = Path(root).resolve()
        if not self.root.is_dir():
            raise FileNotFoundError(f"OKF bundle directory not found: {self.root}")
        self.concepts: Dict[str, Concept] = {}
        self.unparseable: Dict[str, str] = {}  # rel path -> error
        self.index_files: List[Path] = []
        self.log_files: List[Path] = []
        self._links: Optional[List[Link]] = None
        self.reload()

    # ------------------------------------------------------------------ discovery

    def reload(self) -> None:
        self.concepts.clear()
        self.unparseable.clear()
        self.index_files.clear()
        self.log_files.clear()
        self._links = None
        for path in self._walk_markdown():
            rel = path.relative_to(self.root).as_posix()
            if path.name == "index.md":
                self.index_files.append(path)
                continue
            if path.name == "log.md":
                self.log_files.append(path)
                continue
            try:
                doc = OKFDocument.parse(path.read_text(encoding="utf-8"))
            except (OKFParseError, UnicodeDecodeError) as exc:
                self.unparseable[rel] = str(exc)
                continue
            cid = rel[:-3]
            self.concepts[cid] = Concept(id=cid, path=path, doc=doc)

    def _walk_markdown(self) -> Iterable[Path]:
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = sorted(d for d in dirnames if d not in _SKIP_DIRS and not d.startswith("."))
            for name in sorted(filenames):
                if name.lower().endswith(".md"):
                    yield Path(dirpath) / name

    @property
    def declared_version(self) -> Optional[str]:
        """okf_version from the bundle-root index.md frontmatter (§12), if any."""
        idx = self.root / "index.md"
        if not idx.exists():
            return None
        try:
            doc = OKFDocument.parse(idx.read_text(encoding="utf-8"))
        except OKFParseError:
            return None
        v = doc.frontmatter.get("okf_version")
        return str(v) if v is not None else None

    def get(self, concept_id: str) -> Optional[Concept]:
        return self.concepts.get(concept_id.strip("/").removesuffix(".md"))

    def path_for(self, concept_id: str) -> Path:
        cid = validate_concept_id(concept_id)
        path = (self.root / (cid + ".md")).resolve()
        if self.root not in path.parents:
            raise OKFPathError(f"path escapes bundle: {concept_id!r}")
        return path

    # ------------------------------------------------------------------ links (§6)

    def resolve_link(self, source_id: str, target: str) -> Tuple[Optional[str], bool]:
        """Resolve a link target from a concept. Returns (resolved id, external).

        Absolute links start with '/' (bundle root); others are relative to the source
        concept's directory. A fragment (#...) or query is ignored. A link to a directory
        resolves to '<dir>/' (its index). None means outside the bundle.
        """
        if _SCHEME_RX.match(target) or target.startswith("//"):
            return None, True
        t = target.split("#", 1)[0].split("?", 1)[0]
        if not t:
            return source_id, False  # same-document anchor
        if t.startswith("/"):
            combined = PurePosixPath("/" + t.lstrip("/"))
        else:
            combined = PurePosixPath("/" + source_id).parent / t
        parts: List[str] = []
        for seg in combined.parts[1:]:
            if seg in ("", "."):
                continue
            if seg == "..":
                if not parts:
                    return None, False  # escapes the bundle root
                parts.pop()
                continue
            parts.append(seg)
        joined = "/".join(parts)
        if t.endswith("/") or (self.root / joined).is_dir():
            return (joined + "/") if joined else "/", False
        if joined.endswith(".md"):
            joined = joined[:-3]
        return joined, False

    def links(self) -> List[Link]:
        if self._links is None:
            out: List[Link] = []
            for cid, c in self.concepts.items():
                out.extend(self._extract_links(cid, c.doc.body))
            self._links = out
        return self._links

    def _extract_links(self, source_id: str, body: str) -> List[Link]:
        found: List[Link] = []
        in_fence = False
        for line in body.splitlines():
            if line.lstrip().startswith(("```", "~~~")):
                in_fence = not in_fence
                continue
            if in_fence or line.startswith("    "):
                continue
            for m in _LINK_RX.finditer(line):
                raw = m.group(2)
                resolved, external = self.resolve_link(source_id, raw)
                broken = False
                if not external:
                    if resolved is None:
                        broken = True
                    elif resolved.endswith("/"):
                        broken = not (self.root / resolved.rstrip("/")).is_dir() and resolved != "/"
                    elif resolved == source_id:
                        broken = False
                    else:
                        broken = resolved not in self.concepts
                found.append(Link(source_id, m.group(1), raw, resolved, external, broken))
        return found

    def outgoing(self, concept_id: str) -> List[Link]:
        return [l for l in self.links() if l.source == concept_id]

    def backlinks(self, concept_id: str) -> List[Link]:
        return [l for l in self.links() if l.target == concept_id and l.source != concept_id]

    def concept_edges(self) -> List[Tuple[str, str]]:
        """Directed, de-duplicated concept→concept edges (untyped, §6.1)."""
        seen: Set[Tuple[str, str]] = set()
        for l in self.links():
            if l.external or l.broken or not l.target or l.target.endswith("/") or l.target == l.source:
                continue
            seen.add((l.source, l.target))
        return sorted(seen)

    def neighbours(self, concept_id: str, hops: int = 1) -> List[str]:
        """Concepts reachable within `hops` links in either direction (excluding itself)."""
        adj: Dict[str, Set[str]] = defaultdict(set)
        for a, b in self.concept_edges():
            adj[a].add(b)
            adj[b].add(a)
        frontier, seen = {concept_id}, {concept_id}
        for _ in range(max(0, hops)):
            frontier = {n for f in frontier for n in adj[f]} - seen
            seen |= frontier
        seen.discard(concept_id)
        return sorted(seen)

    # ------------------------------------------------------------------ conformance (§11)

    def conformance(self) -> ConformanceReport:
        rep = ConformanceReport(
            concepts=len(self.concepts),
            index_files=len(self.index_files),
            log_files=len(self.log_files),
            declared_version=self.declared_version,
        )
        for rel, err in sorted(self.unparseable.items()):
            rep.errors.append(Issue(rel, "error", f"unparseable frontmatter: {err} (§11.1)"))
        for cid, c in sorted(self.concepts.items()):
            rel = cid + ".md"
            rep.errors.extend(Issue(rel, "error", m) for m in c.doc.validate())
            rep.warnings.extend(Issue(rel, "warning", m) for m in c.doc.warnings())
        for idx in self.index_files:
            rep.errors.extend(self._check_index(idx))
        for log in self.log_files:
            rep.errors.extend(self._check_log(log))
        rep.broken_links = [l for l in self.links() if l.broken]
        if rep.declared_version and rep.declared_version.split(".")[0] != OKF_VERSION.split(".")[0]:
            rep.warnings.append(Issue("index.md", "warning",
                                      f"declares okf_version {rep.declared_version}; read best-effort (§12)"))
        return rep

    def _check_index(self, path: Path) -> List[Issue]:
        rel = path.relative_to(self.root).as_posix()
        text = path.read_text(encoding="utf-8")
        if not text.lstrip("﻿").startswith("---"):
            return []
        if path.parent != self.root:
            return [Issue(rel, "error", "index.md must not carry frontmatter below the bundle root (§8)")]
        try:
            doc = OKFDocument.parse(text)
        except OKFParseError as exc:
            return [Issue(rel, "error", f"unparseable index frontmatter: {exc}")]
        extra = set(doc.frontmatter) - {"okf_version"}
        if extra:
            return [Issue(rel, "error", f"root index.md frontmatter may only hold okf_version, found {sorted(extra)} (§8)")]
        return []

    def _check_log(self, path: Path) -> List[Issue]:
        rel = path.relative_to(self.root).as_posix()
        out = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("## "):
                heading = line[3:].strip()
                if not _LOG_DATE_RX.match(heading):
                    out.append(Issue(rel, "error", f"log date heading '{heading}' is not YYYY-MM-DD (§9)"))
        return out

    # ------------------------------------------------------------------ search

    def search(self, query: str, limit: int = 20, type_filter: Optional[str] = None,
               tag: Optional[str] = None) -> List[Tuple[Concept, float]]:
        """Lexical search over title (×3), description (×2), tags (×2), type and body."""
        terms = [t for t in re.findall(r"[a-z0-9_]+", query.lower()) if len(t) > 1]
        results = []
        for c in self.concepts.values():
            if type_filter and c.doc.type != type_filter:
                continue
            if tag and tag not in c.doc.tags:
                continue
            if not terms:
                results.append((c, 0.0))
                continue
            fields = [
                (c.title.lower(), 3.0),
                (c.doc.description.lower(), 2.0),
                (" ".join(c.doc.tags).lower(), 2.0),
                (c.doc.type.lower(), 1.0),
                (c.id.lower(), 1.0),
                (c.doc.body.lower(), 0.5),
            ]
            score = 0.0
            for term in terms:
                for text, w in fields:
                    n = text.count(term)
                    if n:
                        score += w * (1 + min(n, 5) * 0.1)
            if score > 0:
                results.append((c, round(score, 3)))
        results.sort(key=lambda r: (-r[1], r[0].id))
        return results[:limit]

    def types(self) -> Dict[str, int]:
        out: Dict[str, int] = defaultdict(int)
        for c in self.concepts.values():
            out[c.doc.type or "(missing)"] += 1
        return dict(sorted(out.items()))

    def tags(self) -> Dict[str, int]:
        out: Dict[str, int] = defaultdict(int)
        for c in self.concepts.values():
            for t in c.doc.tags:
                out[t] += 1
        return dict(sorted(out.items()))

    # ------------------------------------------------------------------ writes

    def write_concept(self, concept_id: str, doc: OKFDocument) -> Path:
        errors = doc.validate()
        if errors:
            raise ValueError(f"refusing to write a non-conformant concept: {errors}")
        path = self.path_for(concept_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".md.tmp")
        tmp.write_text(doc.serialize(), encoding="utf-8", newline="\n")
        os.replace(tmp, path)
        cid = validate_concept_id(concept_id)
        self.concepts[cid] = Concept(id=cid, path=path, doc=doc)
        self._links = None
        return path

    def append_log(self, entries: List[str], day: Optional[date] = None, scope: str = "") -> Path:
        """Add entries under today's ISO date heading in <scope>/log.md, newest first (§9)."""
        d = (day or date.today()).isoformat()
        scope_dir = (self.root / scope).resolve() if scope else self.root
        if scope_dir != self.root and self.root not in scope_dir.parents:
            raise OKFPathError(f"log scope escapes bundle: {scope!r}")
        scope_dir.mkdir(parents=True, exist_ok=True)
        path = scope_dir / "log.md"
        lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else ["# Update Log"]
        new = [f"* {e}" for e in entries]
        heading = f"## {d}"
        if heading in lines:
            i = lines.index(heading) + 1
            lines[i:i] = new
        else:
            first = next((i for i, l in enumerate(lines) if l.startswith("## ")), len(lines))
            block = [heading] + new + [""]
            if first == len(lines) and lines and lines[-1].strip():
                block = [""] + block
            lines[first:first] = block
        path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8", newline="\n")
        if path not in self.log_files:
            self.log_files.append(path)
        return path

    def regenerate_indexes(self, declare_version: bool = True) -> List[Path]:
        """Write deterministic index.md files (§8) for every directory holding concepts.

        Sections group entries by concept type; each entry carries the concept's
        description. Subdirectories are listed with their concept count. No LLM is used.
        """
        dirs: Set[Path] = {self.root}
        for c in self.concepts.values():
            p = c.path.parent
            while p != self.root and self.root in p.parents:
                dirs.add(p)
                p = p.parent
        written = []
        for d in sorted(dirs, key=lambda p: (-len(p.parts), str(p))):
            grouped: Dict[str, List[Tuple[str, str, str]]] = defaultdict(list)
            for c in self.concepts.values():
                if c.path.parent == d:
                    grouped[c.doc.type or "Other"].append((c.title, c.path.name, c.doc.description))
            subdirs = sorted(s for s in dirs if s.parent == d)
            sections = []
            for typ in sorted(grouped):
                lines = [f"# {typ}", ""]
                for title, link, desc in sorted(grouped[typ], key=lambda e: e[0].lower()):
                    lines.append(f"* [{title}]({link})" + (f" - {desc}" if desc else ""))
                sections.append("\n".join(lines))
            if subdirs:
                lines = ["# Directories", ""]
                for s in subdirs:
                    n = sum(1 for c in self.concepts.values() if s == c.path.parent or s in c.path.parents)
                    lines.append(f"* [{s.name}]({s.name}/) - {n} concept{'s' if n != 1 else ''}")
                sections.append("\n".join(lines))
            text = "\n\n".join(sections) + "\n"
            if d == self.root and declare_version:
                text = f"---\nokf_version: \"{OKF_VERSION}\"\n---\n\n" + text
            path = d / "index.md"
            path.write_text(text, encoding="utf-8", newline="\n")
            written.append(path)
        self.index_files = sorted(set(self.index_files) | set(written))
        return written
