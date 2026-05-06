"""HTTP API for trust checks, disputes, and metrics (no Gemini required).

Run::

    PYTHONPATH=src uvicorn dev_api:app --host 0.0.0.0 --port 8081

Optional header ``X-Verification-Tier: enterprise`` selects stricter sample rules.
"""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import auditor
from disputes.store import create_dispute
from disputes.store import init_disputes_db
from payment_routes import payment_internal_routes
from payment_store import init_payment_db
from middleware.rate_limit import RateLimitMiddleware
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.responses import PlainTextResponse
from starlette.routing import Route

from observability.metrics import render_prometheus

logger = logging.getLogger(__name__)


async def health(_: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "mode": "dev_api"})


def _tier_from_request(request: Request) -> str | None:
    return request.headers.get("x-verification-tier")


async def verify_identity_http(request: Request) -> JSONResponse:
    try:
        body = await _read_json(request)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    agent_id = body.get("target_agent_id")
    if not agent_id or not isinstance(agent_id, str):
        return JSONResponse(
            {"error": "target_agent_id (string) is required"}, status_code=400
        )
    tier = body.get("verification_tier")
    if tier is not None and not isinstance(tier, str):
        return JSONResponse({"error": "verification_tier must be a string"}, status_code=400)
    tier = tier or _tier_from_request(request)
    result = await auditor.verify_identity(agent_id, verification_tier=tier)
    return JSONResponse(result)


async def audit_reputation_http(request: Request) -> JSONResponse:
    try:
        body = await _read_json(request)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    agent_id = body.get("target_agent_id")
    if not agent_id or not isinstance(agent_id, str):
        return JSONResponse(
            {"error": "target_agent_id (string) is required"}, status_code=400
        )
    context = body.get("context") or ""
    if not isinstance(context, str):
        return JSONResponse({"error": "context must be a string"}, status_code=400)
    tier = body.get("verification_tier")
    if tier is not None and not isinstance(tier, str):
        return JSONResponse({"error": "verification_tier must be a string"}, status_code=400)
    tier = tier or _tier_from_request(request)
    result = await auditor.audit_reputation(
        agent_id, context, verification_tier=tier
    )
    return JSONResponse(result)


async def create_dispute_http(request: Request) -> JSONResponse:
    try:
        body = await _read_json(request)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    target = body.get("target_agent_id")
    reason = body.get("reason")
    if not target or not isinstance(target, str):
        return JSONResponse({"error": "target_agent_id is required"}, status_code=400)
    if not reason or not isinstance(reason, str):
        return JSONResponse({"error": "reason is required"}, status_code=400)
    token = body.get("verification_token")
    hiring = body.get("hiring_agent_id")
    contact = body.get("contact")
    dispute_id = await create_dispute(
        target_agent_id=target,
        reason=reason,
        verification_token=token if isinstance(token, str) else None,
        hiring_agent_id=hiring if isinstance(hiring, str) else None,
        contact=contact if isinstance(contact, str) else None,
        extra={k: v for k, v in body.items() if k not in ("reason", "target_agent_id")},
    )
    return JSONResponse({"dispute_id": dispute_id, "status": "received"}, status_code=201)


async def metrics_http(_: Request) -> PlainTextResponse:
    return PlainTextResponse(
        render_prometheus(), media_type="text/plain; version=0.0.4; charset=utf-8"
    )


async def _read_json(request: Request) -> dict[str, Any]:
    raw = await request.body()
    if not raw:
        return {}
    try:
        data = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("invalid JSON body") from exc
    if not isinstance(data, dict):
        raise ValueError("JSON body must be an object")
    return data


@asynccontextmanager
async def lifespan(_: Starlette) -> AsyncIterator[None]:
    init_disputes_db()
    init_payment_db()
    yield


routes = [
    Route("/health", health, methods=["GET"]),
    Route("/metrics", metrics_http, methods=["GET"]),
    Route("/v1/verify-identity", verify_identity_http, methods=["POST"]),
    Route("/v1/audit-reputation", audit_reputation_http, methods=["POST"]),
    Route("/v1/disputes", create_dispute_http, methods=["POST"]),
    *payment_internal_routes(),
]

app = Starlette(
    routes=routes,
    lifespan=lifespan,
    middleware=[Middleware(RateLimitMiddleware)],
)
