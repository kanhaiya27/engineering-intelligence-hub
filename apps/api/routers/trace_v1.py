"""
POST /v1/trace and POST /v1/trace/stream: the frozen pipeline-trace contract v1
(docs/API_CONTRACT.md, apps/api/contract/v1.py).

Errors use `ErrorResponse` (never a stack trace, path or config); `X-Request-ID` is echoed
or generated; one trace runs at a time (one local GPU) and a concurrent request gets 429
with Retry-After instead of silently queueing behind a multi-minute System E run.
"""

from __future__ import annotations

import json
import queue
import re
import threading
import uuid
from typing import Iterator, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from apps.api.contract import v1
from core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/v1", tags=["Pipeline trace (contract v1)"])

_GPU = threading.Lock()
_RID = re.compile(r"^[A-Za-z0-9-]{1,64}$")
RETRY_AFTER_S = 30

_EVENTS = {
    "classification": v1.ClassificationEvent, "retrieval": v1.RetrievalEvent,
    "generation": v1.GenerationEvent, "verification": v1.VerificationEvent, "escalation": v1.EscalationEvent,
}


def request_id(req: Request) -> str:
    rid = req.headers.get("X-Request-ID", "")
    return rid if _RID.match(rid) else str(uuid.uuid4())


def error_response(rid: str, status: int, code: v1.ErrorCode, message: str,
                   retry_after: Optional[int] = None) -> JSONResponse:
    body = v1.ErrorResponse(request_id=rid, error=v1.ErrorBody(code=code, message=message[:500],
                                                                 retry_after_s=retry_after))
    headers = {"X-Request-ID": rid}
    if retry_after is not None:
        headers["Retry-After"] = str(retry_after)
    return JSONResponse(body.model_dump(mode="json"), status_code=status, headers=headers)


def _unavailable(rid: str) -> Optional[JSONResponse]:
    from apps.api.trace_adapter import runner
    try:
        llm = runner().llm_provider
        if not llm.is_available():
            return error_response(rid, 503, v1.ErrorCode.PIPELINE_UNAVAILABLE, "The local model server is not reachable.")
    except Exception:  # noqa: BLE001
        logger.exception("trace pipeline could not be initialised")
        return error_response(rid, 503, v1.ErrorCode.PIPELINE_UNAVAILABLE, "The pipeline could not be initialised.")
    return None


@router.post("/trace", response_model=v1.PipelineTrace,
             responses={k: {"model": v1.ErrorResponse} for k in (400, 413, 422, 429, 503)})
def trace(body: v1.TraceRequest, req: Request):
    from apps.api.trace_adapter import run_trace

    rid = request_id(req)
    if (err := _unavailable(rid)) is not None:
        return err
    if not _GPU.acquire(blocking=False):
        return error_response(rid, 429, v1.ErrorCode.RATE_LIMITED, "Another trace is running on the GPU.", RETRY_AFTER_S)
    try:
        result = run_trace(body.query, body.system.value, rid, body.repository,
                           body.task_type_hint.value if body.task_type_hint else None)
    except Exception:  # noqa: BLE001
        logger.exception("trace failed")
        return error_response(rid, 500, v1.ErrorCode.INTERNAL_ERROR, "The pipeline failed while answering.")
    finally:
        _GPU.release()
    return JSONResponse(result.model_dump(mode="json"), headers={"X-Request-ID": rid})


def _frame(event) -> str:
    return f"event: {event.event}\ndata: {json.dumps(event.model_dump(mode='json'))}\n\n"


@router.post("/trace/stream", responses={k: {"model": v1.ErrorResponse} for k in (400, 413, 422, 429, 503)})
def trace_stream(body: v1.TraceRequest, req: Request):
    from apps.api.trace_adapter import execution_context, run_trace

    rid = request_id(req)
    if (err := _unavailable(rid)) is not None:
        return err
    if not _GPU.acquire(blocking=False):
        return error_response(rid, 429, v1.ErrorCode.RATE_LIMITED, "Another trace is running on the GPU.", RETRY_AFTER_S)
    trace_id = uuid.uuid4().hex
    q: "queue.Queue" = queue.Queue()

    def work():
        try:
            result = run_trace(body.query, body.system.value, rid, body.repository,
                               body.task_type_hint.value if body.task_type_hint else None,
                               emit=lambda kind, payload: q.put((kind, payload)), trace_id=trace_id)
            q.put(("trace.completed", result))
        except Exception:  # noqa: BLE001
            logger.exception("trace stream failed")
            q.put(("error", v1.ErrorBody(code=v1.ErrorCode.INTERNAL_ERROR, message="The pipeline failed while answering.")))
        finally:
            q.put(None)
            _GPU.release()

    def events() -> Iterator[str]:
        seq = 0
        yield _frame(v1.TraceStartedEvent(trace_id=trace_id, seq=seq, payload=v1.TraceStartedPayload(
            request_id=rid, system=body.system, execution=execution_context())))
        threading.Thread(target=work, daemon=True).start()
        while (item := q.get()) is not None:
            seq += 1
            kind, payload = item
            cls = {"trace.completed": v1.TraceCompletedEvent, "error": v1.ErrorEvent}.get(kind) or _EVENTS[kind]
            yield _frame(cls(trace_id=trace_id, seq=seq, payload=payload))

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"X-Request-ID": rid, "Cache-Control": "no-cache"})
