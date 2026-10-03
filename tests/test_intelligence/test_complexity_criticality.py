"""
Tests for HeuristicComplexityAnalyzer and HeuristicCriticalityAnalyzer
"""


from intelligence.complexity import HeuristicComplexityAnalyzer
from intelligence.criticality import HeuristicCriticalityAnalyzer
from knowledge.schemas.tasks import (
    ComplexityLevel,
    CriticalityLevel,
    SDLCStage,
    SecuritySensitivity,
    TaskType,
)


def test_heuristic_complexity_analyzer_levels():
    analyzer = HeuristicComplexityAnalyzer()

    # Simple short lookup
    level_low, score_low, _ = analyzer.analyze(query="What is Flask?")
    assert level_low in {ComplexityLevel.LOW, ComplexityLevel.MEDIUM}

    # Complex multi-step reasoning query
    complex_query = (
        "Explain the architectural design principles of blueprint registration under the hood, "
        "and diagnose the root cause of cross-module race conditions and memory leaks across files "
        "when using async dependencies in FastAPI."
    )
    level_high, score_high, reasons = analyzer.analyze(
        query=complex_query,
        sdlc_stage=SDLCStage.ARCHITECTURE,
        task_type=TaskType.ARCHITECTURE_QA,
        context_files_count=3,
    )
    assert level_high in {ComplexityLevel.HIGH, ComplexityLevel.VERY_HIGH}
    assert score_high > score_low
    assert len(reasons) > 0


def test_heuristic_criticality_analyzer_levels():
    analyzer = HeuristicCriticalityAnalyzer()

    # Low criticality query
    crit_low, sec_low, thresh_low, _ = analyzer.analyze(
        query="What does url_for do in Flask?",
        sdlc_stage=SDLCStage.DEVELOPMENT,
        task_type=TaskType.CODE_EXPLANATION,
    )
    assert crit_low in {CriticalityLevel.LOW, CriticalityLevel.MEDIUM}
    assert sec_low == SecuritySensitivity.NONE
    assert thresh_low <= 0.75

    # Critical security query
    crit_high, sec_high, thresh_high, reasons_high = analyzer.analyze(
        query="Critical bug: SQL injection and authentication token private key exploit found in production outage",
        sdlc_stage=SDLCStage.CODE_REVIEW,
        task_type=TaskType.DEFECT_DETECTION,
    )
    assert crit_high == CriticalityLevel.CRITICAL
    assert sec_high == SecuritySensitivity.HIGH
    assert thresh_high >= 0.85
    assert len(reasons_high) > 0
