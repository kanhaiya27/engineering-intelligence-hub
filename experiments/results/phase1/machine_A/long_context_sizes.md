# Long-context probe, part 1 — prompt sizes from the real corpus

48046 chunks in `eih_knowledge`, formatted as the pipeline formats evidence and counted with `Qwen/Qwen2.5-Coder-1.5B-Instruct`. Prompt overhead (system prompt + chat template + question): **236 tokens** (MEASURED). Recorded 2026-10-05T08:07:42+00:00.

Tokens per formatted chunk (MEASURED):

| Scope | n | mean | p50 | p90 | p95 | p99 | max |
|---|---|---|---|---|---|---|---|
| all | 48046 | 184.3 | 117 | 374 | 515 | 903 | 67021 |
| fastapi/fastapi | 18899 | 170.5 | 110 | 331 | 443 | 878 | 39743 |
| pallets/flask | 1489 | 210.0 | 160 | 414 | 520 | 929 | 2329 |
| psf/requests | 976 | 168.6 | 120 | 339 | 440 | 707 | 2577 |
| pylint-dev/pylint | 10819 | 152.3 | 93 | 303 | 469 | 822 | 11496 |
| pytest-dev/pytest | 6889 | 210.1 | 155 | 422 | 548 | 624 | 67021 |
| sphinx-doc/sphinx | 8974 | 229.8 | 140 | 494 | 574 | 1234 | 47496 |

Prompt tokens for N evidence chunks (DERIVED: 20000 random draws, seed 42; worst case = the N longest chunks in the corpus):

| N chunks | p50 | p90 | p95 | p99 | max drawn | worst case |
|---|---|---|---|---|---|---|
| 3 | 691 | 1127 | 1331 | 2133 | 67555 | 154496 |
| 5 | 1038 | 1622 | 1896 | 2999 | 68067 | 195557 |
| 8 | 1568 | 2316 | 2671 | 4013 | 69966 | 228936 |
| 10 | 1910 | 2756 | 3149 | 4639 | 68660 | 244624 |
| 14 | 2613 | 3622 | 4099 | 5787 | 70051 | 270470 |
| 15 | 2782 | 3840 | 4335 | 5986 | 69463 | 275521 |
| 18 | 3317 | 4481 | 5030 | 7028 | 72147 | 289154 |
| 20 | 3667 | 4909 | 5518 | 7489 | 71633 | 297811 |
| 24 | 4381 | 5770 | 6419 | 8967 | 72463 | 312900 |
