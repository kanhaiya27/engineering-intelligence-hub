# Team Workflow

How two developers (Laptop A, Laptop B) share one private GitHub repository
without overwriting each other's work or mixing up results.

**Which tasks each laptop does, in what order, and the phase status:**
[docs/WORK_PLAN.md](WORK_PLAN.md). This file covers the rules.

## 1. Branches

| Branch | Purpose |
|---|---|
| `master` | Integration branch. **Only changes through reviewed Pull Requests. No direct pushes.** |
| `phase-2-intelligence` | Current phase branch, merged into `master` via PR. |
| `feat/<area>-<short-desc>` | All new work. One topic per branch. |
| `fix/<area>-<short-desc>` | Bug fixes. |
| `docs/<short-desc>` | Documentation-only changes. |

`<area>` is the top-level directory or subsystem: `feat/routing-ollama-ladder`,
`feat/ingestion-treesitter-java`, `fix/retrieval-bm25-empty-index`,
`feat/benchmark-eih-swe-batch1`.

```powershell
git checkout master; git pull
git checkout -b feat/<area>-<short-desc>
# ... work, commit ...
git push -u origin feat/<area>-<short-desc>
# open a PR on GitHub into master
```

**Never** `git push --force`, never rewrite pushed history (`rebase`/`amend` on
pushed commits), never change repository visibility. Keep the repo private.

## 2. Directory ownership

The owner reviews every PR that touches their directories. Non-owners may edit
them, but only through a PR the owner approves.

| Owner | Directories |
|---|---|
| **A** (Laptop A, Avaneesh) | `routing/` `generation/` `verification/` `experiments/` `retrieval/` `sustainability/` |
| **B** (Laptop B, teammate) | `ingestion/` `knowledge/graph/` `benchmark/` `apps/` `web/` `docs/` |
| **Shared** (both review) | `core/` `configs/` `intelligence/` `knowledge/schemas/` `knowledge/vector/` `evaluation/` `agents/` `dashboard/` `datasets/` `scripts/` `tests/`, root files |

Changes to shared schemas (`knowledge/schemas/`) or `core/config.py` break the
other person's code most easily — announce them before merging.

## 3. Commits

Conventional Commits: `type(scope): summary` — types `feat`, `fix`, `docs`,
`test`, `refactor`, `chore`, `perf`. Small, single-purpose commits. Run
`python -m pytest` before every commit that touches code.

## 4. Pull Requests

- Open PRs into `master` (use the template in `.github/pull_request_template.md`).
- Tests must pass locally; say on which machine.
- The other person reviews; merge with **"Create a merge commit"** or
  **"Squash and merge"** — never force.
- Delete the feature branch on GitHub after merge (the button on the PR page);
  this deletes only the branch, never commits on `master`.
- Sync daily: `git checkout master; git pull`, then
  `git merge master` into your feature branch if it is long-lived.

## 5. Experiment results must record `machine_id`

The two laptops have different GPUs (RTX 4050 vs RTX 5050), so energy, latency and
CO₂e from them are **not comparable** unless the machine is recorded.

- `machine_id` is `laptop-a` or `laptop-b`. Put it in your local `.env` as
  `EIH_MACHINE_ID=laptop-a` (or `laptop-b`).
- Every results directory, report and table must state its `machine_id`, plus the
  GPU model, PyTorch/CUDA versions and carbon region.
- Name result folders `experiments/results/<study>/machine_A/` or `.../machine_B/`.
- Never combine runs from both machines in one comparison without a
  `machine_id` column; a final A–E comparison runs all systems on **one** machine.
  **Only Laptop A produces headline results**; Laptop B runs are development runs.
- Every result file embeds `experiments.provenance.collect_provenance()`: machine_id,
  GPU, torch/CUDA versions, Ollama model digests and the git SHA.

## 6. Data that is NOT in git

Qdrant collections, Neo4j databases, model weights, cloned corpora
(`.corpus_cache/`) and raw results are excluded by `.gitignore`. Share them via
`C:\EIH_share\` (copied by USB / cloud drive), with restore steps in
`SETUP_LAPTOP_B.md`. Never commit `.env` or any key/token.

## 7. Progress logs

Each person keeps `PROGRESS-A.md` / `PROGRESS-B.md` current — one dated entry per
session: done, measured (real numbers only), next, blocked. Commit it with your
work so the other laptop sees it after `git pull`.
