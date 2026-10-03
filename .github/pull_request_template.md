## What & why

<!-- One or two sentences: what this PR changes and why. Link issues/decisions (RD-xxx). -->

## Area / owner

- [ ] Touches only my own directories (see `docs/WORKFLOW.md` §2)
- [ ] Touches the other person's or shared directories → requested their review
- [ ] Changes `knowledge/schemas/` or `core/config.py` (announced to the team)

## Testing

- Machine: `laptop-a` / `laptop-b`
- `python -m pytest` result: `___ passed, ___ skipped, ___ failed`
- Docker (Qdrant/Neo4j) running during tests: yes / no

## Results & research integrity (if this PR reports numbers)

- [ ] Every number comes from a run that actually executed (no mock-LLM results presented as findings)
- [ ] `machine_id`, GPU, carbon region and manifest hash are recorded
- [ ] Held-out test split was not used
- [ ] Not applicable — no results in this PR

## Safety

- [ ] No secrets (`.env`, keys, tokens) and no large data (snapshots, dumps, weights, `.corpus_cache/`)
- [ ] `PROGRESS-A.md` / `PROGRESS-B.md` updated
