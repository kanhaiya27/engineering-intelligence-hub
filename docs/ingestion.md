# Ingestion Architecture & Reference Guide

## Overview

The Engineering Intelligence Hub ingestion subsystem extracts software engineering artifacts from repositories while preserving strict provenance, line ranges, commit hashes, and structural context.

---

## 1. Supported Ingestion Sources

### `FileIngestionSource`
- **Location**: `ingestion/loaders/file_loader.py`
- **Capabilities**:
  - Traverses directory trees while respecting standard ignore lists (`.git`, `__pycache__`, `venv`, `dist`, `build`, etc.).
  - Classifies artifacts into `SOURCE_CODE`, `DOCUMENTATION`, `CONFIGURATION`, or `TEST`.
  - Computes SHA-256 hash for artifact deduplication.
  - Automatically preserves relative file paths and line counts.

### `GitHubRepositoryIngestionSource`
- **Location**: `ingestion/loaders/github_loader.py`
- **Capabilities**:
  - Clones or updates target repositories from GitHub.
  - Pins checkouts to immutable tags or commit SHAs (e.g. `pallets/flask` @ `3.0.3` / `4aa68d5`).
  - Ingests file tree, Git commit history, issues, and pull requests into standard schema objects (`SourceFile`, `Commit`, `Issue`, `PullRequest`).

---

## 2. Processors & Chunking

### `ArtifactNormalizer`
- **Location**: `ingestion/processors/normalizer.py`
- **Operations**:
  1. Strips UTF Byte Order Marks (`\ufeff`).
  2. Normalizes mixed Windows (`\r\n`) and UNIX (`\n`) line endings.
  3. Filters control characters while preserving formatting and tabs.
  4. Routes artifacts to specialized chunkers based on type.

### `CodeAwareChunker`
- **Location**: `ingestion/processors/chunker.py`
- **Methodology**:
  - Uses Python `ast.parse` to extract top-level and class-level definitions:
    - `ast.FunctionDef`, `ast.AsyncFunctionDef`
    - `ast.ClassDef`
  - Captures exact 1-indexed `start_line` and `end_line`.
  - Attaches `symbol_name`, `symbol_type`, `file_path`, and `docstring` to `KnowledgeChunk.metadata`.
  - For oversized AST nodes exceeding `max_chunk_size`, falls back to line-based sliding windows with overlap.

### `DocAwareChunker`
- **Methodology**:
  - Splits markdown and restructured text across header markers (`# `, `## `, `### `, `====`, `----`).
  - Attaches `section_title` and line boundaries to each chunk.

---

## 3. Dataset Registry

Pinned repository versions are defined in `datasets/registry.yaml`:

```yaml
version: "1.0"
repositories:
  - id: pallets/flask
    name: flask
    clone_url: https://github.com/pallets/flask.git
    pinned_tag: 3.0.3
    pinned_commit: 4aa68d5a153fd780b43f769fa5afcaadcf973cb3
  - id: fastapi/fastapi
    name: fastapi
    clone_url: https://github.com/fastapi/fastapi.git
    pinned_tag: 0.111.0
    pinned_commit: 43594b291d9ccf5309320e8b15d0eaef32f30737
```
