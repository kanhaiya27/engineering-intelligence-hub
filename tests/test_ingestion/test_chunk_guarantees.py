"""
Chunker guarantees (2026-10-05 fix): every chunk fits the embedding model's window
(counted with its own tokenizer), every non-blank line is covered, and every chunk's
start/end lines are exact.
"""

from __future__ import annotations

import pytest

from ingestion.processors.chunker import CodeAwareChunker, DocAwareChunker, estimate_tokens
from knowledge.schemas.artifacts import ArtifactType, BaseArtifact, ProgrammingLanguage, SourceFile

LIMIT = 512


def py(content: str, path: str = "src/mod.py") -> SourceFile:
    return SourceFile(artifact_id=f"r:{path}:h", artifact_type=ArtifactType.SOURCE_CODE, repository="o/r",
                      source_path=path, language=ProgrammingLanguage.PYTHON, raw_content=content)


def doc(content: str, path: str = "docs/x.rst", kind=ArtifactType.MARKDOWN) -> BaseArtifact:
    return BaseArtifact(artifact_id=f"r:{path}:h", artifact_type=kind, repository="o/r",
                        source_path=path, raw_content=content)


def assert_guarantees(chunks, content: str, limit: int = LIMIT):
    lines = content.splitlines()
    covered = set()
    for c in chunks:
        assert estimate_tokens(c.content) <= limit, (c.metadata, estimate_tokens(c.content))
        assert 1 <= c.start_line <= c.end_line <= len(lines)
        span = "\n".join(lines[c.start_line - 1: c.end_line])
        # the chunk text is exactly its lines (or, for a split single line, a piece of it)
        if c.start_line != c.end_line or c.content == span.strip():
            assert c.content == span.strip(), (c.start_line, c.end_line)
        else:
            assert c.content in lines[c.start_line - 1]
        covered.update(range(c.start_line, c.end_line + 1))
    missing = [i for i, l in enumerate(lines, 1) if l.strip() and i not in covered]
    assert not missing, f"non-blank lines not in any chunk: {missing[:10]}"


def long_function(name: str, n_lines: int) -> str:
    body = "\n".join(f"    value_{i} = compute_something(argument_{i}, option_{i})" for i in range(n_lines))
    return f"def {name}():\n{body}\n    return value_0\n"


def test_long_function_is_split_into_parts_that_fit():
    content = '"""Module."""\nimport os\n\n' + long_function("huge", 200)
    chunks = CodeAwareChunker(min_tokens_per_chunk=1).chunk(py(content))
    parts = [c for c in chunks if c.metadata["symbol_name"] == "huge"]
    assert len(parts) > 1 and {c.metadata["parts"] for c in parts} == {len(parts)}
    assert [c.metadata["part"] for c in parts] == list(range(1, len(parts) + 1))
    assert_guarantees(chunks, content)


def test_code_between_definitions_and_decorators_are_not_dropped():
    content = (
        "import flask\n\n"
        "def first():\n    return 1\n\n"
        "app = flask.Flask(__name__)\napp.config['DEBUG'] = True\n\n"
        "@app.route('/')\n@login_required\ndef index():\n    return 'ok'\n\n"
        "if __name__ == '__main__':\n    app.run()\n"
    )
    chunks = CodeAwareChunker(min_tokens_per_chunk=1).chunk(py(content))
    by_symbol = {c.metadata["symbol_name"]: c for c in chunks}
    assert "app.config['DEBUG'] = True" in by_symbol["<module_code>"].content
    assert by_symbol["index"].start_line == 9 and by_symbol["index"].content.startswith("@app.route")
    assert "app.run()" in by_symbol["<module_trailer>"].content
    assert_guarantees(chunks, content)


def test_oversized_class_keeps_body_between_methods():
    methods = "\n".join(
        f"    def method_{k}(self):\n" + "\n".join(f"        x_{i} = self.call_{i}(argument_{i})" for i in range(12))
        + f"\n\n    CONSTANT_{k} = {k}\n" for k in range(12)
    )
    content = "class Big:\n    '''Doc.'''\n    attr = 1\n\n" + methods
    chunks = CodeAwareChunker(min_tokens_per_chunk=1).chunk(py(content))
    symbols = [c.metadata["symbol_name"] for c in chunks]
    assert "Big.<header>" in symbols and "Big.method_0" in symbols and "Big.<body>" in symbols
    assert_guarantees(chunks, content)


def test_giant_paragraph_and_giant_line_are_split():
    table = "\n".join(f"| plugin-{i} | Some description of plugin number {i} for pytest | 1.{i} |" for i in range(400))
    one_line = " ".join(f"token{i}" for i in range(3000))
    content = "Plugins\n=======\n\n" + table + "\n\nOther\n=====\n\n" + one_line + "\n"
    chunks = DocAwareChunker().chunk(doc(content))
    assert len(chunks) > 5
    assert {c.metadata["section_title"] for c in chunks} == {"Plugins", "Other"}
    assert_guarantees(chunks, content)


def test_sub_chunks_of_a_long_section_have_their_own_line_ranges():
    paras = "\n\n".join(" ".join(f"word{p}_{i}" for i in range(120)) for p in range(12))
    content = "# Title\n\n" + paras + "\n"
    chunks = DocAwareChunker().chunk(doc(content, "docs/x.md"))
    assert len(chunks) > 1
    ends = [c.end_line for c in chunks]
    assert len(set(ends)) == len(ends), "each block must end at its own last line, not the section end"
    assert_guarantees(chunks, content)


def test_non_python_code_window_is_token_bounded():
    minified = "var a=" + "+".join(f"f{i}(x{i})" for i in range(4000)) + ";"
    content = "function ok() {\n  return 1;\n}\n" + minified + "\n"
    chunks = CodeAwareChunker().chunk(SourceFile(
        artifact_id="r:a.js:h", artifact_type=ArtifactType.SOURCE_CODE, repository="o/r",
        source_path="static/a.js", language=ProgrammingLanguage.JAVASCRIPT, raw_content=content))
    assert len(chunks) > 3
    assert_guarantees(chunks, content)


@pytest.mark.parametrize("content", ["", "\n\n\n"])
def test_empty_files_give_no_chunks(content):
    assert CodeAwareChunker().chunk(py(content)) == []
    assert DocAwareChunker().chunk(doc(content)) == []
