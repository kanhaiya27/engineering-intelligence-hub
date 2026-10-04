"""
OpenAPI export for the v1 trace contract.

``build_contract_app()`` declares only the contract endpoints, so the exported
document is the frozen interface and nothing else. The serving app (step 3,
Phase 8) implements these routes with the same models; a test asserts the
committed export still matches.

    python -m apps.api.contract.openapi            # rewrite docs/api/openapi-v1.json
    python -m apps.api.contract.openapi --check    # exit 1 if the export is stale
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from pydantic import TypeAdapter

from apps.api.contract.v1 import (
    CONTRACT_VERSION,
    ErrorResponse,
    PipelineTrace,
    TraceEvent,
    TraceRequest,
)

EXPORT_PATH = Path(__file__).resolve().parents[3] / "docs" / "api" / "openapi-v1.json"

_REF_TEMPLATE = "#/components/schemas/{model}"

ERROR_RESPONSES: Dict[int | str, Dict[str, Any]] = {
    400: {"model": ErrorResponse, "description": "Invalid request"},
    413: {"model": ErrorResponse, "description": "Request body too large"},
    422: {"model": ErrorResponse, "description": "Request failed validation"},
    429: {"model": ErrorResponse, "description": "Rate limited; see Retry-After"},
    503: {"model": ErrorResponse, "description": "Pipeline and cache both unavailable"},
}


def build_contract_app() -> FastAPI:
    app = FastAPI(
        title="EIH Pipeline Trace API",
        version=CONTRACT_VERSION,
        description=(
            "Frozen v1 contract between the EIH research pipeline and the web "
            "platform. See docs/API_CONTRACT.md."
        ),
    )

    @app.post(
        "/v1/trace",
        response_model=PipelineTrace,
        responses=ERROR_RESPONSES,
        summary="Run one query and return the full pipeline trace",
        tags=["Trace v1"],
    )
    async def trace(req: TraceRequest) -> PipelineTrace:  # pragma: no cover - declaration only
        raise NotImplementedError

    @app.post(
        "/v1/trace/stream",
        responses={
            200: {
                "description": (
                    "Server-Sent Events. Each event's `event:` field equals the "
                    "JSON `event` discriminator; `data:` is one TraceEvent."
                ),
                "content": {
                    "text/event-stream": {
                        "schema": {"$ref": _REF_TEMPLATE.format(model="TraceEvent")}
                    }
                },
            },
            **ERROR_RESPONSES,
        },
        summary="Run one query and stream trace events as they happen",
        tags=["Trace v1"],
    )
    async def trace_stream(req: TraceRequest):  # pragma: no cover - declaration only
        raise NotImplementedError

    return app


def build_openapi() -> Dict[str, Any]:
    app = build_contract_app()
    doc = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    # The SSE body is not a response_model, so register TraceEvent and its
    # members in components explicitly.
    event_schema = TypeAdapter(TraceEvent).json_schema(ref_template=_REF_TEMPLATE)
    components = doc.setdefault("components", {}).setdefault("schemas", {})
    for name, schema in event_schema.pop("$defs", {}).items():
        components.setdefault(name, schema)
    components["TraceEvent"] = event_schema
    # FastAPI adds a default application/json body to 200 when none is given.
    doc["paths"]["/v1/trace/stream"]["post"]["responses"]["200"]["content"].pop(
        "application/json", None
    )
    return doc


def render() -> str:
    return json.dumps(build_openapi(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--check", action="store_true", help="fail if the export is stale")
    args = parser.parse_args(argv)

    rendered = render()
    if args.check:
        current = EXPORT_PATH.read_text(encoding="utf-8") if EXPORT_PATH.exists() else ""
        if current != rendered:
            print(f"{EXPORT_PATH.name} is stale; run python -m apps.api.contract.openapi")
            return 1
        print(f"{EXPORT_PATH.name} is up to date (contract {CONTRACT_VERSION})")
        return 0

    EXPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    EXPORT_PATH.write_text(rendered, encoding="utf-8", newline="\n")
    print(f"wrote {EXPORT_PATH} (contract {CONTRACT_VERSION})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
