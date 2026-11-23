"""
Tree-sitter symbol boundaries for Java, Go, Rust, JavaScript, TypeScript/TSX, C and C++
(WORK_PLAN step 16, plan §10.6).

Parsing runs in `tools/treesitter/parse.mjs`, the official web-tree-sitter (WebAssembly)
build with the official grammar .wasm files, inside Node. The native Python binding is
blocked by Windows Smart App Control on this laptop (decided 2026-11-23: use WASM, keep
Smart App Control on). One Node process serves a whole ingestion run over JSON lines.

Units mirror the Python AST chunker: top-level definitions become units (leading comments and
attributes attached); the code between them becomes module_header / module_code /
module_trailer units; an oversized container (class, interface, impl, trait, namespace, ...)
is split into header, members and body. Units go through the same token-bounded splitter,
so every chunk still fits the embedding window.

This is OPT-IN (`CodeAwareChunker(syntax=...)`). Wave 1 does not use it (ASK_ME T16 (a)),
which `scripts/chunking_fingerprint.py` verifies byte for byte.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from knowledge.schemas.artifacts import ProgrammingLanguage

Unit = Tuple[int, int, Dict[str, Any]]
CHUNKER_ID = "tree_sitter_wasm"
SERVICE_DIR = Path(__file__).resolve().parents[2] / "tools" / "treesitter"

LANGUAGE_IDS = {
    ProgrammingLanguage.JAVA: "java", ProgrammingLanguage.GO: "go", ProgrammingLanguage.RUST: "rust",
    ProgrammingLanguage.JAVASCRIPT: "javascript", ProgrammingLanguage.TYPESCRIPT: "typescript",
    ProgrammingLanguage.C: "c", ProgrammingLanguage.CPP: "cpp",
}
_EXT_OVERRIDE = {".tsx": "tsx", ".jsx": "javascript", ".h": "c"}

DEFINITIONS = {
    "java": {"class_declaration", "interface_declaration", "enum_declaration", "record_declaration",
             "annotation_type_declaration", "method_declaration"},
    "go": {"function_declaration", "method_declaration", "type_declaration"},
    "rust": {"function_item", "struct_item", "enum_item", "union_item", "impl_item", "trait_item", "mod_item",
             "macro_definition"},
    "javascript": {"function_declaration", "generator_function_declaration", "class_declaration",
                   "lexical_declaration", "export_statement", "assigned_function"},
    "c": {"function_definition", "struct_specifier", "enum_specifier", "union_specifier", "type_definition"},
    "cpp": {"function_definition", "struct_specifier", "enum_specifier", "union_specifier", "class_specifier",
            "namespace_definition", "template_declaration", "type_definition"},
}
DEFINITIONS["typescript"] = DEFINITIONS["javascript"] | {"interface_declaration", "type_alias_declaration",
                                                        "enum_declaration", "abstract_class_declaration",
                                                        "module", "internal_module"}
DEFINITIONS["tsx"] = DEFINITIONS["typescript"]
LEADING = {"comment", "line_comment", "block_comment", "attribute_item", "decorator"}
MEMBERS = {"method_declaration", "constructor_declaration", "method_definition", "function_item",
           "function_definition", "function_declaration", "function_signature_item", "class_declaration",
           "class_specifier", "interface_declaration", "enum_declaration", "struct_item", "impl_item"}
CONTAINER_TYPES = {"class_declaration", "interface_declaration", "enum_declaration", "record_declaration",
                   "impl_item", "trait_item", "mod_item", "class_specifier", "struct_specifier", "namespace_definition",
                   "abstract_class_declaration", "export_statement", "template_declaration", "module",
                   "internal_module"}


def language_id(language: Optional[ProgrammingLanguage], source_path: Optional[str]) -> Optional[str]:
    ext = Path(source_path or "").suffix.lower()
    if ext in _EXT_OVERRIDE and (language in LANGUAGE_IDS or ext == ".tsx"):
        return _EXT_OVERRIDE[ext]
    return LANGUAGE_IDS.get(language) if language is not None else None


def _node_executable() -> str:
    for cand in (os.environ.get("EIH_NODE"), shutil.which("node"),
                 str(Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "nodejs" / "node.exe")):
        if cand and Path(cand).exists():
            return cand
    raise RuntimeError("Node.js not found (set EIH_NODE): tree-sitter chunking needs it")


class TreeSitterService:
    """One long-running Node parser process; thread-safe; fails loudly, never silently."""

    def __init__(self, service_dir: Path = SERVICE_DIR):
        self.service_dir = service_dir
        if not (service_dir / "node_modules" / "web-tree-sitter").exists():
            raise RuntimeError(f"tree-sitter service not installed: run `npm ci` in {service_dir}")
        self._proc: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()
        self._next = 0

    def _start(self) -> subprocess.Popen:
        if self._proc is None or self._proc.poll() is not None:
            self._proc = subprocess.Popen([_node_executable(), str(self.service_dir / "parse.mjs")],
                                          cwd=self.service_dir, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                          stderr=subprocess.PIPE, text=True, encoding="utf-8", bufsize=1)
        return self._proc

    def parse(self, lang: str, source: str) -> Dict[str, Any]:
        with self._lock:
            proc = self._start()
            self._next += 1
            proc.stdin.write(json.dumps({"id": self._next, "lang": lang, "source": source}) + "\n")
            proc.stdin.flush()
            line = proc.stdout.readline()
            if not line:
                raise RuntimeError(f"tree-sitter service stopped: {proc.stderr.read()[:500]}")
            resp = json.loads(line)
            if resp.get("id") != self._next:
                raise RuntimeError("tree-sitter service out of sync")
            return resp

    def close(self) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.stdin.close()
            self._proc.wait(timeout=10)

    def __enter__(self) -> "TreeSitterService":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def syntax_units(parsed: Dict[str, Any], lang: str, n_lines: int, fits) -> Optional[List[Unit]]:
    """Units from a parse response (rows 0-based -> lines 1-based). None = use the window.

    A file with parse errors keeps the definitions tree-sitter did recognise (errors in
    macro-heavy C are usually inside function bodies); error regions fall into the code gaps,
    so coverage and the token bound still hold. Such units carry parse_errors=True."""
    if not parsed.get("ok"):
        return None
    defs = DEFINITIONS[lang]
    base = {"language": lang, "chunker": CHUNKER_ID}
    if parsed.get("has_error"):
        base["parse_errors"] = True
    nodes = parsed["nodes"]
    units: List[Unit] = []
    cursor, k, lead = 1, 0, None
    for node in nodes:
        if node["type"] in LEADING:
            lead = lead if lead is not None else node["start_row"] + 1
            continue
        is_def = node["type"] in defs and (node["type"] != "export_statement" or node.get("name"))
        if not is_def:
            lead = None
            continue
        start = min(lead, node["start_row"] + 1) if lead is not None else node["start_row"] + 1
        end = min(node["end_row"] + 1, n_lines)
        lead = None
        if start < cursor:  # overlapping/contained (should not happen for root children)
            start = cursor
        if start > end:
            continue
        if cursor < start:
            units.append((cursor, start - 1, {**base, "symbol_name": "<module_preamble>" if k == 0 else "<module_code>",
                                              "chunk_type": "module_header" if k == 0 else "module_code"}))
        name = node.get("name") or f"<{node['type']}>"
        members = [m for m in node.get("members", []) if m["type"] in MEMBERS]
        if node["type"] in CONTAINER_TYPES and members and not fits(start, end):
            units.extend(_container_units(node, members, name, start, end, base))
        else:
            units.append((start, end, {**base, "symbol_name": name, "chunk_type": node["type"]}))
        cursor, k = end + 1, k + 1
    if not k:
        return None
    if cursor <= n_lines:
        units.append((cursor, n_lines, {**base, "symbol_name": "<module_trailer>", "chunk_type": "module_trailer"}))
    return units


def _container_units(node, members, name, start, end, base) -> List[Unit]:
    units: List[Unit] = []
    first = members[0]["start_row"] + 1
    if start < first:
        units.append((start, first - 1, {**base, "symbol_name": f"{name}.<header>", "chunk_type": "class_header"}))
    cursor = first
    for m in members:
        m_start, m_end = m["start_row"] + 1, min(m["end_row"] + 1, end)
        if m_start < cursor:
            continue
        if cursor < m_start:
            units.append((cursor, m_start - 1, {**base, "symbol_name": f"{name}.<body>", "chunk_type": "class_body"}))
        units.append((m_start, m_end, {**base, "symbol_name": f"{name}.{m.get('name') or '<' + m['type'] + '>'}",
                                       "chunk_type": "method"}))
        cursor = m_end + 1
    if cursor <= end:
        units.append((cursor, end, {**base, "symbol_name": f"{name}.<body>", "chunk_type": "class_body"}))
    return units
