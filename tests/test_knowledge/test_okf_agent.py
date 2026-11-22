"""OKF agent workflow rules (scripted LLM: tests parsing and the proposal path, not answer quality)."""

from __future__ import annotations

from pathlib import Path

import pytest

from generation.base import BaseLLMProvider, GenerationRequest, GenerationResponse
from knowledge.okf.agent import OKFAgent
from knowledge.okf.bundle import OKFBundle
from knowledge.okf.collaboration import KnowledgeWorkspace


class ScriptedLLM(BaseLLMProvider):
    def __init__(self, text: str):
        self.text, self.requests = text, []

    @property
    def provider_name(self) -> str:
        return "scripted"

    def is_available(self) -> bool:
        return True

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        self.requests.append(request)
        return GenerationResponse(text=self.text, model_id=request.model_id, input_tokens=10, output_tokens=5,
                                  latency_ms=1.0, finish_reason="stop")

    def list_available_models(self):
        return ["m"]


@pytest.fixture
def ws(tmp_path: Path) -> KnowledgeWorkspace:
    root = tmp_path / "b"
    (root / "auth").mkdir(parents=True)
    (root / "auth" / "login.md").write_text(
        "---\ntype: API Endpoint\ntitle: Login\ndescription: Session login.\n---\n\nUses [tokens](/auth/tokens.md).\n",
        encoding="utf-8")
    (root / "auth" / "tokens.md").write_text("---\ntype: Component\ntitle: Tokens\n---\n\nJWT, 15 min expiry.\n",
                                             encoding="utf-8")
    return KnowledgeWorkspace(OKFBundle(root), tmp_path / "state")


ANSWER = """Login creates a session [okf:auth/login] and tokens expire after 15 minutes [okf:auth/tokens].
The refresh path is in [code:1]. Made-up source [okf:auth/nope].

```json
{"knowledge_gaps": [
 {"kind": "create", "concept_id": "auth/refresh", "type": "Component", "title": "Token refresh",
  "description": "How tokens are refreshed.", "body": "Refresh happens in [code:1].", "rationale": "No concept covers it."},
 {"kind": "update", "concept_id": "auth/unseen", "title": "x", "rationale": "r"},
 {"kind": "create", "concept_id": "../escape", "title": "x", "rationale": "r"}
]}
```"""


def _agent(ws, text=ANSWER):
    code = lambda q, k: [{"repository": "acme/api", "source_path": "auth/refresh.py", "start_line": 3,  # noqa: E731
                          "end_line": 9, "content": "def refresh(): ..."}]
    return OKFAgent(ws, ScriptedLLM(text), "qwen2.5-coder:7b", vector_index=None, code_evidence=code)


def test_discovery_follows_links_and_reports_mode(ws):
    concepts, mode = _agent(ws).discover("login", k=1)
    assert mode == "lexical"
    assert [(c.concept_id, c.reason) for c in concepts] == [("auth/login", "search"),
                                                            ("auth/tokens", "link from auth/login")]


def test_citations_validated_and_gaps_become_pending_proposals(ws):
    agent = _agent(ws)
    res = agent.answer("How does login work?")
    assert res.citations == ["code:1", "okf:auth/login", "okf:auth/tokens"]
    assert res.invalid_citations == ["okf:auth/nope"]
    assert "knowledge_gaps" not in res.answer
    assert [p["concept_id"] for p in res.proposals] == ["auth/refresh"]
    assert res.proposals[0]["proposed_by"] == "eih_agent/qwen2.5-coder-7b"
    assert res.proposals[0]["proposed_frontmatter"]["status"] == "draft"
    assert {r["reason"][:20] for r in res.rejected_proposals} == {"update of a concept ", "invalid concept id: "}
    assert ws.bundle.get("auth/refresh") is None  # nothing written without a human
    assert len(ws.list_proposals(status="pending")) == 1
    req = agent.llm.requests[0]
    assert "[okf:auth/tokens] Tokens (Component; unverified" in req.messages[-1]["content"]
    assert all(m["role"] != "system" for m in req.messages)


def test_insufficient_evidence_flag_and_no_proposals_when_disabled(ws):
    res = _agent(ws, "INSUFFICIENT EVIDENCE: nothing about billing.").answer("billing?", propose=False)
    assert res.insufficient_evidence and res.proposals == [] and res.citations == []
