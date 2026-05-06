"""HTTP identity registry — accountability for agent IDs (reference implementation).

Run::

    export PYTHONPATH=src
    uvicorn identity_registry.app:app --host 0.0.0.0 --port 8091

Auditor::

    export IDENTITY_REGISTRY_URL=http://127.0.0.1:8091

Optional: ``REGISTRY_SERVICE_API_KEY`` — ``Authorization: Bearer <key>`` on all routes.
"""

from __future__ import annotations

import json
import os
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from identity_registry.store import add_key
from identity_registry.store import agent_exists
from identity_registry.store import attest_operator as attest_operator_store
from identity_registry.store import attest_partner as attest_partner_store
from identity_registry.store import get_status_payload
from identity_registry.store import register_agent
from identity_registry.store import revoke_key
from identity_registry.store import set_status


def _auth_fail(request: Request) -> JSONResponse | None:
    key = os.environ.get("REGISTRY_SERVICE_API_KEY", "").strip()
    if not key:
        return None
    auth = request.headers.get("authorization", "")
    if auth != f"Bearer {key}":
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    return None


def _admin_fail(request: Request) -> JSONResponse | None:
    key = os.environ.get("REGISTRY_ADMIN_API_KEY", "").strip()
    if not key:
        return JSONResponse(
            {"error": "operator attestation not enabled (set REGISTRY_ADMIN_API_KEY)"},
            status_code=503,
        )
    auth = request.headers.get("authorization", "")
    if auth != f"Bearer {key}":
        return JSONResponse({"error": "forbidden"}, status_code=403)
    return None


def _partner_fail(request: Request) -> JSONResponse | None:
    tok = os.environ.get("PARTNER_ATTESTATION_TOKEN", "").strip()
    if not tok:
        return JSONResponse(
            {
                "error": "partner attestation not enabled (set PARTNER_ATTESTATION_TOKEN)"
            },
            status_code=503,
        )
    if request.headers.get("x-partner-attestation-token") != tok:
        return JSONResponse({"error": "forbidden"}, status_code=403)
    return None


async def health(_: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "identity_registry"})


async def agent_status(request: Request) -> JSONResponse:
    if err := _auth_fail(request):
        return err
    agent_id = request.path_params["agent_id"]
    payload = get_status_payload(agent_id)
    if not payload:
        return JSONResponse(
            {"registered": False, "agent_id": agent_id, "flags": ["UNKNOWN_AGENT"]},
            status_code=404,
        )
    return JSONResponse(payload)


async def create_agent(request: Request) -> JSONResponse:
    if err := _auth_fail(request):
        return err
    try:
        body = await _read_json(request)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    agent_id = body.get("agent_id")
    if not agent_id or not isinstance(agent_id, str):
        return JSONResponse({"error": "agent_id is required"}, status_code=400)
    register_agent(
        agent_id=agent_id,
        org_id=body.get("org_id") if isinstance(body.get("org_id"), str) else None,
        operator_name=body.get("operator_name")
        if isinstance(body.get("operator_name"), str)
        else None,
        operator_contact=body.get("operator_contact")
        if isinstance(body.get("operator_contact"), str)
        else None,
        kyc_verified=bool(body.get("kyc_verified", False)),
        metadata=body.get("metadata") if isinstance(body.get("metadata"), dict) else None,
    )
    pk = body.get("public_key")
    algo = body.get("algorithm") if isinstance(body.get("algorithm"), str) else "unknown"
    if isinstance(pk, str) and pk.strip():
        add_key(agent_id=agent_id, public_key=pk, algorithm=algo)
    out = get_status_payload(agent_id)
    return JSONResponse(out or {}, status_code=201)


async def add_agent_key(request: Request) -> JSONResponse:
    if err := _auth_fail(request):
        return err
    agent_id = request.path_params["agent_id"]
    try:
        body = await _read_json(request)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    pk = body.get("public_key")
    if not pk or not isinstance(pk, str):
        return JSONResponse({"error": "public_key is required"}, status_code=400)
    algo = body.get("algorithm") if isinstance(body.get("algorithm"), str) else "unknown"
    if not agent_exists(agent_id):
        return JSONResponse({"error": "unknown agent_id"}, status_code=404)
    kid = add_key(agent_id=agent_id, public_key=pk, algorithm=algo)
    return JSONResponse({"key_id": kid, "status": "added"}, status_code=201)


async def revoke_agent_key(request: Request) -> JSONResponse:
    if err := _auth_fail(request):
        return err
    agent_id = request.path_params["agent_id"]
    key_id = request.path_params["key_id"]
    ok = revoke_key(agent_id, key_id)
    if not ok:
        return JSONResponse({"error": "key not found or already revoked"}, status_code=404)
    return JSONResponse({"status": "revoked"})


async def suspend_agent(request: Request) -> JSONResponse:
    if err := _auth_fail(request):
        return err
    agent_id = request.path_params["agent_id"]
    if not set_status(agent_id, "suspended"):
        return JSONResponse({"error": "unknown agent"}, status_code=404)
    return JSONResponse(get_status_payload(agent_id) or {})


async def activate_agent(request: Request) -> JSONResponse:
    if err := _auth_fail(request):
        return err
    agent_id = request.path_params["agent_id"]
    if not set_status(agent_id, "active"):
        return JSONResponse({"error": "unknown agent"}, status_code=404)
    return JSONResponse(get_status_payload(agent_id) or {})


async def revoke_agent(request: Request) -> JSONResponse:
    if err := _auth_fail(request):
        return err
    agent_id = request.path_params["agent_id"]
    if not set_status(agent_id, "revoked"):
        return JSONResponse({"error": "unknown agent"}, status_code=404)
    return JSONResponse(get_status_payload(agent_id) or {})


async def attest_operator_route(request: Request) -> JSONResponse:
    if err := _admin_fail(request):
        return err
    agent_id = request.path_params["agent_id"]
    try:
        body = await _read_json(request)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    attestor = body.get("attestor")
    if not attestor or not isinstance(attestor, str):
        return JSONResponse({"error": "attestor is required"}, status_code=400)
    notes = body.get("notes") if isinstance(body.get("notes"), str) else None
    if not attest_operator_store(agent_id, attestor=attestor, notes=notes):
        return JSONResponse({"error": "unknown agent"}, status_code=404)
    return JSONResponse(get_status_payload(agent_id) or {})


async def attest_partner_route(request: Request) -> JSONResponse:
    if err := _partner_fail(request):
        return err
    agent_id = request.path_params["agent_id"]
    try:
        body = await _read_json(request)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    partner_id = body.get("partner_id")
    partner_ref = body.get("partner_ref")
    if not partner_id or not isinstance(partner_id, str):
        return JSONResponse({"error": "partner_id is required"}, status_code=400)
    if not partner_ref or not isinstance(partner_ref, str):
        return JSONResponse({"error": "partner_ref is required"}, status_code=400)
    attestor = body.get("attestor") if isinstance(body.get("attestor"), str) else None
    if not attest_partner_store(
        agent_id,
        partner_id=partner_id,
        partner_ref=partner_ref,
        attestor=attestor,
    ):
        return JSONResponse({"error": "unknown agent"}, status_code=404)
    return JSONResponse(get_status_payload(agent_id) or {})


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
    Route("/agents/{agent_id}/status", agent_status, methods=["GET"]),
    Route("/v1/agents", create_agent, methods=["POST"]),
    Route("/v1/agents/{agent_id}/keys", add_agent_key, methods=["POST"]),
    Route(
        "/v1/agents/{agent_id}/keys/{key_id}/revoke",
        revoke_agent_key,
        methods=["POST"],
    ),
    Route("/v1/agents/{agent_id}/suspend", suspend_agent, methods=["POST"]),
    Route("/v1/agents/{agent_id}/activate", activate_agent, methods=["POST"]),
    Route("/v1/agents/{agent_id}/revoke", revoke_agent, methods=["POST"]),
    Route(
        "/v1/admin/agents/{agent_id}/attest/operator",
        attest_operator_route,
        methods=["POST"],
    ),
    Route(
        "/v1/partner/v1/agents/{agent_id}/attest",
        attest_partner_route,
        methods=["POST"],
    ),
]

app = Starlette(routes=routes)
