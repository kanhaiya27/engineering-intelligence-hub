# Mode P sample plan (fixed before any Mode P run)

Decided 2026-11-25 by CODE RAD for the team, with Avaneesh (ASK_ME P2, WORK_PLAN C39). It
supersedes D6 / C28 "Defects4J first". This file is written **before** any Mode P run, and the
sample is not changed after the first run on a set.

## Scope

- **Sets:** all 8 Mode P sets of WORK_PLAN step 19, in the step's order (table below).
- **Systems:** all systems in the Mode P comparison (the A–E ladder plus E + routing, as the
  harness of step 19 supports them). Every system runs on the same sampled bugs.
- **Sample:** ~50 bugs per set, about 400 bugs in total.
- **GPU:** rough estimate **200–300 GPU-h (ESTIMATED)**, to be re-measured on the first set and
  replaced by the measured figure (`docs/SCHEDULE.md` §3). Running all 3,959 instances was a guessed
  ~1,300 GPU-h.

## Sampling method

1. Take the set's **official instance list** at the version pinned for it in the licence audit
   (WORK_PLAN step 12). Nothing is downloaded before that audit clears the set.
2. Take the instance ids as strings, remove duplicates, and sort them (plain string order).
3. Record the sha256 of the sorted list, joined with `\n`, next to the version.
4. Draw **50 ids uniformly without replacement** with `random.Random(42).sample(ids, 50)`. Use a new
   `random.Random(42)` per set, so one set's draw never depends on another. If a set has fewer than
   50 instances, take all of them.
5. List the sampled ids, sorted, in the set's row below and commit the file before the set's
   first run.

The seed is **42**, the project's split seed (`benchmark/data/splits_v1.0.json`, `"seed": 42`).

## Sets and sampled instance ids

None of the 8 official instance lists is in the repository yet (checked 2026-11-25), so no id is
sampled yet. Instance counts are as recorded in `docs/SCHEDULE.md` §3 and are not re-verified here.

| # | Set | Instances (SCHEDULE §3) | Version | List sha256 | Sampled instance ids (seed 42) |
|---|---|---|---|---|---|
| 1 | Defects4J | 835 | to be pinned (step 12) | — | to be sampled from the pinned version with seed 42 before the first run |
| 2 | BugsInPy | 493 | to be pinned (step 12) | — | to be sampled from the pinned version with seed 42 before the first run |
| 3 | CodeFlaws | 500 | to be pinned (step 12) | — | to be sampled from the pinned version with seed 42 before the first run |
| 4 | SWE-bench Lite | 300 | to be pinned (step 12) | — | to be sampled from the pinned version with seed 42 before the first run |
| 5 | SWE-bench Pro (public) | 731 | to be pinned (step 12) | — | to be sampled from the pinned version with seed 42 before the first run |
| 6 | SWE-rebench | ~500 | to be pinned (step 12) | — | to be sampled from the pinned version with seed 42 before the first run |
| 7 | Multi-SWE-bench flash | 300 | to be pinned (step 12) | — | to be sampled from the pinned version with seed 42 before the first run |
| 8 | SWE-bench Multilingual | 300 | to be pinned (step 12) | — | to be sampled from the pinned version with seed 42 before the first run |

## Reporting

Results are reported per set as results on a **50-bug random sample**, with the sample size and
the 95% confidence interval. They are never presented as full-set results or compared with
published full-set leaderboard numbers as if they were the same measurement.
