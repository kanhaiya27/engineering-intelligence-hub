"""
Developer chat: OKF-grounded answers with code evidence, conversation history, streaming.

Each answer carries its traceability (concepts used and why, code evidence, citations and
invalid citations, proposals filed) and its measurements with their tier (plan §9.1):
tokens / latency / GPU energy MEASURED (NVML counter, start and end only), CO2e ESTIMATED
from that energy and the configured grid intensity, cost ESTIMATED (0 for local inference).
Chat answers are application output, not research evidence (Systems A-E run in the harness).
"""

from __future__ import annotations

import json
from typing import Any, Dict, Iterator, List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from apps.api import services
from core.config import settings

router = APIRouter(tags=["Chat"])


class ChatRequest(BaseModel):
    question: str = Field(min_length=3, max_length=4000)
    conversation_id: Optional[str] = Field(default=None, max_length=64)
    bundle: Optional[str] = Field(default=None, max_length=64)
    model_id: Optional[str] = Field(default=None, max_length=64)
    use_code: bool = True
    propose_updates: bool = True
    k: int = Field(default=5, ge=1, le=12)
    hops: int = Field(default=1, ge=0, le=2)
    code_k: int = Field(default=4, ge=0, le=8)


def _measurements(ans: Dict[str, Any]) -> Dict[str, Any]:
    from sustainability.carbon.estimator import CarbonEstimator

    extra = ans.get("generation_extra") or {}
    energy_j = extra.get("energy_joules")
    est = CarbonEstimator.from_settings()
    co2 = None if energy_j is None else round(energy_j / 3_600_000.0 * est.carbon_intensity, 6)
    return {
        "latency_ms": ans.get("latency_ms"), "stage_ms": ans.get("stage_ms"),
        "input_tokens": ans.get("input_tokens"), "output_tokens": ans.get("output_tokens"),
        "gpu_energy_joules": energy_j, "energy_reliability": extra.get("energy_reliability"),
        "co2e_grams": co2, "carbon_intensity_gco2_per_kwh": est.carbon_intensity, "carbon_region": est.region,
        "cost_usd": 0.0, "model_id": ans.get("model_id"), "model_digest": extra.get("model_digest"),
        "machine_id": settings.machine_id,
        "tiers": {"tokens": "MEASURED", "latency_ms": "MEASURED",
                  "gpu_energy_joules": "MEASURED" if energy_j is not None else "UNAVAILABLE",
                  "co2e_grams": "ESTIMATED" if co2 is not None else "UNAVAILABLE", "cost_usd": "ESTIMATED"},
    }


def _agent(req: ChatRequest):
    from knowledge.okf.agent import OKFAgent

    bundle = req.bundle or settings.okf.default_bundle
    ws = services.workspace(bundle)
    llm = services.llm()
    if not llm.is_available():
        raise services.unavailable("Ollama", f"not reachable at {settings.secrets.local_model_base_url}")
    model = req.model_id or settings.model.default_model_id
    if model not in (llm.list_available_models() or []):
        raise services.unavailable("Model", f"'{model}' is not pulled in Ollama")
    try:
        vec = services.vector_index()
    except Exception:  # noqa: BLE001 - the agent reports lexical mode itself
        vec = None
    code = services.code_evidence if req.use_code else None
    return OKFAgent(ws, llm, model, vector_index=vec, code_evidence=code,
                    max_output_tokens=settings.model.max_tokens), bundle


def _conversation(req: ChatRequest, bundle: str) -> str:
    store = services.conversations()
    if req.conversation_id:
        if store.get(req.conversation_id) is None:
            raise HTTPException(404, "conversation not found")
        return req.conversation_id
    return store.create(req.question[:80], bundle)["id"]


@router.post("/chat")
def chat(req: ChatRequest) -> Dict[str, Any]:
    agent, bundle = _agent(req)
    cid = _conversation(req, bundle)
    store = services.conversations()
    history = store.history(cid)
    store.add_message(cid, "user", req.question)
    ans = agent.answer(req.question, k=req.k, hops=req.hops, code_k=req.code_k if req.use_code else 0,
                       propose=req.propose_updates, history=history).to_dict()
    ans["measurements"] = _measurements(ans)
    msg = store.add_message(cid, "assistant", ans["answer"], meta=ans)
    return {"conversation_id": cid, "message_id": msg["id"], **ans}


def _sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


@router.post("/chat/stream")
def chat_stream(req: ChatRequest) -> StreamingResponse:
    """Server-sent events: `conversation`, `context`, `delta`*, `answer`, or `error`."""
    agent, bundle = _agent(req)  # 503 before the stream starts if a service is down
    cid = _conversation(req, bundle)
    store = services.conversations()
    history = store.history(cid)
    store.add_message(cid, "user", req.question)

    def events() -> Iterator[str]:
        yield _sse("conversation", {"conversation_id": cid, "bundle": bundle})
        try:
            for kind, payload in agent.answer_stream(req.question, k=req.k, hops=req.hops,
                                                      code_k=req.code_k if req.use_code else 0,
                                                      propose=req.propose_updates, history=history):
                if kind == "answer":
                    ans = payload.to_dict()
                    ans["measurements"] = _measurements(ans)
                    msg = store.add_message(cid, "assistant", ans["answer"], meta=ans)
                    yield _sse("answer", {"conversation_id": cid, "message_id": msg["id"], **ans})
                else:
                    yield _sse(kind, payload)
        except Exception as exc:  # noqa: BLE001 - surface, never fake an answer
            store.add_message(cid, "assistant", f"[error] {exc}", meta={"error": str(exc)})
            yield _sse("error", {"message": str(exc)})

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/conversations")
def list_conversations(q: Optional[str] = None, limit: int = Query(100, ge=1, le=500)) -> List[Dict[str, Any]]:
    return services.conversations().list(limit=limit, query=q)


@router.get("/conversations/{cid}")
def get_conversation(cid: str) -> Dict[str, Any]:
    conv = services.conversations().get(cid)
    if conv is None:
        raise HTTPException(404, "conversation not found")
    return conv


class RenameRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)


@router.patch("/conversations/{cid}")
def rename_conversation(cid: str, req: RenameRequest) -> Dict[str, Any]:
    if not services.conversations().rename(cid, req.title):
        raise HTTPException(404, "conversation not found")
    return {"id": cid, "title": req.title}


@router.delete("/conversations/{cid}")
def delete_conversation(cid: str) -> Dict[str, Any]:
    if not services.conversations().delete(cid):
        raise HTTPException(404, "conversation not found")
    return {"deleted": cid}
