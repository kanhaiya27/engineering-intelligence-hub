# Retrieval Architecture & Strategy Guide

## Overview

The retrieval engine provides dense semantic vector search, code-aware BM25 keyword search, and weighted hybrid retrieval across software engineering knowledge chunks.

---

## 1. Dense Retriever (`retrieval/dense.py`)

- **Model**: `BAAI/bge-small-en-v1.5` (384 dimensions, cosine distance).
- **Backend**: Qdrant Vector Store (Docker container `qdrant/qdrant:v1.13.2` or in-memory).
- **Capabilities**:
  - Semantic query embedding with BGE query instruction prefix.
  - Cosine similarity matching in vector space.
  - Metadata payload filtering (by `repository`, `artifact_type`).
  - Score threshold enforcement (`score_threshold >= 0.0`).

---

## 2. BM25 Sparse Retriever (`retrieval/bm25.py`)

- **Algorithm**: `BM25Plus` from `rank_bm25` (ensuring positive IDF values and robust scoring even on small corpora).
- **Tokenization**:
  - `code_aware_tokenize` splits CamelCase, snake_case, dot notation (`app.route`), and file paths (`src/flask/app.py`).
  - Indexes combined content, symbol names, file paths, and repository identifiers.

---

## 3. Hybrid Retriever (`retrieval/hybrid.py`)

- **Fusion Formula**:
  $$\text{FusedScore}(d) = w_{\text{dense}} \times \text{DenseScore}_{\text{norm}}(d) + w_{\text{sparse}} \times \text{SparseScore}_{\text{norm}}(d)$$
  Default weights: $w_{\text{dense}} = 0.7$, $w_{\text{sparse}} = 0.3$.
- **Normalization**: Max-score normalization per channel to ensure balanced contribution.
- **Deduplication**: Merges chunk hits across dense and sparse channels by `chunk_id`.

---

## 4. Configuration Schema (`retrieval/strategies.py`)

```python
strategy = RetrievalStrategyConfig(
    strategy_name="hybrid_top5",
    mode=RetrievalMode.HYBRID,
    top_k=5,
    dense_weight=0.7,
    sparse_weight=0.3,
    score_threshold=0.0,
    repository_filter="pallets/flask",
    max_context_chunks=5,
)
```
