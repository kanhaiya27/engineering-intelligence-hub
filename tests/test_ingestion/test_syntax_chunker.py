"""Tree-sitter (WASM) chunking for Java/Go/Rust/JS/TS/TSX/C/C++ (WORK_PLAN step 16).

Needs Node and `npm ci` in tools/treesitter; skipped with a visible reason otherwise.
"""

from __future__ import annotations

import pytest

from ingestion.processors.chunker import CodeAwareChunker, estimate_tokens
from ingestion.processors.syntax_chunker import CHUNKER_ID, TreeSitterService, language_id
from knowledge.schemas.artifacts import ArtifactType, ProgrammingLanguage, SourceFile

L = ProgrammingLanguage


@pytest.fixture(scope="module")
def ts():
    try:
        svc = TreeSitterService()
        svc.parse("java", "class A {}")
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"tree-sitter service unavailable: {exc}")
    yield svc
    svc.close()


def src(path: str, lang: ProgrammingLanguage, content: str) -> SourceFile:
    return SourceFile(artifact_id=f"r:{path}:h", artifact_type=ArtifactType.SOURCE_CODE, repository="o/r",
                      source_path=path, language=lang, raw_content=content)


CASES = [
    ("A.java", L.JAVA, "package a;\nimport b.C;\n\n/** Doc. */\npublic class A {\n  void f() {}\n}\n\ninterface I { void g(); }\n",
     ["<module_preamble>", "A", "I"]),
    ("m.go", L.GO, "package m\n\nimport \"fmt\"\n\n// F prints.\nfunc F() { fmt.Println() }\n\ntype T struct{}\n\nfunc (t T) M() {}\n",
     ["<module_preamble>", "F", "T", "M"]),
    ("lib.rs", L.RUST, "use std::fmt;\n\n/// A thing.\n#[derive(Debug)]\nstruct S;\n\nimpl fmt::Display for S {\n    fn fmt(&self) {}\n}\n\nfn main() {}\n",
     ["<module_preamble>", "S", "fmt::Display for S", "main"]),
    ("a.js", L.JAVASCRIPT, "const x = require('x');\n\nfunction f() { return 1; }\n\nclass C {\n  m() {}\n}\n\nmodule.exports = { f, C };\n",
     ["x", "f", "C", "<module_trailer>"]),
    ("a.ts", L.TYPESCRIPT, "interface I { a: number }\n\nexport type T = string;\n\nexport function f(): void {}\n",
     ["I", "T", "f"]),
    ("A.tsx", L.TYPESCRIPT, "export function App() {\n  return <div>hi</div>;\n}\n", ["App"]),
    ("x.c", L.C, "#include <stdio.h>\n\n/* add */\nstatic int add(int a, int b) { return a + b; }\n\nstruct P { int x; };\n",
     ["<module_preamble>", "add", "P"]),
    ("x.cpp", L.CPP, "#include <vector>\n\nnamespace n {\nclass C { public: void m() {} };\n}\n\ntemplate <typename T> T id(T a) { return a; }\n",
     ["<module_preamble>", "n", "id"]),
]


@pytest.mark.parametrize("path,lang,content,symbols", CASES, ids=[c[0] for c in CASES])
def test_symbol_units_cover_every_line(ts, path, lang, content, symbols):
    chunks = CodeAwareChunker(syntax=ts).chunk(src(path, lang, content))
    assert [c.metadata["symbol_name"] for c in chunks] == symbols
    assert all(c.metadata["chunker"] == CHUNKER_ID for c in chunks)
    covered = {i for c in chunks for i in range(c.start_line, c.end_line + 1)}
    assert all(i in covered for i, l in enumerate(content.splitlines(), 1) if l.strip())


def test_leading_comments_and_attributes_stay_with_their_definition(ts):
    content = "use x;\n\n/// Doc line.\n#[inline]\nfn f() {}\n"
    chunks = CodeAwareChunker(syntax=ts).chunk(src("a.rs", L.RUST, content))
    f = next(c for c in chunks if c.metadata["symbol_name"] == "f")
    assert f.content.startswith("/// Doc line.") and f.start_line == 3


def test_oversized_class_is_split_into_members_within_the_window(ts):
    body = "\n".join(f"  int m{i}(int a) {{\n" + "    a = a + 1; // padding words here\n" * 12 + "    return a;\n  }" for i in range(12))
    content = f"public class Big {{\n  private int x;\n{body}\n}}\n"
    chunks = CodeAwareChunker(syntax=ts).chunk(src("Big.java", L.JAVA, content))
    names = [c.metadata["symbol_name"] for c in chunks]
    assert "Big.<header>" in names and "Big.m0" in names and "Big.m11" in names
    assert max(estimate_tokens(c.content) for c in chunks) <= 512


def test_local_parse_errors_keep_units_and_are_flagged(ts):
    content = "int ok(void) { return 1; }\n\nint bad(void) { return MACRO(,; }\n\nint ok2(void) { return 2; }\n"
    chunks = CodeAwareChunker(syntax=ts).chunk(src("m.c", L.C, content))
    assert "ok" in [c.metadata["symbol_name"] for c in chunks] and "ok2" in [c.metadata["symbol_name"] for c in chunks]
    assert all(c.metadata.get("parse_errors") for c in chunks)
    covered = {i for c in chunks for i in range(c.start_line, c.end_line + 1)}
    assert all(i in covered for i, l in enumerate(content.splitlines(), 1) if l.strip())


def test_file_without_definitions_falls_back_to_the_window_visibly(ts):
    chunks = CodeAwareChunker(syntax=ts).chunk(src("cfg.js", L.JAVASCRIPT, "app.set('x', 1);\napp.listen(3000);\n"))
    assert chunks and all(c.metadata.get("chunker") != CHUNKER_ID for c in chunks)
    assert chunks[0].metadata.get("syntax_fallback") == "no_definitions"


def test_commonjs_assigned_functions_and_ifdef_wrapped_c(ts):
    js = "var a = require('a');\n\nres.send = function send(body) {\n  return body;\n};\n\nvar g = function () {};\n"
    names = [c.metadata["symbol_name"] for c in CodeAwareChunker(syntax=ts).chunk(src("r.js", L.JAVASCRIPT, js))]
    assert "res.send" in names and "g" in names
    h = "#ifndef X_H\n#define X_H\n\nint f(void);\n\nstatic int g(void) { return 0; }\n\n#endif\n"
    names = [c.metadata["symbol_name"] for c in CodeAwareChunker(syntax=ts).chunk(src("x.h", L.C, h))]
    assert "g" in names


def test_default_chunker_is_unchanged_without_a_syntax_service():
    """Wave 1 (ASK_ME T16 option (a)): no syntax service -> the pre-step-16 line window."""
    content = "function f() { return 1; }\n\nclass C { m() {} }\n"
    chunks = CodeAwareChunker().chunk(src("a.js", L.JAVASCRIPT, content))
    assert [c.metadata["chunk_type"] for c in chunks] == ["code_block"] and "chunker" not in chunks[0].metadata


def test_python_is_never_routed_to_tree_sitter(ts):
    chunks = CodeAwareChunker(syntax=ts).chunk(src("a.py", L.PYTHON, "def f():\n    return 1\n"))
    assert chunks[0].metadata["language"] == "python" and "chunker" not in chunks[0].metadata


def test_language_ids():
    assert language_id(L.TYPESCRIPT, "a/App.tsx") == "tsx" and language_id(L.C, "x.h") == "c"
    assert language_id(L.PYTHON, "a.py") is None and language_id(L.RUBY, "a.rb") is None
