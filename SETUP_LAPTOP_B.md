# Setup — Laptop B (RTX 5050, Windows 11)

Step-by-step setup for cloning EIH onto the second development laptop. Run
commands in **PowerShell** unless noted. Allow ~1–2 hours (downloads dominate).

> The RTX 5050 is a **Blackwell** GPU (compute capability `sm_120`). Older PyTorch
> builds (cu121 / cu124, as on Laptop A) **do not contain kernels for it** and fail
> with `no kernel image is available for execution on the device`. You need a
> **CUDA 12.8 (cu128)** build of PyTorch ≥ 2.7, installed *before* the rest of the
> requirements (step 4).

---

## 0. Prerequisites (install once)

| Tool | Install | Check |
|---|---|---|
| Git for Windows | https://git-scm.com/download/win (includes Git Credential Manager) | `git --version` |
| Python **3.11** (64-bit) | https://www.python.org/downloads/release/python-3119/ — tick "Add to PATH" | `py -3.11 --version` |
| NVIDIA driver **≥ 570** (Blackwell + CUDA 12.8) | GeForce Experience / nvidia.com/drivers | `nvidia-smi` (top right shows "CUDA Version: 12.8" or higher) |
| Docker Desktop (WSL 2 backend) | https://www.docker.com/products/docker-desktop/ | `docker --version`, `docker compose version` |
| Ollama | https://ollama.com/download/windows | `ollama --version` |
| VS Code (optional) | https://code.visualstudio.com/ | Accounts icon (bottom-left) → signed in to GitHub |

You also need **collaborator access** to the private repo
`kanhaiya27/engineering-intelligence-hub` — Avaneesh invites you via GitHub →
Settings → Collaborators. Accept the email invite first.

## 1. Git identity (once per laptop)

```powershell
git config --global user.name  "Your Name"
git config --global user.email "<id>+<username>@users.noreply.github.com"   # GitHub → Settings → Emails
git config --global core.autocrlf false    # the repo's .gitattributes enforces LF
```

## 2. Clone the working branch

```powershell
mkdir C:\Projects -Force; cd C:\Projects
git clone -b phase-2-intelligence https://github.com/kanhaiya27/engineering-intelligence-hub.git
cd engineering-intelligence-hub
git log --oneline -5
```

The first `git clone` opens a browser window for GitHub sign-in (Git Credential
Manager). If it says "Repository not found", the collaborator invite hasn't been
accepted yet.

## 3. Virtual environment

```powershell
py -3.11 -m venv .venv311
.\.venv311\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

If activation is blocked: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

## 4. PyTorch for Blackwell (CUDA 12.8) — do this BEFORE requirements.txt

```powershell
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
```

Verify — all four lines must look right:

```powershell
python -c "import torch; print(torch.__version__); print(torch.version.cuda); print(torch.cuda.is_available(), torch.cuda.get_device_name(0)); print(torch.cuda.get_arch_list())"
```

Expected: version `2.7`+ ending in `+cu128`, CUDA `12.8`, `True NVIDIA GeForce RTX 5050 ...`,
and **`sm_120` present in the arch list**. Then a real kernel test:

```powershell
python -c "import torch; x=torch.randn(1024,1024,device='cuda'); print((x@x).sum().item())"
```

If you see `no kernel image is available` or `sm_120 is not compatible`, the
wrong build is installed: `pip uninstall -y torch torchvision` and repeat step 4.

## 5. Project dependencies

```powershell
pip install -r requirements-dev.txt
python -c "import torch; print(torch.__version__)"   # must STILL end in +cu128
```

If pip replaced torch with a CPU build, repeat step 4 with `--force-reinstall`.

## 6. Local configuration (`.env` — never committed)

```powershell
Copy-Item .env.example .env
nvidia-smi -q -d POWER     # note "Max Power Limit" / "Current Power Limit"
```

Edit `.env`:
- `EIH_SUSTAINABILITY_GPU_TDP_WATTS=` → your GPU power limit from `nvidia-smi`
- `EIH_SUSTAINABILITY_CPU_TDP_WATTS=` → your CPU's base power (look up the model; `Get-CimInstance Win32_Processor | Select Name`)
- Leave `EIH_SUSTAINABILITY_CARBON_REGION=custom` and `...INTENSITY...=713.0` (India grid) unless you run elsewhere.
- `EIH_GRAPH_PASSWORD=` → choose one; it must match what Neo4j was created with (step 7).

Record your hardware in `PROGRESS-B.md`.

## 7. Docker services (Qdrant + Neo4j)

Start Docker Desktop, then:

```powershell
docker compose up -d
docker compose ps                                   # both "healthy" after ~1 min
curl.exe -s http://localhost:6333/healthz           # "healthz check passed"
```

> In Windows PowerShell 5.1, `curl` is an alias for `Invoke-WebRequest` — always
> type **`curl.exe`** for the commands below.

## 8. Restore the shared data (from Laptop A)

Data is **not** in git. Avaneesh copies the folder `C:\EIH_share\` to your laptop
(USB drive / Google Drive / OneDrive) — put it at `C:\EIH_share\` too.
Check `C:\EIH_share\README.txt` for the exact file names and checksums.

### 8a. Qdrant collection `eih_knowledge` (48,046 chunks)

```powershell
# Verify the file arrived intact (compare with the SHA256 in README.txt)
Get-FileHash C:\EIH_share\eih_knowledge.snapshot -Algorithm SHA256

# Upload + restore (creates the collection; takes a few minutes)
curl.exe -X POST "http://localhost:6333/collections/eih_knowledge/snapshots/upload?priority=snapshot" `
  -H "Content-Type: multipart/form-data" `
  -F "snapshot=@C:/EIH_share/eih_knowledge.snapshot"

# Verify: points_count must be 48046
curl.exe -s http://localhost:6333/collections/eih_knowledge
```

**Alternative (no snapshot):** rebuild from source on your own GPU — slower
(~6 min embedding + clone time) but fully independent:

```powershell
python -m scripts.ingest_corpus --wave 1
```

Note: re-ingesting may resolve slightly different chunk counts if a repository
tag moved; the snapshot guarantees an identical corpus to Laptop A.

### 8b. Neo4j graph (only if `C:\EIH_share\neo4j.dump` exists)

The dump can only be loaded into a **stopped** database:

```powershell
docker compose stop neo4j
docker run --rm `
  -v engineering-intelligence-hub_neo4j_data:/data `
  -v C:/EIH_share:/dumps `
  neo4j:5.18-community `
  neo4j-admin database load neo4j --from-path=/dumps --overwrite-destination=true
docker compose start neo4j
```

The volume name is `<folder-name>_neo4j_data`; check with `docker volume ls` if you
cloned into a differently named folder. Verify at http://localhost:7474
(`MATCH (n) RETURN count(n)`). If no dump was shared, the graph is empty on both
laptops and is built by the graph builder when needed.

## 9. Ollama (local LLMs)

```powershell
ollama pull qwen2.5-coder:1.5b
ollama pull qwen2.5-coder:3b
ollama pull qwen2.5-coder:7b          # Q4 by default, ~4.7 GB
ollama run qwen2.5-coder:1.5b "Say hello in one word"
```

Ollama serves on `http://localhost:11434` (`EIH_LOCAL_MODEL_BASE_URL`). Note: the
Ollama provider is not wired into the pipeline yet — this just prepares models.

## 10. Run the tests

```powershell
.\.venv311\Scripts\Activate.ps1
python -m pytest
```

Expected on a correct setup with Docker running: **178 passed** (or 176 passed,
2 skipped if Qdrant isn't up). Quick GPU embedding check:

```powershell
python -c "from knowledge.vector.embeddings import BGEEmbeddingModel as M; m=M(); print(m.active_device, len(m.embed_text('hello')))"
# expected: cuda 384
```

## 11. Start working

Read `CLAUDE.md` and `docs/WORKFLOW.md`, then:

```powershell
git checkout phase-2-intelligence; git pull
git checkout -b feat/<area>-<short-description>
```

Log each session in `PROGRESS-B.md`; always set `machine_id: laptop-b` on results.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `no kernel image is available for execution on the device` | Wrong PyTorch build — repeat step 4 (cu128). |
| `torch.cuda.is_available()` is False | Driver too old (< 570) or CPU torch installed; check `nvidia-smi` and step 5. |
| Qdrant tests skipped | Docker Desktop not running / `docker compose up -d` not done. |
| `Repository not found` on clone | Collaborator invite not accepted, or signed in to the wrong GitHub account (Windows Credential Manager → remove `git:https://github.com`). |
| Neo4j auth failure | `EIH_GRAPH_PASSWORD` in `.env` differs from the one the volume was created with. |
