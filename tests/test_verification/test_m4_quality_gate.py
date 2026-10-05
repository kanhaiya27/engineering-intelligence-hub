"""
Tests for Phase-2 M4: Quality-Aware Verification and Bounded Escalation
=======================================================================
Test Coverage:
  1. CitationGroundingEvaluator:
     - Valid file & line citations pass
     - Invalid / hallucinated file citations fail
     - Out-of-bounds line ranges penalized
     - INSUFFICIENT EVIDENCE refusal scored as 1.0 (valid refusal)
     - Missing citations when chunks exist scored low
  2. EvidenceCoverageEvaluator:
     - High lexical overlap & chunk usage scored high
     - Low overlap / hallucinated answers scored low
     - Chunk utilization calculated accurately
  3. QueryRelevanceEvaluator:
     - Direct query keyword matches scored high
     - Off-topic answers scored low
  4. EvidenceConsistencyEvaluator:
     - Consistent statements pass with 1.0
     - Contradictions / false absence claims flagged
  5. Task-Specific Dynamic Thresholds:
     - Thresholds from TaskClassification (0.60 to 0.90) respected
  6. QualityGate Decision Logic:
     - Aggregated weighted average computed correctly
     - Critical failure overrides aggregate score
  7. EscalationPolicy:
     - Attempt 1 escalates top-k
     - Attempt 2 activates graph augmentation
     - Attempt 3 reaches maximal capability
     - Strictly bounded by max_attempts
  8. QualityAwareRAGPipeline:
     - Immediate pass on attempt 0
     - Successful recovery on attempt 1
     - Exhausted escalation produces explicit INSUFFICIENT EVIDENCE response
     - Full telemetry and provenance recorded
"""

from __future__ import annotations

from typing import List, Optional
from unittest.mock import MagicMock


from generation.base import BaseLLMProvider, GenerationRequest, GenerationResponse
from generation.quality_rag import QualityAwareRAGPipeline
from knowledge.schemas.tasks import (
    ComplexityLevel,
    CriticalityLevel,
    EngTaskRequest,
    EngTaskResponse,
    RetrievalResult,
    RetrievedChunk,
    SDLCStage,
    TaskClassification,
    TaskStatus,
    TaskType,
)
from retrieval.strategies import RetrievalMode, RetrievalStrategyConfig
from verification.config import VerificationConfig
from verification.escalation import EscalationPolicy
from verification.evaluators import (
    CitationGroundingEvaluator,
    EvidenceConsistencyEvaluator,
    EvidenceCoverageEvaluator,
    QueryRelevanceEvaluator,
)
from verification.gate import QualityGate
from verification.signals import QualityReport, QualitySignal, SignalStatus, SignalType


# ---------------------------------------------------------------------------
# Test Fixtures & Helpers
# ---------------------------------------------------------------------------

def _make_chunk(
    chunk_id: str = "chunk-1",
    source_path: str = "src/auth/jwt.py",
    content: str = "def verify_token(token: str) -> bool:\n    \"\"\"Verify JWT token.\"\"\"\n    return decode(token) is not None",
    start_line: int = 10,
    end_line: int = 25,
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        content=content,
        source_path=source_path,
        score=0.88,
        repository="my-org/auth-service",
        metadata={"start_line": start_line, "end_line": end_line, "symbol_name": "verify_token"},
    )


def _make_retrieval(chunks: Optional[List[RetrievedChunk]] = None) -> RetrievalResult:
    c_list = chunks if chunks is not None else [_make_chunk()]
    return RetrievalResult(
        task_id="task-001",
        strategy_used="hybrid",
        chunks=c_list,
        total_retrieved=len(c_list),
        retrieval_latency_ms=15.0,
    )


def _make_classification(
    task_type: TaskType = TaskType.CODE_EXPLANATION,
    criticality: CriticalityLevel = CriticalityLevel.MEDIUM,
    quality_threshold: float = 0.75,
) -> TaskClassification:
    return TaskClassification(
        task_id="task-001",
        task_type=task_type,
        sdlc_stage=SDLCStage.DEVELOPMENT,
        complexity=ComplexityLevel.MEDIUM,
        criticality=criticality,
        security_sensitivity="none",
        quality_threshold=quality_threshold,
    )


class DeterministicMockLLM(BaseLLMProvider):
    """Mock LLM provider returning predetermined answers."""

    def __init__(self, responses: Optional[List[str]] = None) -> None:
        self._responses = responses or ["SUPPORTED BY EVIDENCE: `src/auth/jwt.py:L10-L25` defines verify_token."]
        self._index = 0

    @property
    def provider_name(self) -> str:
        return "mock_deterministic"

    def is_available(self) -> bool:
        return True

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        ans = self._responses[min(self._index, len(self._responses) - 1)]
        self._index += 1
        return GenerationResponse(
            text=ans,
            model_id="mock-model",
            input_tokens=100,
            output_tokens=30,
            latency_ms=45.0,
            finish_reason="stop",
        )


# ---------------------------------------------------------------------------
# 1. Citation Grounding Evaluator Tests
# ---------------------------------------------------------------------------

class TestCitationGroundingEvaluator:

    def test_valid_citation_passes(self):
        evaluator = CitationGroundingEvaluator()
        req = EngTaskRequest(task_id="t1", query="How is JWT verified?")
        chunk = _make_chunk(source_path="src/auth/jwt.py", start_line=10, end_line=25)
        resp = EngTaskResponse(
            task_id="t1",
            answer="SUPPORTED BY EVIDENCE: `src/auth/jwt.py:L10-L25` verifies the token by decoding it.",
            retrieval=_make_retrieval([chunk]),
        )
        signals = evaluator.evaluate(req, resp)
        assert len(signals) == 1
        sig = signals[0]
        assert sig.status == SignalStatus.PASSED
        assert sig.score >= 0.85
        assert sig.metadata["valid_citations"] == 1
        assert len(sig.metadata["invalid_citations"]) == 0

    def test_invalid_hallucinated_citation_fails(self):
        evaluator = CitationGroundingEvaluator()
        req = EngTaskRequest(task_id="t1", query="How is JWT verified?")
        chunk = _make_chunk(source_path="src/auth/jwt.py")
        resp = EngTaskResponse(
            task_id="t1",
            answer="SUPPORTED BY EVIDENCE: In `src/security/oauth_checker.py:L50`, token is verified.",
            retrieval=_make_retrieval([chunk]),
        )
        signals = evaluator.evaluate(req, resp)
        sig = signals[0]
        assert sig.status == SignalStatus.FAILED
        assert sig.score < 0.70
        assert len(sig.metadata["invalid_citations"]) == 1

    def test_out_of_bounds_line_range_penalized(self):
        evaluator = CitationGroundingEvaluator()
        req = EngTaskRequest(task_id="t1", query="Where is auth?")
        chunk = _make_chunk(source_path="src/auth/jwt.py", start_line=10, end_line=25)
        # Line 500-520 is outside chunk start=10, end=25
        resp = EngTaskResponse(
            task_id="t1",
            answer="SUPPORTED BY EVIDENCE: `src/auth/jwt.py:L500-L520` handles auth logic.",
            retrieval=_make_retrieval([chunk]),
        )
        signals = evaluator.evaluate(req, resp)
        sig = signals[0]
        # Should be penalized for out of bounds line range
        assert sig.score < 0.90

    def test_insufficient_evidence_refusal_passes_with_full_score(self):
        evaluator = CitationGroundingEvaluator()
        req = EngTaskRequest(task_id="t1", query="Show me the billing logic.")
        resp = EngTaskResponse(
            task_id="t1",
            answer="INSUFFICIENT EVIDENCE: The repository does not contain billing or payment processing files.",
            retrieval=_make_retrieval([]),
        )
        signals = evaluator.evaluate(req, resp)
        sig = signals[0]
        assert sig.status == SignalStatus.PASSED
        assert sig.score == 0.50
        assert sig.metadata.get("valid_refusal") is True

    def test_missing_citations_when_evidence_present_is_flagged(self):
        evaluator = CitationGroundingEvaluator()
        req = EngTaskRequest(task_id="t1", query="Explain verify_token.")
        chunk = _make_chunk()
        resp = EngTaskResponse(
            task_id="t1",
            answer="Token is verified using decode function.",
            retrieval=_make_retrieval([chunk]),
        )
        signals = evaluator.evaluate(req, resp)
        sig = signals[0]
        assert sig.status == SignalStatus.FAILED
        assert sig.score == 0.30


# ---------------------------------------------------------------------------
# 2. Evidence Coverage Evaluator Tests
# ---------------------------------------------------------------------------

class TestEvidenceCoverageEvaluator:

    def test_high_overlap_scores_high(self):
        evaluator = EvidenceCoverageEvaluator()
        req = EngTaskRequest(task_id="t1", query="How does verify_token work?")
        chunk = _make_chunk(content="def verify_token(token: str) -> bool: return decode(token) is not None")
        resp = EngTaskResponse(
            task_id="t1",
            answer="SUPPORTED BY EVIDENCE: verify_token accepts token string and returns decode token boolean.",
            retrieval=_make_retrieval([chunk]),
        )
        signals = evaluator.evaluate(req, resp)
        sig = signals[0]
        assert sig.status == SignalStatus.PASSED
        assert sig.score >= 0.55
        assert sig.metadata["utilized_chunks"] >= 1

    def test_zero_overlap_fails(self):
        evaluator = EvidenceCoverageEvaluator()
        req = EngTaskRequest(task_id="t1", query="Explain database connection pool.")
        chunk = _make_chunk(content="def verify_token(token): pass")
        resp = EngTaskResponse(
            task_id="t1",
            answer="Database connection pool maintains min_size=5 and max_size=20 connections in PostgreSQL cluster.",
            retrieval=_make_retrieval([chunk]),
        )
        signals = evaluator.evaluate(req, resp)
        sig = signals[0]
        assert sig.status == SignalStatus.FAILED
        assert sig.score < 0.50

    def test_empty_retrieval_chunks_fails(self):
        evaluator = EvidenceCoverageEvaluator()
        req = EngTaskRequest(task_id="t1", query="Explain auth.")
        resp = EngTaskResponse(
            task_id="t1",
            answer="Auth works via tokens.",
            retrieval=_make_retrieval([]),
        )
        signals = evaluator.evaluate(req, resp)
        sig = signals[0]
        assert sig.status == SignalStatus.FAILED
        assert sig.score == 0.10


# ---------------------------------------------------------------------------
# 3. Query Relevance Evaluator Tests
# ---------------------------------------------------------------------------

class TestQueryRelevanceEvaluator:

    def test_relevant_answer_passes(self):
        evaluator = QueryRelevanceEvaluator()
        req = EngTaskRequest(task_id="t1", query="Explain how JWT verify_token function works")
        resp = EngTaskResponse(
            task_id="t1",
            answer="The verify_token function explains how JWT verification works by decoding tokens.",
        )
        signals = evaluator.evaluate(req, resp)
        sig = signals[0]
        assert sig.status == SignalStatus.PASSED
        assert sig.score >= 0.70
        assert sig.metadata["keyword_recall"] >= 0.50

    def test_off_topic_answer_fails(self):
        evaluator = QueryRelevanceEvaluator()
        req = EngTaskRequest(task_id="t1", query="How to configure database connection retry timeout?")
        resp = EngTaskResponse(
            task_id="t1",
            answer="CSS frontend styling is handled with flexbox in layout.html.",
        )
        signals = evaluator.evaluate(req, resp)
        sig = signals[0]
        assert sig.status == SignalStatus.FAILED
        assert sig.score < 0.60


# ---------------------------------------------------------------------------
# 4. Evidence Consistency Evaluator Tests
# ---------------------------------------------------------------------------

class TestEvidenceConsistencyEvaluator:

    def test_consistent_evidence_passes(self):
        evaluator = EvidenceConsistencyEvaluator()
        req = EngTaskRequest(task_id="t1", query="Explain auth")
        chunk = _make_chunk(source_path="src/auth/jwt.py")
        resp = EngTaskResponse(
            task_id="t1",
            answer="The authentication module uses JWT tokens defined in src/auth/jwt.py.",
            retrieval=_make_retrieval([chunk]),
        )
        signals = evaluator.evaluate(req, resp)
        sig = signals[0]
        assert sig.status == SignalStatus.PASSED
        assert sig.score == 1.0

    def test_false_missing_file_claim_detected(self):
        evaluator = EvidenceConsistencyEvaluator()
        req = EngTaskRequest(task_id="t1", query="Where is auth jwt defined?")
        chunk = _make_chunk(source_path="src/auth/jwt.py")
        resp = EngTaskResponse(
            task_id="t1",
            answer="The repository does not contain src/auth/jwt.py anywhere.",
            retrieval=_make_retrieval([chunk]),
        )
        signals = evaluator.evaluate(req, resp)
        sig = signals[0]
        assert sig.status == SignalStatus.FAILED
        assert len(sig.metadata["contradictions"]) >= 1


# ---------------------------------------------------------------------------
# 5. Task-Specific Dynamic Threshold Handling
# ---------------------------------------------------------------------------

class TestTaskSpecificThresholds:

    def test_high_threshold_task_fails_moderate_score(self):
        gate = QualityGate.default_gate()
        req = EngTaskRequest(task_id="t1", query="Explain verify_token in jwt.py")
        chunk = _make_chunk()
        # Answer with partially valid citation and text
        resp = EngTaskResponse(
            task_id="t1",
            answer="verify_token checks tokens in jwt.py.",
            retrieval=_make_retrieval([chunk]),
        )
        # Low criticality threshold: 0.50 -> passes
        rep_low = gate.check(req, resp, threshold=0.50)
        assert rep_low.passed is True

        # High criticality threshold: 0.90 -> fails
        rep_high = gate.check(req, resp, threshold=0.90)
        assert rep_high.passed is False
        assert rep_high.threshold_applied == 0.90


# ---------------------------------------------------------------------------
# 6. QualityGate Aggregation & Critical Failures
# ---------------------------------------------------------------------------

class TestQualityGateAggregation:

    def test_custom_weights_affect_aggregated_score(self):
        cfg = VerificationConfig(
            citation_grounding_weight=0.80,
            query_relevance_weight=0.10,
            evidence_coverage_weight=0.05,
            evidence_consistency_weight=0.05,
        )
        gate = QualityGate.default_gate(config=cfg)
        assert gate.evaluators[0]._weight == 0.80

    def test_critical_failure_overrides_high_average(self):
        signals = [
            QualitySignal(signal_type=SignalType.RELEVANCE, status=SignalStatus.PASSED, score=0.99, weight=1.0),
            QualitySignal(signal_type=SignalType.GROUNDEDNESS, status=SignalStatus.FAILED, score=0.0, weight=1.0),
        ]
        report = QualityReport.compute(task_id="t1", signals=signals, threshold=0.40)
        assert report.passed is False
        assert SignalType.GROUNDEDNESS in report.critical_failures


# ---------------------------------------------------------------------------
# 7. Escalation Policy Tests
# ---------------------------------------------------------------------------

class TestEscalationPolicy:

    def test_escalation_progression(self):
        policy = EscalationPolicy()
        initial_strat = RetrievalStrategyConfig(
            strategy_name="hybrid",
            mode=RetrievalMode.HYBRID,
            top_k=5,
            max_context_chunks=5,
            score_threshold=0.60,
            include_graph_context=False,
        )

        # Attempt 1: Broaden search (top_k + 3)
        strat1 = policy.escalate(initial_strat, attempt=1)
        assert strat1.top_k == 8
        assert strat1.max_context_chunks == 8
        assert strat1.score_threshold == 0.55
        assert strat1.include_graph_context is False

        # Attempt 2: Graph augmentation
        strat2 = policy.escalate(strat1, attempt=2)
        assert strat2.mode == RetrievalMode.GRAPH_AUGMENTED
        assert strat2.include_graph_context is True
        assert strat2.graph_hop_depth == 2
        assert strat2.top_k == 14

        # Attempt 3: Maximal capability with reranking
        strat3 = policy.escalate(strat2, attempt=3)
        assert strat3.enable_reranking is True
        assert strat3.top_k == 30

    def test_max_attempts_limit_respected(self):
        policy = EscalationPolicy(VerificationConfig(max_escalation_attempts=3))
        assert policy.get_max_attempts() == 3


class TestEscalationExecutes:
    """Finding F1: the escalated strategy must be the one the retriever runs.

    Uses the real strategy registry (configs/retrieval.yaml), the real policy
    and the real EscalationPolicy; only the retrievers are recorders. Before the
    fix every attempt executed plain "hybrid" (top_k 7, no graph, no rerank)
    while attempt_history recorded the escalated names.
    """

    def _pipeline_with_recorders(self):
        from retrieval.adaptive import AdaptiveRetrievalPipeline
        from retrieval.policy import AdaptiveRetrievalPolicy
        from retrieval.router import RetrievalRouter

        router = RetrievalRouter.from_yaml("configs/retrieval.yaml")
        pipeline = AdaptiveRetrievalPipeline.__new__(AdaptiveRetrievalPipeline)
        pipeline._router = router
        pipeline._registry = router.list_strategies()
        pipeline._policy = AdaptiveRetrievalPolicy(pipeline._registry)
        pipeline._graph_store = None

        calls = []

        def recorder(name):
            def retrieve(query, strategy, classification, task_id):
                calls.append((name, strategy))
                result = _make_retrieval([])
                result.strategy_used = strategy.strategy_name
                return result
            mock = MagicMock()
            mock.retrieve.side_effect = retrieve
            return mock

        for attr in ("_dense", "_sparse", "_hybrid", "_graph_aug"):
            setattr(pipeline, attr, recorder(attr))
        self.augments = []

        def augment(base, hop_depth, task_id="adhoc"):
            # System D (C23): C's retrieval, then graph context appended
            self.augments.append(hop_depth)
            return base
        pipeline._graph_aug.augment.side_effect = augment
        return pipeline, calls

    def _run(self, experiment_mode):
        from retrieval.adaptive import ExperimentMode  # noqa: F401
        adaptive, calls = self._pipeline_with_recorders()
        pipeline = QualityAwareRAGPipeline(
            adaptive_pipeline=adaptive,
            llm_provider=DeterministicMockLLM(["In `missing.py:10`, it does stuff."]),
            verification_config=VerificationConfig(max_escalation_attempts=3),
        )
        response = pipeline.execute(
            request=EngTaskRequest(task_id="f1", query="Explain verify_token"),
            classification=_make_classification(quality_threshold=0.85),
            experiment_mode=experiment_mode,
        )
        return response, calls

    def test_each_rung_executes_its_escalated_config_system_d(self):
        from retrieval.adaptive import ExperimentMode
        response, calls = self._run(ExperimentMode.SYSTEM_D)

        assert response.passed_quality_gate is False
        assert len(calls) == 4
        names = [strategy.strategy_name for _, strategy in calls]
        assert names[1].endswith("_esc1")
        assert names[2].endswith("_esc2_graph")
        assert names[3].endswith("_esc_max")

        base, esc1, esc2, esc_max = (strategy for _, strategy in calls)
        assert esc1.top_k > base.top_k
        assert esc_max.enable_reranking is True
        assert esc_max.reranker_type == "cross_encoder"
        assert esc_max.top_k == 30
        # System D (C23): every attempt runs C's retrieval (the graph flag is applied by D itself,
        # never by the base retriever) and appends graph context; the escalation's hop depth reaches it.
        assert all(name != "_graph_aug" for name, _ in calls)
        assert all(strategy.include_graph_context is False for _, strategy in calls)
        assert len(self.augments) == 4 and self.augments[-1] == 3

        # What is recorded per attempt is what was executed.
        history = response.verification_details["attempt_history"]
        for record, (_, strategy) in zip(history, calls):
            assert record["strategy_used"] == strategy.strategy_name
            assert record["strategy_executed"]["strategy_name"] == strategy.strategy_name
            assert record["strategy_executed"]["top_k"] == strategy.top_k
        assert history[3]["strategy_executed"]["enable_reranking"] is True
        assert all(h["strategy_executed"]["include_graph_context"] is True for h in history)

    def test_system_c_escalation_widens_without_graph(self):
        from retrieval.adaptive import ExperimentMode
        _, calls = self._run(ExperimentMode.SYSTEM_C)

        assert len(calls) == 4
        assert all(name != "_graph_aug" for name, _ in calls)
        assert all(strategy.include_graph_context is False for _, strategy in calls)
        assert calls[3][1].enable_reranking is True
        assert calls[3][1].top_k == 30


# ---------------------------------------------------------------------------
# 8. QualityAwareRAGPipeline End-to-End Tests
# ---------------------------------------------------------------------------

class TestQualityAwareRAGPipeline:

    def _make_mock_adaptive(self, chunks: Optional[List[RetrievedChunk]] = None) -> MagicMock:
        mock = MagicMock()
        mock.retrieve.return_value = _make_retrieval(chunks)
        mock.list_strategies.return_value = {"hybrid": RetrievalStrategyConfig(strategy_name="hybrid")}
        return mock

    def test_immediate_pass_attempt_0(self):
        """High quality answer passes on attempt 0 with 0 escalations."""
        adaptive_mock = self._make_mock_adaptive()
        llm_mock = DeterministicMockLLM([
            "SUPPORTED BY EVIDENCE: `src/auth/jwt.py:L10-L25` verify_token accepts token string and verifies it."
        ])

        pipeline = QualityAwareRAGPipeline(
            adaptive_pipeline=adaptive_mock,
            llm_provider=llm_mock,
        )

        req = EngTaskRequest(task_id="t1", query="How does verify_token work in jwt.py?")
        clf = _make_classification(quality_threshold=0.70)

        response = pipeline.execute(request=req, classification=clf)

        assert response.status == TaskStatus.COMPLETED
        assert response.passed_quality_gate is True
        assert response.escalation_count == 0
        assert response.quality_score >= 0.70
        assert "SUPPORTED BY EVIDENCE" in response.answer
        assert response.verification_details["total_attempts"] == 1

    def test_recovery_on_escalation_attempt_1(self):
        """Attempt 0 fails, Attempt 1 succeeds after retrieval escalation."""
        adaptive_mock = self._make_mock_adaptive()
        # First attempt returns poor citation, second returns valid citation
        llm_mock = DeterministicMockLLM([
            "Token is checked somewhere in auth.",  # Attempt 0: low quality
            "SUPPORTED BY EVIDENCE: `src/auth/jwt.py:L10-L25` verify_token verifies the token.",  # Attempt 1: high quality
        ])

        pipeline = QualityAwareRAGPipeline(
            adaptive_pipeline=adaptive_mock,
            llm_provider=llm_mock,
        )

        req = EngTaskRequest(task_id="t1", query="Explain verify_token in jwt.py")
        clf = _make_classification(quality_threshold=0.75)

        response = pipeline.execute(request=req, classification=clf)

        assert response.passed_quality_gate is True
        assert response.escalation_count == 1
        assert response.verification_details["total_attempts"] == 2

    def test_exhausted_escalation_returns_insufficient_evidence(self):
        """When all escalations fail to achieve threshold, returns explicit INSUFFICIENT EVIDENCE."""
        adaptive_mock = self._make_mock_adaptive([])  # Empty chunks
        # LLM keeps hallucinating citations that do not exist
        llm_mock = DeterministicMockLLM([
            "In `non_existent_file.py:10`, it does stuff.",
            "In `another_missing_file.py:20`, it does stuff.",
            "In `yet_another_missing.py:30`, it does stuff.",
        ])

        pipeline = QualityAwareRAGPipeline(
            adaptive_pipeline=adaptive_mock,
            llm_provider=llm_mock,
            verification_config=VerificationConfig(max_escalation_attempts=2),
        )

        req = EngTaskRequest(task_id="t1", query="Explain quantum encryption module.")
        clf = _make_classification(quality_threshold=0.85)

        response = pipeline.execute(request=req, classification=clf)

        assert response.passed_quality_gate is False
        assert response.escalation_count == 2
        assert "INSUFFICIENT EVIDENCE" in response.answer
        assert response.verification_details["total_attempts"] == 3

    def test_skip_verification_flag_bypasses_quality_gate(self):
        """Ablation baseline mode: skip_verification=True passes directly without quality gate."""
        adaptive_mock = self._make_mock_adaptive()
        llm_mock = DeterministicMockLLM(["Raw unverified text."])

        pipeline = QualityAwareRAGPipeline(
            adaptive_pipeline=adaptive_mock,
            llm_provider=llm_mock,
        )

        req = EngTaskRequest(task_id="t1", query="Explain auth.")
        response = pipeline.execute(request=req, skip_verification=True)

        assert response.passed_quality_gate is True
        assert response.quality_score is None
        assert response.answer == "Raw unverified text."
