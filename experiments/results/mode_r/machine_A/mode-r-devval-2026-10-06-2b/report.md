# Mode R: dev + val retrieval (mode-r-devval-2026-10-06-2b)

**Labels: 36 draft.** These are PROVISIONAL until the labels are human-verified (ASK_ME L1). Dev/val only; no test task was loaded.

- Tasks: 36 ({'dev': 24, 'val': 12}); commit 31f56b8539f8d2fdc02854e105f84589da6ab289; manifest b8315d76e26a08b2
- Collection eih_knowledge_v2 (53905 points); graph 37066 nodes / 58982 edges
- Labels file sha256:d91195763693…

Definitions: `evaluation/retrieval_metrics.py`. File level counts graph-context chunks (they name a file);
span level counts only chunks with source text; Precision@K divides by K.

## File level

| System | mrr | recall@1 | recall@3 | recall@5 | recall@10 | precision@1 | precision@3 | precision@5 | precision@10 | ndcg@1 | ndcg@3 | ndcg@5 | ndcg@10 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| baseline_b | 0.563 | 0.315 | 0.407 | 0.468 | 0.468 | 0.500 | 0.231 | 0.167 | 0.083 | 0.500 | 0.423 | 0.456 | 0.456 |
| system_c | 0.557 | 0.273 | 0.435 | 0.509 | 0.519 | 0.472 | 0.259 | 0.183 | 0.094 | 0.472 | 0.426 | 0.461 | 0.465 |
| system_d | 0.557 | 0.273 | 0.435 | 0.509 | 0.532 | 0.472 | 0.259 | 0.183 | 0.097 | 0.472 | 0.426 | 0.461 | 0.470 |
| system_e_esc1 | 0.576 | 0.273 | 0.435 | 0.574 | 0.611 | 0.472 | 0.259 | 0.200 | 0.108 | 0.472 | 0.426 | 0.491 | 0.507 |
| system_e_esc2 | 0.560 | 0.259 | 0.454 | 0.537 | 0.611 | 0.444 | 0.259 | 0.189 | 0.108 | 0.444 | 0.427 | 0.467 | 0.497 |
| system_e_esc_max | 0.586 | 0.278 | 0.468 | 0.569 | 0.597 | 0.500 | 0.287 | 0.200 | 0.106 | 0.500 | 0.449 | 0.493 | 0.504 |

## Span level (text chunks)

| System | mrr | recall@1 | recall@3 | recall@5 | recall@10 | precision@1 | precision@3 | precision@5 | precision@10 | ndcg@1 | ndcg@3 | ndcg@5 | ndcg@10 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| baseline_b | 0.412 | 0.190 | 0.292 | 0.363 | 0.363 | 0.333 | 0.185 | 0.144 | 0.072 | 0.333 | 0.217 | 0.210 | 0.196 |
| system_c | 0.424 | 0.185 | 0.312 | 0.373 | 0.403 | 0.333 | 0.204 | 0.150 | 0.083 | 0.333 | 0.228 | 0.220 | 0.217 |
| system_d | 0.424 | 0.185 | 0.312 | 0.373 | 0.403 | 0.333 | 0.204 | 0.150 | 0.083 | 0.333 | 0.228 | 0.220 | 0.217 |
| system_e_esc1 | 0.442 | 0.185 | 0.333 | 0.400 | 0.472 | 0.333 | 0.204 | 0.167 | 0.100 | 0.333 | 0.230 | 0.233 | 0.246 |
| system_e_esc2 | 0.422 | 0.171 | 0.333 | 0.407 | 0.479 | 0.306 | 0.213 | 0.178 | 0.106 | 0.306 | 0.232 | 0.240 | 0.250 |
| system_e_esc_max | 0.453 | 0.199 | 0.336 | 0.407 | 0.514 | 0.361 | 0.241 | 0.178 | 0.122 | 0.361 | 0.271 | 0.263 | 0.297 |

## Span level incl. graph chunks

| System | mrr | recall@1 | recall@3 | recall@5 | recall@10 | precision@1 | precision@3 | precision@5 | precision@10 | ndcg@1 | ndcg@3 | ndcg@5 | ndcg@10 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| baseline_b | 0.412 | 0.190 | 0.292 | 0.363 | 0.363 | 0.333 | 0.185 | 0.144 | 0.072 | 0.333 | 0.217 | 0.210 | 0.196 |
| system_c | 0.424 | 0.185 | 0.312 | 0.373 | 0.403 | 0.333 | 0.204 | 0.150 | 0.083 | 0.333 | 0.228 | 0.220 | 0.217 |
| system_d | 0.424 | 0.185 | 0.312 | 0.373 | 0.403 | 0.333 | 0.204 | 0.150 | 0.083 | 0.333 | 0.228 | 0.220 | 0.217 |
| system_e_esc1 | 0.442 | 0.185 | 0.333 | 0.400 | 0.472 | 0.333 | 0.204 | 0.167 | 0.100 | 0.333 | 0.230 | 0.233 | 0.246 |
| system_e_esc2 | 0.422 | 0.171 | 0.333 | 0.407 | 0.479 | 0.306 | 0.213 | 0.178 | 0.106 | 0.306 | 0.232 | 0.240 | 0.250 |
| system_e_esc_max | 0.453 | 0.199 | 0.336 | 0.407 | 0.514 | 0.361 | 0.241 | 0.178 | 0.122 | 0.361 | 0.271 | 0.263 | 0.297 |

## Zero-evidence tasks (no chunk retrieved)

- baseline_b: 0
- system_c: 0
- system_d: 0
- system_e_esc1: 0
- system_e_esc2: 0
- system_e_esc_max: 0

## Retrieval latency per query (ms, warm)

| System | mean | max |
|---|---|---|
| baseline_b | 446 | 890 |
| system_c | 427 | 846 |
| system_d | 476 | 985 |
| system_e_esc1 | 518 | 1328 |
| system_e_esc2 | 552 | 1103 |
| system_e_esc_max | 903 | 1413 |
