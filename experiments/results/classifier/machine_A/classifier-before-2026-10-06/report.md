# Classifier vs benchmark labels (classifier-before-2026-10-06)

Dev = where rules are improved; val = untouched check. Benchmark labels are pilot labels still under review.

| Split | n | stage | task type | complexity | criticality | all four |
|---|---|---|---|---|---|---|
| dev | 24 | 15/24 | 16/24 | 11/24 | 11/24 | 3/24 |
| val | 12 | 5/12 | 7/12 | 6/12 | 6/12 | 1/12 |

### dev · sdlc_stage (rows: benchmark label, columns: classifier)

| label \ predicted | architecture | code_review | development | maintenance | operations | requirements | testing |
|---|---|---|---|---|---|---|---|
| architecture | 1 | 0 | 3 | 0 | 0 | 0 | 0 |
| code_review | 0 | 4 | 0 | 0 | 0 | 0 | 0 |
| development | 0 | 0 | 3 | 0 | 1 | 0 | 0 |
| maintenance | 0 | 0 | 1 | 1 | 2 | 0 | 0 |
| requirements | 0 | 0 | 1 | 0 | 0 | 3 | 0 |
| testing | 0 | 0 | 0 | 0 | 1 | 0 | 3 |

### dev · task_type (rows: benchmark label, columns: classifier)

| label \ predicted | change_understanding | code_explanation | code_generation | defect_detection | dependency_understanding | error_analysis | requirement_understanding | review_assistance | test_generation |
|---|---|---|---|---|---|---|---|---|---|
| architecture_qa | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| change_understanding | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| code_explanation | 0 | 3 | 0 | 0 | 1 | 0 | 0 | 0 | 0 |
| code_generation | 0 | 0 | 3 | 0 | 0 | 1 | 0 | 0 | 0 |
| defect_detection | 0 | 0 | 0 | 2 | 0 | 0 | 0 | 1 | 0 |
| error_analysis | 0 | 0 | 0 | 0 | 0 | 2 | 0 | 0 | 0 |
| requirement_retrieval | 0 | 0 | 0 | 0 | 0 | 0 | 2 | 0 | 0 |
| requirement_understanding | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 |
| review_assistance | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 |
| test_failure_analysis | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 |
| test_generation | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 3 |

### dev · complexity (rows: benchmark label, columns: classifier)

| label \ predicted | high | low | medium |
|---|---|---|---|
| high | 0 | 2 | 0 |
| low | 0 | 5 | 2 |
| medium | 2 | 7 | 6 |

### dev · criticality (rows: benchmark label, columns: classifier)

| label \ predicted | critical | high | low | medium |
|---|---|---|---|---|
| high | 1 | 1 | 0 | 1 |
| low | 0 | 0 | 1 | 3 |
| medium | 0 | 5 | 3 | 9 |

### val · sdlc_stage (rows: benchmark label, columns: classifier)

| label \ predicted | architecture | code_review | development | operations | requirements | testing |
|---|---|---|---|---|---|---|
| architecture | 0 | 0 | 1 | 1 | 0 | 0 |
| code_review | 0 | 2 | 0 | 0 | 0 | 0 |
| development | 0 | 0 | 2 | 0 | 0 | 0 |
| maintenance | 0 | 0 | 1 | 0 | 0 | 1 |
| requirements | 1 | 0 | 0 | 0 | 1 | 0 |
| testing | 0 | 0 | 2 | 0 | 0 | 0 |

### val · task_type (rows: benchmark label, columns: classifier)

| label \ predicted | architecture_qa | code_explanation | code_generation | defect_detection | error_analysis | repository_assistance | requirement_understanding | risk_identification | test_failure_analysis |
|---|---|---|---|---|---|---|---|---|---|
| architecture_qa | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| change_understanding | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| code_explanation | 0 | 1 | 0 | 0 | 1 | 0 | 0 | 0 | 0 |
| code_generation | 0 | 0 | 2 | 0 | 0 | 0 | 0 | 0 | 0 |
| defect_detection | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 0 |
| error_analysis | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 |
| requirement_understanding | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 |
| risk_identification | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 |
| test_explanation | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| test_generation | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 |

### val · complexity (rows: benchmark label, columns: classifier)

| label \ predicted | low | medium |
|---|---|---|
| low | 4 | 1 |
| medium | 5 | 2 |

### val · criticality (rows: benchmark label, columns: classifier)

| label \ predicted | critical | high | low | medium |
|---|---|---|---|---|
| high | 1 | 2 | 1 | 0 |
| low | 0 | 1 | 0 | 2 |
| medium | 0 | 0 | 1 | 4 |
