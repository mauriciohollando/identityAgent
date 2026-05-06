"""HTTP transaction log — ingest agent runs and serve aggregates to the Trust Auditor.

Run::

    export PYTHONPATH=src
    uvicorn transaction_log.app:app --host 0.0.0.0 --port 8090

Point the auditor at it::

    export MCP_SERVER_BASE_URL=http://127.0.0.1:8090

Optional: ``LOG_SERVICE_API_KEY`` — requires ``Authorization: Bearer <key>`` on all routes.
"""

from __future__ import annotations

import json
import os
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from transaction_log.store import aggregate_for_agent
from transaction_log.store import insert_event


def _check_auth(request: Request) -> JSONResponse | None:
    key = os.environ.get("LOG_SERVICE_API_KEY", "").strip()
    if not key:
        return None
    auth = request.headers.get("authorization", "")
    if auth != f"Bearer {key}":
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    return None


async def transactions(request: Request) -> JSONResponse:
    if request.method == "GET":
        return await _get_aggregate(request)
    return await _ingest_event(request)


async def _ingest_event(request: Request) -> JSONResponse:
    if err := _check_auth(request):
        return err
    agent_id = request.path_params["agent_id"]
    try:
        body = await _read_json(request)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)

    outcome = body.get("outcome")
    if not outcome or not isinstance(outcome, str):
        return JSONResponse({"error": "outcome is required"}, status_code=400)

    context = body.get("context") if isinstance(body.get("context"), str) else ""
    latency = body.get("latency_ms")
    latency_ms = int(latency) if isinstance(latency, int) else None
    metadata = body.get("metadata") if isinstance(body.get("metadata"), dict) else {}

    try:
        eid = insert_event(
            agent_id=agent_id,
            outcome=outcome.lower(),
            context=context,
            latency_ms=latency_ms,
            metadata=metadata,
        )
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)

    return JSONResponse({"event_id": eid, "status": "stored"}, status_code=201)


async def _get_aggregate(request: Request) -> JSONResponse:
    if err := _check_auth(request):
        return err
    agent_id = request.path_params["agent_id"]
    context = request.query_params.get("context") or None
    payload = aggregate_for_agent(agent_id, context=context)
    return JSONResponse(payload)


async def health(_: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "transaction_log"})


async def _read_json(request: Request) -> dict[str, Any]:
    raw = await request.body()
    if not raw:
        return {}
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("JSON body must be an object")
    return data


routes = [
    Route("/health", health, methods=["GET"]),
    Route(
        "/v1/agents/{agent_id}/transactions",
        transactions,
        methods=["GET", "POST"],
    ),
]

app = Starlette(routes=routes)
