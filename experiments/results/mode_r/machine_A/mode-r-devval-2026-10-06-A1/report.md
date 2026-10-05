# Mode R: dev + val retrieval (mode-r-devval-2026-10-06-A1)

**Labels: 36 draft.** These are PROVISIONAL until the labels are human-verified (ASK_ME L1). Dev/val only; no test task was loaded.

- Tasks: 36 ({'dev': 24, 'val': 12}); commit abd5a7324c78818e150e5212666ea42e951787c5; manifest fea25caa0be4013e
- Collection eih_knowledge_v2 (53905 points); graph 37066 nodes / 58982 edges
- Labels file sha256:d91195763693…

Definitions: `evaluation/retrieval_metrics.py`. File level counts graph-context chunks (they name a file);
span level counts only chunks with source text; Precision@K divides by K.

## File level

| System | mrr | recall@1 | recall@3 | recall@5 | recall@10 | precision@1 | precision@3 | precision@5 | precision@10 | ndcg@1 | ndcg@3 | ndcg@5 | ndcg@10 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| baseline_b | 0.563 | 0.315 | 0.407 | 0.468 | 0.468 | 0.500 | 0.231 | 0.167 | 0.083 | 0.500 | 0.423 | 0.456 | 0.456 |
| system_c | 0.512 | 0.287 | 0.398 | 0.440 | 0.440 | 0.472 | 0.231 | 0.161 | 0.081 | 0.472 | 0.400 | 0.423 | 0.423 |
| system_d | 0.512 | 0.287 | 0.398 | 0.440 | 0.449 | 0.472 | 0.231 | 0.161 | 0.083 | 0.472 | 0.400 | 0.423 | 0.427 |
| system_e_esc1 | 0.612 | 0.310 | 0.463 | 0.583 | 0.620 | 0.528 | 0.269 | 0.206 | 0.111 | 0.528 | 0.459 | 0.518 | 0.533 |
| system_e_esc2 | 0.578 | 0.269 | 0.481 | 0.560 | 0.644 | 0.472 | 0.269 | 0.194 | 0.114 | 0.472 | 0.446 | 0.485 | 0.518 |
| system_e_esc_max | 0.593 | 0.278 | 0.468 | 0.597 | 0.625 | 0.500 | 0.287 | 0.206 | 0.108 | 0.500 | 0.449 | 0.505 | 0.516 |

## Span level (text chunks)

| System | mrr | recall@1 | recall@3 | recall@5 | recall@10 | precision@1 | precision@3 | precision@5 | precision@10 | ndcg@1 | ndcg@3 | ndcg@5 | ndcg@10 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| baseline_b | 0.412 | 0.190 | 0.292 | 0.363 | 0.363 | 0.333 | 0.185 | 0.144 | 0.072 | 0.333 | 0.217 | 0.210 | 0.196 |
| system_c | 0.424 | 0.213 | 0.312 | 0.368 | 0.368 | 0.361 | 0.194 | 0.144 | 0.072 | 0.361 | 0.227 | 0.216 | 0.201 |
| system_d | 0.424 | 0.213 | 0.312 | 0.368 | 0.368 | 0.361 | 0.194 | 0.144 | 0.072 | 0.361 | 0.227 | 0.216 | 0.201 |
| system_e_esc1 | 0.475 | 0.213 | 0.361 | 0.438 | 0.500 | 0.361 | 0.213 | 0.178 | 0.103 | 0.361 | 0.243 | 0.248 | 0.255 |
| system_e_esc2 | 0.432 | 0.171 | 0.361 | 0.444 | 0.502 | 0.306 | 0.222 | 0.189 | 0.108 | 0.306 | 0.238 | 0.249 | 0.251 |
| system_e_esc_max | 0.460 | 0.199 | 0.336 | 0.435 | 0.542 | 0.361 | 0.241 | 0.183 | 0.125 | 0.361 | 0.271 | 0.268 | 0.302 |

## Span level incl. graph chunks

| System | mrr | recall@1 | recall@3 | recall@5 | recall@10 | precision@1 | precision@3 | precision@5 | precision@10 | ndcg@1 | ndcg@3 | ndcg@5 | ndcg@10 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| baseline_b | 0.412 | 0.190 | 0.292 | 0.363 | 0.363 | 0.333 | 0.185 | 0.144 | 0.072 | 0.333 | 0.217 | 0.210 | 0.196 |
| system_c | 0.424 | 0.213 | 0.312 | 0.368 | 0.368 | 0.361 | 0.194 | 0.144 | 0.072 | 0.361 | 0.227 | 0.216 | 0.201 |
| system_d | 0.424 | 0.213 | 0.312 | 0.368 | 0.368 | 0.361 | 0.194 | 0.144 | 0.072 | 0.361 | 0.227 | 0.216 | 0.201 |
| system_e_esc1 | 0.475 | 0.213 | 0.361 | 0.438 | 0.500 | 0.361 | 0.213 | 0.178 | 0.103 | 0.361 | 0.243 | 0.248 | 0.255 |
| system_e_esc2 | 0.432 | 0.171 | 0.361 | 0.444 | 0.502 | 0.306 | 0.222 | 0.189 | 0.108 | 0.306 | 0.238 | 0.249 | 0.251 |
| system_e_esc_max | 0.460 | 0.199 | 0.336 | 0.435 | 0.542 | 0.361 | 0.241 | 0.183 | 0.125 | 0.361 | 0.271 | 0.268 | 0.302 |

## Zero-evidence tasks (no chunk retrieved)

- baseline_b: 0
- system_c: 3 (eih-phase1-dev-026, eih-phase1-rev-048, eih-phase1-test-032)
- system_d: 3 (eih-phase1-dev-026, eih-phase1-rev-048, eih-phase1-test-032)
- system_e_esc1: 0
- system_e_esc2: 0
- system_e_esc_max: 0

## Retrieval latency per query (ms, warm)

| System | mean | max |
|---|---|---|
| baseline_b | 457 | 864 |
| system_c | 384 | 890 |
| system_d | 430 | 996 |
| system_e_esc1 | 489 | 1140 |
| system_e_esc2 | 552 | 918 |
| system_e_esc_max | 846 | 1639 |
