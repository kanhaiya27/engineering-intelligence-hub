"""
Engineering Intelligence Hub — Heuristic Task Complexity Model
===============================================================
Estimates engineering task complexity based on transparent heuristic features.

IMPORTANT RESEARCH NOTE:
These complexity signals are initial heuristic features designed for rule-based
classification and experimental baseline stratification. They are NOT claimed
to be scientifically validated complexity metrics.

Heuristic Signals Analyzed:
1. Query length / token span (longer technical prompts with requirements).
2. Number of explicit repository components / entity references.
3. Cross-file / architectural dependency cues ("architecture", "across files", "flow", "call graph").
4. Reasoning depth keywords ("why", "root cause", "trade-off", "design choice", "diagnose").
5. Code modification / multi-step requirements ("refactor", "implement", "migrate", "concurrency").
"""

from __future__ import annotations

import re
from typing import List, Optional, Set, Tuple

from core.logging import get_logger
from knowledge.schemas.tasks import ComplexityLevel, SDLCStage, TaskType

logger = get_logger(__name__)

# Heuristic keyword dictionaries
_ARCHITECTURAL_CUES = {
    "architecture", "architectural", "structure", "design", "flow", "lifecycle",
    "dependency", "dependencies", "interaction", "pipeline", "subsystem",
    "cross-module", "cross-file", "call graph", "dataflow", "component",
}

_DEEP_REASONING_CUES = {
    "why", "root cause", "trade-off", "tradeoff", "rationale", "diagnose",
    "deadlock", "race condition", "memory leak", "performance bottleneck",
    "explain in depth", "step by step", "mechanism", "under the hood",
}

_MULTI_STEP_CUES = {
    "refactor", "migrate", "implement", "rewrite", "generate unit tests",
    "multi-file", "end-to-end", "integration test", "concurrency", "asyncio",
}


class HeuristicComplexityAnalyzer:
    """
    Computes heuristic complexity scores and maps them to ComplexityLevel.
    """

    def analyze(
        self,
        query: str,
        sdlc_stage: Optional[SDLCStage] = None,
        task_type: Optional[TaskType] = None,
        context_files_count: int = 0,
    ) -> Tuple[ComplexityLevel, float, List[str]]:
        """
        Estimate task complexity level and return scoring breakdown.

        Parameters
        ----------
        query : str
            The user prompt or engineering task text.
        sdlc_stage : SDLCStage, optional
            The classified or hinted SDLC stage.
        task_type : TaskType, optional
            The classified task type.
        context_files_count : int, optional
            Number of explicit files attached to the request.

        Returns
        -------
        Tuple[ComplexityLevel, float, List[str]]
            (ComplexityLevel, numerical score 0.0-1.0, list of triggered reason strings)
        """
        query_lower = query.lower()
        score = 0.2  # Base baseline complexity
        reasons: List[str] = []

        # 1. Query length heuristic (longer queries tend to define complex multi-part requirements)
        word_count = len(query.split())
        if word_count > 40:
            score += 0.25
            reasons.append(f"Long query prompt ({word_count} words)")
        elif word_count > 20:
            score += 0.15
            reasons.append(f"Medium query prompt ({word_count} words)")

        # 2. Context files count
        if context_files_count > 2:
            score += 0.25
            reasons.append(f"Multiple context files provided ({context_files_count} files)")
        elif context_files_count > 0:
            score += 0.10
            reasons.append(f"Single context file provided ({context_files_count} file)")

        # 3. Architectural / structural cues
        arch_matches = [w for w in _ARCHITECTURAL_CUES if re.search(r"\b" + re.escape(w) + r"\b", query_lower)]
        if arch_matches:
            score += 0.20
            reasons.append(f"Architectural cues detected: {', '.join(arch_matches[:3])}")

        # 4. Deep reasoning cues
        reasoning_matches = [w for w in _DEEP_REASONING_CUES if re.search(r"\b" + re.escape(w) + r"\b", query_lower)]
        if reasoning_matches:
            score += 0.20
            reasons.append(f"Deep reasoning cues detected: {', '.join(reasoning_matches[:3])}")

        # 5. Multi-step development / migration cues
        multistep_matches = [w for w in _MULTI_STEP_CUES if re.search(r"\b" + re.escape(w) + r"\b", query_lower)]
        if multistep_matches:
            score += 0.15
            reasons.append(f"Multi-step / implementation cues detected: {', '.join(multistep_matches[:3])}")

        # 6. SDLC Stage & TaskType baselines
        if task_type in {
            TaskType.ARCHITECTURE_DECISION_SUPPORT,
            TaskType.CHANGE_IMPACT_ANALYSIS,
            TaskType.TECHNICAL_DEBT_ANALYSIS,
            TaskType.ROOT_CAUSE_ASSISTANCE,
        }:
            score += 0.15
            reasons.append(f"Inherently complex task type: {task_type}")

        # Normalize score to [0.0, 1.0]
        final_score = min(1.0, max(0.0, round(score, 2)))

        # Map to ComplexityLevel enum
        if final_score >= 0.75:
            level = ComplexityLevel.VERY_HIGH
        elif final_score >= 0.50:
            level = ComplexityLevel.HIGH
        elif final_score >= 0.30:
            level = ComplexityLevel.MEDIUM
        else:
            level = ComplexityLevel.LOW

        return level, final_score, reasons
