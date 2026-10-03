# Phase-1 Architecture: Engineering Knowledge Acquisition & Baseline RAG

## Overview

Phase-1 establishes the first operational baseline for the **Engineering Intelligence Hub (EIH)**. It ingests real open-source software repositories, extracts and normalizes engineering artifacts, generates GPU-accelerated embeddings, indexes knowledge into Qdrant and BM25, and executes grounded engineering RAG.

```
+--------------------------+
|  OPEN-SOURCE REPOSITORY  | (pallets/flask, fastapi/fastapi at fixed commits)
+--------------------------+
             |
             v
+--------------------------+
|   REPOSITORY INGESTION   | (FileIngestionSource / GitHubRepositoryIngestionSource)
+--------------------------+
             |
             v
+--------------------------+
|  ARTIFACT NORMALIZATION  | (Validation, BOM/line-ending normalization, deduplication)
+--------------------------+
             |
             v
+--------------------------+
|   CODE-AWARE CHUNKING    | (AST-based boundary parsing, doc heading splitting)
+--------------------------+
             |
             v
+--------------------------+
|      BGE EMBEDDINGS      | (BAAI/bge-small-en-v1.5 on RTX 4050 GPU / CUDA)
+--------------------------+
             |
     +-------+-------+
     |               |
     v               v
+----------+   +----------+
|  QDRANT  |   |   BM25   | (Cosine vector search + BM25Plus keyword index)
+----------+   +----------+
     |               |
     +-------+-------+
             |
             v
+--------------------------+
|     HYBRID RETRIEVAL     | (Dense + Sparse weighted score fusion & metadata filtering)
+--------------------------+
             |
             v
+--------------------------+
|       LLM PROVIDER       | (OpenAIProvider / MockLLMProvider)
+--------------------------+
             |
             v
+--------------------------+
|    GROUNDED RAG ANSWER   | ("SUPPORTED BY EVIDENCE" / "INSUFFICIENT EVIDENCE")
+--------------------------+
             |
             v
+--------------------------+
|  SUSTAINABILITY & LOGS   | (NVML/TDP energy, CO2e, monetary cost, JSONL events)
+--------------------------+
```

---

## Core Pipeline Components

### 1. Ingestion (`ingestion/loaders/`)
- **`FileIngestionSource`**: Recursively scans directories with configurable exclusions (`.git`, `node_modules`, `build`, caches, binary files). Automatically classifies source code (`.py`, `.java`, `.cpp`, `.js`, `.ts`, `.go`, `.rs`), documentation (`.md`, `.txt`, `.rst`), configuration (`.yaml`, `.json`), and test files.
- **`GitHubRepositoryIngestionSource`**: Clones and checks out repositories at pinned commit SHAs/tags, extracting Git commits history, issues, and pull requests while maintaining strict provenance.

### 2. Normalization & Chunking (`ingestion/processors/`)
- **`ArtifactNormalizer`**: Strips BOMs, normalizes line endings, cleans control characters, extracts SHA-256 content hashes, and deduplicates identical artifacts.
- **`CodeAwareChunker`**: Uses Python `ast` to parse functions, async functions, classes, methods, and module headers, preserving exact 1-indexed `start_line` and `end_line` offsets.
- **`DocAwareChunker`**: Splits documentation across Markdown/RST heading boundaries (`# `, `## `, `### `).

### 3. Embeddings (`knowledge/vector/embeddings.py`)
- **`BGEEmbeddingModel`**: Wraps `BAAI/bge-small-en-v1.5` (384 dimensions) on the NVIDIA GeForce RTX 4050 Laptop GPU using PyTorch CUDA (with automatic fallback to CPU). Supports batching and telemetry benchmarking.

### 4. Vector Store (`knowledge/vector/qdrant.py`)
- **`QdrantVectorStore`**: Extends `BaseVectorStore`. Connects to Dockerized Qdrant v1.13.2 or in-memory mode, indexing full `KnowledgeChunk` payloads and providing cosine similarity search with repository and artifact-type filters.

### 5. Retrieval (`retrieval/`)
- **`DenseRetriever`**: Semantic vector similarity search via Qdrant.
- **`BM25Retriever`**: Keyword search with code-aware tokenization (snake_case, camelCase, dot notation, slashes) and `BM25Plus` scoring.
- **`HybridRetriever`**: Fuses dense and sparse rankings with configurable weights (`dense_weight`, `sparse_weight`) and metadata filtering.

### 6. Generation & RAG (`generation/`)
- **`OpenAIProvider`**: Handles chat completions with model-agnostic interfaces, token usage tracking, and latency measurement.
- **`MockLLMProvider`**: Hermetic mock for unit testing and offline development.
- **`BaselineRAGPipeline`**: Assembles retrieved evidence chunks into structured prompts, enforces strict evidence grounding, prevents hallucinations by distinguishing `SUPPORTED BY EVIDENCE` from `INSUFFICIENT EVIDENCE`, and computes sustainability metrics.

### 7. Evaluation & Baselines (`evaluation/`, `experiments/`)
- **`BaselineARunner`**: Evaluates LLM-only performance without retrieval context.
- **`BaselineBRunner`**: Evaluates fixed RAG performance with hybrid retrieval.
- **`BaselineEvaluatorSuite`**: Computes correctness, groundedness, and relevance scores.
