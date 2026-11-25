# Classifier vs benchmark labels (classifier-after-2026-10-06)

Dev = where rules are improved; val = untouched check. Benchmark labels are pilot labels still under review.

| Split | n | stage | task type | complexity | criticality | all four |
|---|---|---|---|---|---|---|
| dev | 24 | 23/24 | 22/24 | 15/24 | 18/24 | 12/24 |
| val | 12 | 7/12 | 8/12 | 6/12 | 6/12 | 2/12 |

### dev · sdlc_stage (rows: benchmark label, columns: classifier)

| label \ predicted | architecture | code_review | development | maintenance | requirements | testing |
|---|---|---|---|---|---|---|
| architecture | 4 | 0 | 0 | 0 | 0 | 0 |
| code_review | 0 | 4 | 0 | 0 | 0 | 0 |
| development | 0 | 0 | 4 | 0 | 0 | 0 |
| maintenance | 0 | 0 | 0 | 4 | 0 | 0 |
| requirements | 1 | 0 | 0 | 0 | 3 | 0 |
| testing | 0 | 0 | 0 | 0 | 0 | 4 |

### dev · task_type (rows: benchmark label, columns: classifier)

| label \ predicted | change_understanding | code_explanation | code_generation | defect_detection | dependency_understanding | error_analysis | requirement_retrieval | requirement_understanding | review_assistance | test_failure_analysis | test_generation |
|---|---|---|---|---|---|---|---|---|---|---|---|
| architecture_qa | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| change_understanding | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| code_explanation | 0 | 3 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| code_generation | 0 | 0 | 4 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| defect_detection | 0 | 0 | 0 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| error_analysis | 0 | 0 | 0 | 0 | 0 | 2 | 0 | 0 | 0 | 0 | 0 |
| requirement_retrieval | 0 | 0 | 0 | 0 | 0 | 0 | 2 | 0 | 0 | 0 | 0 |
| requirement_understanding | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 |
| review_assistance | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 |
| test_failure_analysis | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 |
| test_generation | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 3 |

### dev · complexity (rows: benchmark label, columns: classifier)

| label \ predicted | high | low | medium |
|---|---|---|---|
| high | 0 | 1 | 1 |
| low | 0 | 5 | 2 |
| medium | 3 | 2 | 10 |

### dev · criticality (rows: benchmark label, columns: classifier)

| label \ predicted | critical | high | low | medium |
|---|---|---|---|---|
| high | 1 | 1 | 0 | 1 |
| low | 0 | 0 | 3 | 1 |
| medium | 0 | 1 | 2 | 14 |

### val · sdlc_stage (rows: benchmark label, columns: classifier)

| label \ predicted | architecture | code_review | development | maintenance | requirements | testing |
|---|---|---|---|---|---|---|
| architecture | 1 | 0 | 0 | 1 | 0 | 0 |
| code_review | 0 | 2 | 0 | 0 | 0 | 0 |
| development | 0 | 0 | 2 | 0 | 0 | 0 |
| maintenance | 0 | 0 | 1 | 0 | 0 | 1 |
| requirements | 1 | 0 | 0 | 0 | 1 | 0 |
| testing | 1 | 0 | 0 | 0 | 0 | 1 |

### val · task_type (rows: benchmark label, columns: classifier)

| label \ predicted | architecture_qa | code_explanation | code_generation | defect_detection | error_analysis | requirement_understanding | risk_identification | test_failure_analysis | test_generation |
|---|---|---|---|---|---|---|---|---|---|
| architecture_qa | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| change_understanding | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| code_explanation | 0 | 1 | 0 | 0 | 1 | 0 | 0 | 0 | 0 |
| code_generation | 0 | 0 | 2 | 0 | 0 | 0 | 0 | 0 | 0 |
| defect_detection | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 0 |
| error_analysis | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 |
| requirement_understanding | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 |
| risk_identification | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 |
| test_explanation | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| test_generation | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 |

### val · complexity (rows: benchmark label, columns: classifier)

| label \ predicted | high | low | medium |
|---|---|---|---|
| low | 1 | 3 | 1 |
| medium | 0 | 4 | 3 |

### val · criticality (rows: benchmark label, columns: classifier)

| label \ predicted | critical | high | medium |
|---|---|---|---|
| high | 1 | 1 | 2 |
| low | 0 | 0 | 3 |
| medium | 0 | 0 | 5 |
