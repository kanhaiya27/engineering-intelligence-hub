"""
Engineering Intelligence Hub — Controlled Evaluation Package (Phase-2 M5)
==========================================================================
"""

from experiments.m5.analysis import (
    AblationDelta,
    ParetoPoint,
    compute_ablation_deltas,
    compute_pareto_frontier,
    compute_system_summary,
)
from experiments.m5.failure_tax import (
    FailureCategory,
    FailureDiagnosis,
    diagnose_trial_failure,
)
from experiments.m5.human_eval import (
    HumanEvaluationRating,
    sample_human_evaluation_tasks,
)
from experiments.m5.manifest import (
    ExperimentManifest,
    FrozenVariables,
    SystemConfig,
    SystemID,
)
from experiments.m5.metrics import (
    AggregatedTaskMetrics,
    TrialResult,
    compute_trial_aggregates,
)
from experiments.m5.reports import generate_markdown_report
from experiments.m5.runner import M5BenchmarkRunner
from experiments.m5.splits import (
    DEFAULT_SPLIT_SEED,
    FROZEN_BENCHMARK_VERSION,
    create_stratified_splits,
    load_or_create_splits,
)

__all__ = [
    "ExperimentManifest",
    "SystemConfig",
    "SystemID",
    "FrozenVariables",
    "TrialResult",
    "AggregatedTaskMetrics",
    "compute_trial_aggregates",
    "FailureCategory",
    "FailureDiagnosis",
    "diagnose_trial_failure",
    "HumanEvaluationRating",
    "sample_human_evaluation_tasks",
    "M5BenchmarkRunner",
    "AblationDelta",
    "ParetoPoint",
    "compute_system_summary",
    "compute_ablation_deltas",
    "compute_pareto_frontier",
    "generate_markdown_report",
    "create_stratified_splits",
    "load_or_create_splits",
    "FROZEN_BENCHMARK_VERSION",
    "DEFAULT_SPLIT_SEED",
]
