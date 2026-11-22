"""
The EIH knowledge agent: answers from an OKF bundle (plus optional code evidence) and
proposes knowledge updates for a human to review.

Flow (human -> interface -> OKF bundle -> agent -> OKF proposals -> human):

1. **Discover**: semantic search over the bundle's Qdrant projection (lexical search over
   the files when the vector index is unavailable, reported as such, never hidden).
2. **Follow links**: add concepts linked to/from the top hits (OKF §6), labelled with the
   concept they were reached from.
3. **Ground**: concepts go into the prompt with their trust tier, lifecycle status and
   staleness (§5), so the model and the reader both see how far each can be trusted.
   Optional code evidence (the hybrid retriever over the indexed corpus) is added as
   ``[code:n]`` blocks.
4. **Answer with citations**: the model must cite ``[okf:<concept id>]`` / ``[code:<n>]``;
   citations to anything not in the context are reported as invalid, not silently kept.
5. **Gaps**: the model lists missing, outdated or conflicting knowledge as structured
   proposals; each valid one is filed through ``KnowledgeWorkspace.propose`` and waits for a
   human. Nothing the agent writes reaches the bundle without approval.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from core.logging import get_logger
from generation.base import BaseLLMProvider, GenerationRequest
from knowledge.okf.bundle import OKFPathError, validate_concept_id
from knowledge.okf.collaboration import CollaborationError, KnowledgeWorkspace

logger = get_logger(__name__)

INSUFFICIENT = "INSUFFICIENT EVIDENCE"
_CITE_RX = re.compile(r"\[(okf|code):([^\]\s]+)\]")
_GAPS_RX = re.compile(r"```(?:json)?\s*(\{\s*\"knowledge_gaps\".*?\})\s*```", re.S)

SYSTEM_PROMPT = """You are the EIH knowledge agent for software engineers.
Answer ONLY from the CONTEXT blocks. Every factual sentence must cite its source as
[okf:<concept id>] or [code:<n>] exactly as written in the block header.
Prefer human-reviewed knowledge; say so when you rely on unverified, draft, deprecated or stale concepts.
If the context does not contain the answer, write exactly: INSUFFICIENT EVIDENCE, then say what is missing.
Never invent concept ids, file paths, APIs or numbers.

After the answer, output ONE fenced json block:
```json
{"knowledge_gaps": [
  {"kind": "create" | "update",
   "concept_id": "<folder/name, for update: an existing id from the context>",
   "type": "<OKF concept type>", "title": "...", "description": "<one sentence>",
   "body": "<markdown; cite code as [code:<n>]>",
   "rationale": "<why the bundle needs this>",
   "conflicts_with": ["<concept ids this contradicts>"]}
]}
```
Only propose knowledge that the CONTEXT supports (e.g. facts visible in [code:n] that no concept records,
or a concept the code evidence contradicts). Use an empty list when nothing is missing."""


@dataclass
class ContextConcept:
    concept_id: str
    title: str
    type: str
    trust_tier: str
    status: str
    stale: bool
    reason: str  # "search" | "link from <id>"
    score: Optional[float] = None
    content_hash: str = ""


@dataclass
class AgentAnswer:
    question: str
    answer: str
    insufficient_evidence: bool
    citations: List[str]
    invalid_citations: List[str]
    concepts: List[ContextConcept]
    code_evidence: List[Dict[str, Any]]
    proposals: List[Dict[str, Any]]
    rejected_proposals: List[Dict[str, Any]]
    retrieval_mode: str
    model_id: str
    input_tokens: int = 0
    output_tokens: int = 0
    generation_extra: Dict[str, Any] = field(default_factory=dict)  # provider-measured energy etc.
    latency_ms: float = 0.0
    stage_ms: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = dict(self.__dict__)
        d["concepts"] = [c.__dict__ for c in self.concepts]
        return d


class OKFAgent:
    def __init__(
        self,
        workspace: KnowledgeWorkspace,
        llm: BaseLLMProvider,
        model_id: str,
        vector_index=None,
        code_evidence: Optional[Callable[[str, int], List[Dict[str, Any]]]] = None,
        max_concept_chars: int = 2500,
        max_output_tokens: int = 1024,
    ):
        self.ws = workspace
        self.llm = llm
        self.model_id = model_id
        self.vector_index = vector_index
        self.code_evidence = code_evidence
        self.max_concept_chars = max_concept_chars
        self.max_output_tokens = max_output_tokens

    @property
    def actor(self) -> str:
        from core.config import settings
        safe = re.sub(r"[^A-Za-z0-9_.\-]", "-", self.model_id)
        return f"{settings.okf.agent_actor_prefix}/{safe}"

    # ------------------------------------------------------------------ retrieval

    def discover(self, question: str, k: int = 5, hops: int = 1, max_linked: int = 4):
        bundle, mode, hits = self.ws.bundle, "semantic", []
        if self.vector_index is not None:
            try:
                for h in self.vector_index.search(question, bundle=self.ws.name, limit=k * 3):
                    if h["concept_id"] not in [x[0] for x in hits] and bundle.get(h["concept_id"]):
                        hits.append((h["concept_id"], h.get("score")))
            except Exception as exc:  # noqa: BLE001 - degrade visibly
                logger.warning(f"OKF vector search failed, using lexical search: {exc}")
                mode, hits = "lexical (vector index unavailable)", []
        else:
            mode = "lexical"
        if not hits:
            hits = [(c.id, s) for c, s in bundle.search(question, limit=k)]
        hits = hits[:k]
        out = [self._ctx(cid, "search", score) for cid, score in hits]
        seen = {c.concept_id for c in out}
        linked = []
        for c in list(out):
            for n in bundle.neighbours(c.concept_id, hops=hops):
                if n not in seen and len(linked) < max_linked:
                    seen.add(n)
                    linked.append(self._ctx(n, f"link from {c.concept_id}", None))
        return out + linked, mode

    def _ctx(self, cid: str, reason: str, score: Optional[float]) -> ContextConcept:
        c = self.ws.bundle.get(cid)
        return ContextConcept(cid, c.title, c.doc.type, c.doc.trust_tier, c.doc.status, c.doc.is_stale(),
                              reason, score, c.doc.content_hash())

    def _context_text(self, concepts: List[ContextConcept], code: List[Dict[str, Any]]) -> str:
        blocks = []
        for cc in concepts:
            c = self.ws.bundle.get(cc.concept_id)
            body = c.doc.body
            if len(body) > self.max_concept_chars:
                body = body[: self.max_concept_chars] + "\n[... truncated]"
            flags = [cc.trust_tier, f"status={cc.status}"] + (["STALE"] if cc.stale else [])
            blocks.append(f"### [okf:{cc.concept_id}] {cc.title} ({cc.type}; {', '.join(flags)}; via {cc.reason})\n"
                          f"{c.doc.description}\n\n{body}")
        for i, ch in enumerate(code, 1):
            loc = ch.get("source_path") or "?"
            if ch.get("start_line"):
                loc += f":{ch['start_line']}-{ch.get('end_line', ch['start_line'])}"
            blocks.append(f"### [code:{i}] {ch.get('repository', '')} {loc}\n{ch.get('content', '')}")
        return "\n\n".join(blocks) if blocks else "(no context found)"

    # ------------------------------------------------------------------ answer

    def answer(self, question: str, k: int = 5, hops: int = 1, code_k: int = 4,
               propose: bool = True, history: Optional[List[Dict[str, str]]] = None) -> AgentAnswer:
        t0 = time.perf_counter()
        concepts, mode = self.discover(question, k=k, hops=hops)
        t1 = time.perf_counter()
        code = self.code_evidence(question, code_k) if (self.code_evidence and code_k > 0) else []
        t2 = time.perf_counter()
        context = self._context_text(concepts, code)
        messages: List[Dict[str, str]] = []  # the provider prepends system_prompt itself
        for turn in (history or [])[-6:]:
            if turn.get("role") in ("user", "assistant") and turn.get("content"):
                messages.append({"role": turn["role"], "content": turn["content"][:2000]})
        messages.append({"role": "user", "content": f"CONTEXT:\n\n{context}\n\nQUESTION: {question}"})
        resp = self.llm.generate(GenerationRequest(
            prompt=messages[-1]["content"], model_id=self.model_id, system_prompt=SYSTEM_PROMPT,
            messages=messages, max_tokens=self.max_output_tokens, temperature=0.0))
        t3 = time.perf_counter()

        text = resp.text or ""
        gaps, answer_text = self._split_gaps(text)
        ctx_ids = {c.concept_id for c in concepts}
        cited, invalid = [], []
        for kind, ref in _CITE_RX.findall(answer_text):
            ok = ref in ctx_ids if kind == "okf" else (ref.isdigit() and 1 <= int(ref) <= len(code))
            target = f"{kind}:{ref}"
            (cited if ok else invalid).append(target)
        proposals, rejected = [], []
        if propose:
            proposals, rejected = self._file_proposals(gaps, question, concepts, code)
        t4 = time.perf_counter()
        return AgentAnswer(
            question=question, answer=answer_text.strip(),
            insufficient_evidence=INSUFFICIENT in answer_text,
            citations=sorted(set(cited)), invalid_citations=sorted(set(invalid)),
            concepts=concepts, code_evidence=[{k: v for k, v in c.items() if k != "content"} | {"n": i}
                                              for i, c in enumerate(code, 1)],
            proposals=proposals, rejected_proposals=rejected, retrieval_mode=mode, model_id=self.model_id,
            input_tokens=resp.input_tokens, output_tokens=resp.output_tokens,
            generation_extra={k: v for k, v in (resp.extra or {}).items()
                              if isinstance(v, (int, float, str, bool, dict, list, type(None)))},
            latency_ms=round((t4 - t0) * 1000, 1),
            stage_ms={"okf_retrieval": round((t1 - t0) * 1000, 1), "code_retrieval": round((t2 - t1) * 1000, 1),
                      "generation": round((t3 - t2) * 1000, 1), "proposals": round((t4 - t3) * 1000, 1)},
        )

    @staticmethod
    def _split_gaps(text: str):
        m = _GAPS_RX.search(text)
        if not m:
            return [], text
        try:
            gaps = json.loads(m.group(1)).get("knowledge_gaps") or []
        except json.JSONDecodeError:
            gaps = [{"_unparseable": m.group(1)[:500]}]
        return (gaps if isinstance(gaps, list) else []), (text[: m.start()] + text[m.end():])

    def _file_proposals(self, gaps, question, concepts, code):
        filed, rejected = [], []
        ctx = {c.concept_id: c for c in concepts}
        for g in gaps[:5]:
            if not isinstance(g, dict) or "_unparseable" in g:
                rejected.append({"gap": g, "reason": "unparseable gap description"})
                continue
            kind = g.get("kind")
            try:
                cid = validate_concept_id(str(g.get("concept_id") or ""))
            except OKFPathError as exc:
                rejected.append({"gap": g, "reason": str(exc)})
                continue
            if kind == "update":
                if cid not in ctx:
                    rejected.append({"gap": g, "reason": "update of a concept the agent did not read"})
                    continue
                cur = self.ws.bundle.get(cid)
                fm = dict(cur.doc.frontmatter)
                for key in ("type", "title", "description"):
                    if g.get(key):
                        fm[key] = g[key]
                base_hash = ctx[cid].content_hash
            elif kind == "create":
                fm = {"type": g.get("type") or "Note", "title": g.get("title") or cid.rsplit("/", 1)[-1]}
                if g.get("description"):
                    fm["description"] = g["description"]
                fm["status"] = "draft"
                base_hash = None
            else:
                rejected.append({"gap": g, "reason": f"unknown kind {kind!r}"})
                continue
            evidence = [{"question": question}] + [{"okf": c} for c in ctx] + [
                {"code": i, "repository": c.get("repository"), "source_path": c.get("source_path"),
                 "start_line": c.get("start_line"), "end_line": c.get("end_line")} for i, c in enumerate(code, 1)]
            conflicts = [c for c in (g.get("conflicts_with") or []) if isinstance(c, str)]
            try:
                p = self.ws.propose(kind=kind, concept_id=cid, frontmatter=fm, body=str(g.get("body") or ""),
                                    rationale=str(g.get("rationale") or ""), actor=self.actor,
                                    base_hash=base_hash, evidence=evidence, conflicts_with=conflicts)
                filed.append(p.to_dict())
            except CollaborationError as exc:
                rejected.append({"gap": g, "reason": str(exc)})
        return filed, rejected
