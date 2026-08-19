# Environment & Hardware Specification

This document details the verified runtime, hardware, container, and Python environment for the **Engineering Intelligence Hub** research platform.

---

## 1. System & Hardware Specifications

| Component | Specification | Details / Verification |
|---|---|---|
| **Operating System** | Windows 11 Home / Pro (64-bit) | Build 22631+ |
| **CPU** | Intel Core i7-12650H | 10 Cores (6P + 4E), 16 Threads, Base 2.3 GHz / Boost up to 4.7 GHz |
| **System Memory (RAM)** | 16.0 GB DDR5 | ~15.8 GB usable |
| **GPU** | NVIDIA GeForce RTX 4050 Laptop GPU | 6 GB GDDR6 VRAM (~6141 MiB total) |
| **Driver Version** | 610.74 | CUDA 12.1+ compatible |
| **CUDA Driver / Runtime** | CUDA 12.1 | Verified via NVIDIA Driver & CUDA toolkit |

---

## 2. Python & Virtual Environment

| Item | Details |
|---|---|
| **Python Version** | Python 3.11.9 (tags/v3.11.9, MSC v.1938 64 bit) |
| **Location** | `C:\Users\avane\AppData\Local\Programs\Python\Python311\python.exe` |
| **Active Virtual Environment** | `.venv311/` (`C:\Projects\Majors\engineering-intelligence-hub\.venv311`) |
| **Legacy Virtual Environment** | `.venv/` (Python 3.8.10 - preserved as backup during readiness phase) |
| **Package Manager** | `pip` (v26.2+) |

### Key Verified Packages (Phase-0 Foundation)

- **API & Schemas**: `fastapi==0.141.1`, `uvicorn==0.52.4`, `pydantic==2.13.4`, `pydantic-settings==2.15.0`
- **Testing & Quality**: `pytest==9.1.1`, `pytest-asyncio==1.4.0`, `pytest-cov==7.1.0`, `black==26.5.1`, `mypy==2.3.1`, `isort==8.0.1`
- **Logging & Utilities**: `loguru==0.7.3`, `tiktoken==0.14.0`, `psutil==7.2.2`, `rich==15.0.0`, `typer==0.27.1`
- **Data & Numerical**: `numpy==2.4.6`, `pandas==3.0.5`
- **HTTP Client**: `httpx==0.28.1`

---

## 3. Container & Infrastructure Services

| Service | Version | Status | Notes |
|---|---|---|---|
| **Docker Desktop / Engine** | 28.5.2 | **Running (Active)** | Runtimes: `io.containerd.runc.v2`, `nvidia`, `runc`. Daemon verified operational. |
| **Qdrant Vector Store** | v1.9.2 (Image configured in `docker-compose.yml`) | Configured (Not started in Phase-0) | Bound to port 6333/6334 |
| **Neo4j Graph Store** | 5.18-community (Image configured in `docker-compose.yml`) | Configured (Not started in Phase-0) | Bound to port 7474/7687 |

---

## 4. Git & Version Control

- **Git Version**: 2.53.0.windows.1
- **Current Branch**: `master`
- **Remote**: `origin` (`https://github.com/kanhaiya27/engineering-intelligence-hub.git`)
- **Status**: Clean working tree
- **Phase-0 Base Commit**: `73a992c` (*feat: Phase-0 foundation — schemas, interfaces, sustainability, experiment framework, tests*)

---

## 5. Security & Ignore Rules (.gitignore)

The repository `.gitignore` strictly protects against accidental leakage of:
- All `.env` files and secret files (`*.secret`, `secrets/`, `api_keys.*`, `credentials.*`)
- All local virtual environments (`.venv/`, `.venv311/`, `.venv38/`, `venv/`, `env/`)
- Model weights, checkpoints, embeddings (`*.bin`, `*.safetensors`, `*.pt`, `*.pth`, `*.ckpt`, `*.pkl`, `*.h5`, `*.npy`, `*.npz`)
- Hugging Face and local model cache directories (`.cache/`, `model_cache/`, `hf_cache/`, `sentence_transformers/`)
- Raw experiment runs and dataset files (`experiments/results/**/*.jsonl`, `datasets/**/*.parquet`, etc.)
- Database stores (`.chromadb/`, `qdrant_storage/`, `data/databases/`, `*.duckdb`, `*.sqlite3`)
