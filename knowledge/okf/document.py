"""
OKF concept documents: parse, serialize, validate (Open Knowledge Format v0.2, reads v0.1).

Spec: https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md
(Apache-2.0). Section numbers in comments refer to that document.

A concept is a UTF-8 markdown file: a YAML frontmatter block between two `---` lines,
then a markdown body (§4). `type` is the only required key (§4.1, §11). Everything else
is optional, and unknown keys are preserved on round-trip (§4.1 "Extensions").

Timestamps are kept as the text the author wrote: PyYAML's YAML-1.1 timestamp resolver
would turn `2026-06-30T14:00:00Z` into a datetime and re-dump it differently, silently
rewriting someone else's document. The reference implementation drops the same resolver.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import yaml

OKF_VERSION = "0.2"
REQUIRED_KEYS = ("type",)
RESERVED_FILENAMES = ("index.md", "log.md")
FRONTMATTER_DELIM = "---"

TRUST_UNVERIFIED = "unverified"
TRUST_MACHINE = "machine-confirmed"
TRUST_HUMAN = "human-reviewed"

STATUSES = ("draft", "stable", "deprecated")


class _StringTimestampLoader(yaml.SafeLoader):
    """SafeLoader without the implicit timestamp resolver (values stay strings)."""


_StringTimestampLoader.yaml_implicit_resolvers = {
    ch: [(tag, rx) for tag, rx in resolvers if tag != "tag:yaml.org,2002:timestamp"]
    for ch, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


class OKFParseError(ValueError):
    """The file is not a parseable OKF concept (bad or unterminated frontmatter)."""


def utc_now_iso() -> str:
    """ISO 8601 with explicit UTC offset, second precision (§5)."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass
class OKFDocument:
    """One concept: frontmatter mapping + markdown body."""

    frontmatter: Dict[str, Any] = field(default_factory=dict)
    body: str = ""
    has_frontmatter: bool = True

    # ------------------------------------------------------------------ parse / serialize

    @classmethod
    def parse(cls, text: str) -> "OKFDocument":
        """Parse a concept. A file without a leading `---` has no frontmatter (not an error
        here; `validate()` reports it, because §11 requires frontmatter on concepts)."""
        if text.startswith("﻿"):
            text = text[1:]
        lines = text.splitlines()
        if not lines or lines[0].strip() != FRONTMATTER_DELIM:
            return cls(frontmatter={}, body=text, has_frontmatter=False)
        end = next((i for i in range(1, len(lines)) if lines[i].strip() == FRONTMATTER_DELIM), None)
        if end is None:
            raise OKFParseError("unterminated YAML frontmatter block")
        try:
            fm = yaml.load("\n".join(lines[1:end]), Loader=_StringTimestampLoader)
        except yaml.YAMLError as exc:
            raise OKFParseError(f"invalid YAML in frontmatter: {exc}") from exc
        if fm is None:
            fm = {}
        if not isinstance(fm, dict):
            raise OKFParseError("frontmatter must be a YAML mapping")
        body = "\n".join(lines[end + 1:])
        if body.startswith("\n"):
            body = body[1:]
        if text.endswith("\n") and body and not body.endswith("\n"):
            body += "\n"
        return cls(frontmatter=fm, body=body, has_frontmatter=True)

    def serialize(self) -> str:
        """Frontmatter (key order preserved) + blank line + body, ending in a newline."""
        fm_text = yaml.safe_dump(
            self.frontmatter, sort_keys=False, allow_unicode=True, default_flow_style=False, width=100
        ).rstrip()
        body = self.body if self.body.endswith("\n") or not self.body else self.body + "\n"
        return f"{FRONTMATTER_DELIM}\n{fm_text}\n{FRONTMATTER_DELIM}\n\n{body}"

    # ------------------------------------------------------------------ validation (§11)

    def validate(self) -> List[str]:
        """Conformance errors for a concept document (empty list = conformant)."""
        if not self.has_frontmatter:
            return ["missing YAML frontmatter block (§11.1)"]
        errors = []
        for key in REQUIRED_KEYS:
            val = self.frontmatter.get(key)
            if val is None or (isinstance(val, str) and not val.strip()):
                errors.append(f"missing or empty required field '{key}' (§11.2)")
        return errors

    def warnings(self) -> List[str]:
        """Soft guidance (§11: consumers MUST NOT reject for these)."""
        fm = self.frontmatter
        out = []
        status = fm.get("status")
        if status is not None and status not in STATUSES:
            out.append(f"status '{status}' is not one of {', '.join(STATUSES)} (§5.4)")
        gen = fm.get("generated")
        if gen is not None and (not isinstance(gen, dict) or not gen.get("by")):
            out.append("generated must be a mapping with 'by' (§5.2)")
        for ev in normalize_verified(fm):
            if not ev.get("by"):
                out.append("verified entry without 'by' (§5.2)")
        for src in fm.get("sources") or []:
            if not isinstance(src, dict) or not src.get("resource"):
                out.append("sources entry without 'resource' (§5.1)")
        if fm.get("type") == "Attested Computation" and not fm.get("runtime"):
            out.append("Attested Computation without 'runtime' (§10.2)")
        sa = fm.get("stale_after")
        if sa is not None and _parse_instant(str(sa)) is None:
            out.append("stale_after is not an ISO 8601 datetime with UTC offset (§5.5)")
        if "timestamp" in fm and "generated" not in fm:
            out.append("v0.1 'timestamp' used; v0.2 records this as generated.at (§13.1)")
        return out

    # ------------------------------------------------------------------ derived properties

    @property
    def type(self) -> str:
        return str(self.frontmatter.get("type") or "")

    def title(self, fallback: str = "") -> str:
        return str(self.frontmatter.get("title") or fallback)

    @property
    def description(self) -> str:
        return str(self.frontmatter.get("description") or "")

    @property
    def tags(self) -> List[str]:
        tags = self.frontmatter.get("tags") or []
        if isinstance(tags, str):
            return [tags]
        return [str(t) for t in tags] if isinstance(tags, list) else []

    @property
    def status(self) -> str:
        """Absent status ⇒ stable (§5.4)."""
        return str(self.frontmatter.get("status") or "stable")

    @property
    def generated_by(self) -> Optional[str]:
        gen = self.frontmatter.get("generated")
        return str(gen.get("by")) if isinstance(gen, dict) and gen.get("by") else None

    @property
    def generated_at(self) -> Optional[str]:
        """generated.at, falling back to the v0.1 `timestamp` (§13.1)."""
        gen = self.frontmatter.get("generated")
        if isinstance(gen, dict) and gen.get("at"):
            return str(gen["at"])
        ts = self.frontmatter.get("timestamp")
        return str(ts) if ts else None

    @property
    def trust_tier(self) -> str:
        return trust_tier(self.frontmatter)

    def is_stale(self, now: Optional[datetime] = None) -> bool:
        return is_stale(self.frontmatter, now)

    @property
    def is_human_authored(self) -> bool:
        by = self.generated_by
        return bool(by and by.startswith("human:"))

    def content_hash(self) -> str:
        """SHA-256 of the serialized form: the optimistic-concurrency token for edits."""
        return hashlib.sha256(self.serialize().encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------- module helpers


def normalize_verified(frontmatter: Dict[str, Any]) -> List[Dict[str, Any]]:
    """`verified` as a list; a bare mapping is a one-element list (§5.2, MUST)."""
    v = frontmatter.get("verified")
    if isinstance(v, dict):
        return [v]
    if isinstance(v, list):
        return [e for e in v if isinstance(e, dict)]
    return []


def trust_tier(frontmatter: Dict[str, Any]) -> str:
    """unverified / machine-confirmed / human-reviewed, from `verified` only (§5.3)."""
    events = normalize_verified(frontmatter)
    if not events:
        return TRUST_UNVERIFIED
    if any(str(e.get("by") or "").startswith("human:") for e in events):
        return TRUST_HUMAN
    return TRUST_MACHINE


def _parse_instant(raw: str) -> Optional[datetime]:
    if "T" not in raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo is not None else None


def is_stale(frontmatter: Dict[str, Any], now: Optional[datetime] = None) -> bool:
    """now >= stale_after (§5.5). A date without time/offset is ignored, not guessed."""
    raw = frontmatter.get("stale_after")
    if raw is None:
        return False
    instant = _parse_instant(str(raw))
    if instant is None:
        return False
    return (now or datetime.now(timezone.utc)) >= instant


_ACTOR_RX = re.compile(r"^(human:[^\s]+|process:[^\s]+|[A-Za-z0-9_.\-]+/[^\s]+)$")


def is_valid_actor(actor: str) -> bool:
    """`<producer>/<version>`, `human:<id>` or `process:<id>` (§7)."""
    return bool(_ACTOR_RX.match(actor or ""))
