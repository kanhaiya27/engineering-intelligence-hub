"""
Engineering Intelligence Hub — Human Evaluation Protocol (Phase-2 M5)
======================================================================
Defines an independent human validation protocol for validating automated
quality metrics on a representative sample of 12 benchmark tasks (2 per SDLC stage).

Evaluation Dimensions (1 to 5 Likert Scale):
  1. Correctness            (Factual precision against software engineering standards)
  2. Groundedness           (Verifiability against retrieved repository artifacts)
  3. Relevance              (Topical alignment with the engineering query)
  4. Evidence Completeness  (Coverage of all necessary implementation details)
  5. Actionability          (Readiness for developer adoption without debugging)
"""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from knowledge.schemas.benchmark import BenchmarkTask


class HumanEvaluationRating(BaseModel):
    """Single human annotator rating on one system response."""
    task_id: str
    system_id: str
    annotator_id: str
    correctness: int = Field(ge=1, le=5, description="1 (Completely Wrong) to 5 (Perfect)")
    groundedness: int = Field(ge=1, le=5, description="1 (Hallucinated) to 5 (Strictly Cited)")
    relevance: int = Field(ge=1, le=5, description="1 (Off-topic) to 5 (Directly Focused)")
    evidence_completeness: int = Field(ge=1, le=5, description="1 (Incomplete) to 5 (Thorough)")
    actionability: int = Field(ge=1, le=5, description="1 (Unusable) to 5 (Production-Ready)")
    notes: Optional[str] = Field(default=None, description="Qualitative feedback / comments")

    model_config = ConfigDict(use_enum_values=True)

    @property
    def normalized_mean_score(self) -> float:
        """Compute normalized composite score in [0.0, 1.0]."""
        raw_avg = (self.correctness + self.groundedness + self.relevance + self.evidence_completeness + self.actionability) / 5.0
        return round((raw_avg - 1.0) / 4.0, 4)


def sample_human_evaluation_tasks(
    tasks: List[BenchmarkTask],
    sample_per_stage: int = 2,
) -> List[BenchmarkTask]:
    """
    Select a representative 12-task sample (sample_per_stage per SDLC stage,
    balanced across repositories and difficulties).
    """
    by_stage: Dict[str, List[BenchmarkTask]] = {}
    for t in tasks:
        stage = t.sdlc_stage.value if hasattr(t.sdlc_stage, "value") else str(t.sdlc_stage)
        if stage not in by_stage:
            by_stage[stage] = []
        by_stage[stage].append(t)

    selected: List[BenchmarkTask] = []
    for stage, stage_tasks in sorted(by_stage.items()):
        # Select 1 Flask and 1 FastAPI task
        flask_tasks = [t for t in stage_tasks if "flask" in t.repository.lower()]
        fastapi_tasks = [t for t in stage_tasks if "fastapi" in t.repository.lower()]

        if flask_tasks:
            selected.append(sorted(flask_tasks, key=lambda t: t.task_id)[0])
        if fastapi_tasks:
            selected.append(sorted(fastapi_tasks, key=lambda t: t.task_id)[0])

    return selected[: sample_per_stage * 6]
