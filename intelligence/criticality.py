"""
Engineering Intelligence Hub — Heuristic Criticality & Security Analyzer
========================================================================
Estimates operational criticality, security sensitivity, and minimum required
quality thresholds based on engineering task risk profiles.

IMPORTANT RESEARCH NOTE:
These classifications represent rule-based risk stratifications for testing
quality-constrained resource allocation. They are initial heuristics, not
formal risk assessments.

Criticality Levels:
- LOW: Informational queries, documentation lookups, syntax explanations.
- MEDIUM: Standard feature development, code understanding, unit test generation.
- HIGH: Architecture changes, incident diagnosis, concurrency/performance bugs.
- CRITICAL: Security-sensitive flaws, data leakage risks, cryptographic keys, production outage.
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

from core.logging import get_logger
from knowledge.schemas.tasks import (
    CriticalityLevel,
    SDLCStage,
    SecuritySensitivity,
    TaskType,
)

logger = get_logger(__name__)

# Security trigger patterns
_SECURITY_CUES = {
    "cve", "vulnerability", "vulnerabilities", "exploit", "attack", "injection",
    "xss", "csrf", "ssrf", "sqli", "auth", "authentication", "authorization",
    "jwt", "token", "password", "secret", "private key", "crypto", "tls", "ssl",
    "path traversal", "sanitize", "privilege escalation", "permission",
}

# Production outage / disaster cues
_OUTAGE_CUES = {
    "production outage", "crash in production", "data corruption", "data loss",
    "system down", "p0", "sev1", "critical bug", "fatal error", "segfault",
}


# Production context that raises an error/defect to HIGH criticality
_PRODUCTION_CUES = {"production", "in prod", "live traffic", "customers"}


class HeuristicCriticalityAnalyzer:
    """
    Computes task criticality, security sensitivity, and recommended quality thresholds.
    """

    def analyze(
        self,
        query: str,
        sdlc_stage: Optional[SDLCStage] = None,
        task_type: Optional[TaskType] = None,
    ) -> Tuple[CriticalityLevel, SecuritySensitivity, float, List[str]]:
        """
        Analyze query for criticality, security sensitivity, and quality threshold.

        Parameters
        ----------
        query : str
            The user prompt text.
        sdlc_stage : SDLCStage, optional
            The SDLC stage.
        task_type : TaskType, optional
            The task type.

        Returns
        -------
        Tuple[CriticalityLevel, SecuritySensitivity, float, List[str]]
            (CriticalityLevel, SecuritySensitivity, quality_threshold, reason_list)
        """
        query_lower = query.lower()
        reasons: List[str] = []

        # 1. Security Sensitivity Assessment
        sec_matches = [w for w in _SECURITY_CUES if re.search(r"\b" + re.escape(w) + r"\b", query_lower)]
        if len(sec_matches) >= 2 or any(w in query_lower for w in ["cve", "injection", "vulnerability", "secret"]):
            security_sensitivity = SecuritySensitivity.HIGH
            reasons.append(f"High security keywords detected: {', '.join(sec_matches[:3])}")
        elif len(sec_matches) == 1:
            security_sensitivity = SecuritySensitivity.MEDIUM
            reasons.append(f"Security keyword detected: {sec_matches[0]}")
        elif task_type in {TaskType.RISK_IDENTIFICATION, TaskType.DEFECT_DETECTION}:
            security_sensitivity = SecuritySensitivity.LOW
            reasons.append("Code review task type implies baseline security awareness")
        else:
            security_sensitivity = SecuritySensitivity.NONE

        # 2. Criticality Assessment
        outage_matches = [w for w in _OUTAGE_CUES if re.search(r"\b" + re.escape(w) + r"\b", query_lower)]

        if outage_matches or security_sensitivity == SecuritySensitivity.HIGH:
            criticality = CriticalityLevel.CRITICAL
            base_threshold = 0.90
            reasons.append("Marked CRITICAL due to production outage/high security risk")
        elif task_type in {
            TaskType.ROOT_CAUSE_ASSISTANCE,
            TaskType.ARCHITECTURE_QA,
            TaskType.CHANGE_IMPACT_ANALYSIS,
        } or security_sensitivity == SecuritySensitivity.MEDIUM or (
            # Step 2a revision (2026-10-06, dev only): an error or defect is HIGH only when it is in
            # production (or security-sensitive, above); otherwise it is standard MEDIUM work.
            task_type in {TaskType.ERROR_ANALYSIS, TaskType.DEFECT_DETECTION}
            and any(re.search(r"\b" + re.escape(w) + r"\b", query_lower) for w in _PRODUCTION_CUES)
        ):
            criticality = CriticalityLevel.HIGH
            base_threshold = 0.85
            reasons.append(f"Marked HIGH criticality based on task type ({task_type}) or security sensitivity")
        elif task_type in {
            TaskType.CODE_GENERATION,
            TaskType.TEST_GENERATION,
            TaskType.CODE_EXPLANATION,
            TaskType.REQUIREMENT_UNDERSTANDING,
            TaskType.ERROR_ANALYSIS,
            TaskType.DEFECT_DETECTION,
            TaskType.TEST_FAILURE_ANALYSIS,
        }:
            criticality = CriticalityLevel.MEDIUM
            base_threshold = 0.75
            reasons.append(f"Marked MEDIUM criticality for standard engineering workflow ({task_type})")
        else:
            criticality = CriticalityLevel.LOW
            base_threshold = 0.70
            reasons.append("Marked LOW criticality for general/informational engineering task")

        return criticality, security_sensitivity, base_threshold, reasons
