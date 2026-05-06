"""Internal HTTP routes: payment webhooks, ops summary, prepaid credit grants."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from datetime import UTC
from datetime import datetime
from typing import Any

import payment_store as store
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from payments import apply_webhook_payload


async def payment_webhook(request: Request) -> JSONResponse:
    raw = await request.body()
    secret = os.environ.get("PAYMENT_WEBHOOK_SECRET", "").strip()
    if secret:
        sig = request.headers.get("x-payment-signature", "").strip()
        expected = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
        if not sig or not hmac.compare_digest(sig, expected):
            return JSONResponse({"error": "invalid signature"}, status_code=401)
    try:
        data = json.loads(raw.decode("utf-8")) if raw else {}
    except json.JSONDecodeError:
        return JSONResponse({"error": "invalid json"}, status_code=400)
    if not isinstance(data, dict):
        return JSONResponse({"error": "object required"}, status_code=400)
    result = apply_webhook_payload(data)
    return JSONResponse(result)


def _ops_auth(request: Request) -> JSONResponse | None:
    key = os.environ.get("PAYMENT_OPS_API_KEY", "").strip()
    if not key:
        return JSONResponse({"error": "ops api disabled"}, status_code=503)
    auth = request.headers.get("authorization", "")
    if auth != f"Bearer {key}":
        return JSONResponse({"error": "forbidden"}, status_code=403)
    return None


async def payment_summary(request: Request) -> JSONResponse:
    if err := _ops_auth(request):
        return err
    from_ts = int(request.query_params.get("from_unix", "0"))
    to_ts = int(request.query_params.get("to_unix", str(int(time.time()))))
    return JSONResponse(store.summary(from_ts, to_ts))


async def payment_credit_grant(request: Request) -> JSONResponse:
    if err := _ops_auth(request):
        return err
    try:
        raw = await request.body()
        data = json.loads(raw.decode("utf-8")) if raw else {}
    except json.JSONDecodeError:
        return JSONResponse({"error": "invalid json"}, status_code=400)
    hid = data.get("hiring_agent_id")
    cents = data.get("amount_cents")
    if not isinstance(hid, str) or not isinstance(cents, int):
        return JSONResponse(
            {"error": "hiring_agent_id and amount_cents required"},
            status_code=400,
        )
    note = data.get("note") if isinstance(data.get("note"), str) else None
    bal = store.add_credits(hid, cents, note=note)
    return JSONResponse({"balance_cents": bal})


def _subscription_tiers() -> dict[str, dict[str, int | str]]:
    raw = os.environ.get("AP2_SUBSCRIPTION_TIERS_JSON", "").strip()
    if not raw:
        # Conservative defaults for launch ops; override in env.
        return {
            "starter": {"included_calls": 500, "period_days": 30},
            "growth": {"included_calls": 5000, "period_days": 30},
            "scale": {"included_calls": 30000, "period_days": 30},
        }
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, dict[str, int | str]] = {}
    for key, val in data.items():
        if not isinstance(key, str) or not isinstance(val, dict):
            continue
        inc = val.get("included_calls")
        days = val.get("period_days", 30)
        if isinstance(inc, int) and inc >= 0 and isinstance(days, int) and days > 0:
            out[key] = {"included_calls": inc, "period_days": days}
    return out


async def payment_subscription_grant(request: Request) -> JSONResponse:
    if err := _ops_auth(request):
        return err
    try:
        raw = await request.body()
        data = json.loads(raw.decode("utf-8")) if raw else {}
    except json.JSONDecodeError:
        return JSONResponse({"error": "invalid json"}, status_code=400)
    hid = data.get("hiring_agent_id")
    tier = data.get("tier_id")
    inc = data.get("included_calls")
    if not isinstance(hid, str) or not isinstance(tier, str) or not isinstance(inc, int):
        return JSONResponse(
            {"error": "hiring_agent_id, tier_id, included_calls required"},
            status_code=400,
        )
    period_days = data.get("period_days", 30)
    if not isinstance(period_days, int) or period_days <= 0:
        return JSONResponse({"error": "period_days must be positive integer"}, status_code=400)
    status = data.get("status", "active")
    if not isinstance(status, str):
        return JSONResponse({"error": "status must be string"}, status_code=400)
    start = data.get("period_start_unix")
    if isinstance(start, int):
        start_unix = start
    else:
        start_unix = int(time.time())
    end_unix = start_unix + period_days * 24 * 60 * 60
    used_calls = data.get("used_calls", 0)
    if not isinstance(used_calls, int) or used_calls < 0:
        return JSONResponse({"error": "used_calls must be non-negative integer"}, status_code=400)
    metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else None
    store.upsert_subscription_entitlement(
        hiring_agent_id=hid,
        tier_id=tier,
        included_calls=inc,
        period_start_unix=start_unix,
        period_end_unix=end_unix,
        status=status.lower(),
        used_calls=used_calls,
        metadata=metadata,
    )
    ent = store.get_subscription_entitlement(hid)
    return JSONResponse({"ok": True, "entitlement": ent})


async def payment_subscription_assign_tier(request: Request) -> JSONResponse:
    if err := _ops_auth(request):
        return err
    try:
        raw = await request.body()
        data = json.loads(raw.decode("utf-8")) if raw else {}
    except json.JSONDecodeError:
        return JSONResponse({"error": "invalid json"}, status_code=400)
    hid = data.get("hiring_agent_id")
    tier = data.get("tier_id")
    if not isinstance(hid, str) or not isinstance(tier, str):
        return JSONResponse({"error": "hiring_agent_id and tier_id required"}, status_code=400)
    tiers = _subscription_tiers()
    spec = tiers.get(tier)
    if not spec:
        return JSONResponse({"error": "unknown tier_id", "available_tiers": sorted(tiers.keys())}, status_code=400)
    now = int(time.time())
    period_days = int(spec["period_days"])
    store.upsert_subscription_entitlement(
        hiring_agent_id=hid,
        tier_id=tier,
        included_calls=int(spec["included_calls"]),
        period_start_unix=now,
        period_end_unix=now + period_days * 24 * 60 * 60,
        status="active",
        used_calls=0,
        metadata={"assigned_at": datetime.now(UTC).isoformat()},
    )
    ent = store.get_subscription_entitlement(hid)
    return JSONResponse({"ok": True, "entitlement": ent})


async def payment_subscription_get(request: Request) -> JSONResponse:
    if err := _ops_auth(request):
        return err
    hid = request.path_params["hiring_agent_id"]
    ent = store.get_subscription_entitlement(hid)
    if not ent:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse(ent)


async def payment_subscription_tiers(request: Request) -> JSONResponse:
    if err := _ops_auth(request):
        return err
    return JSONResponse({"tiers": _subscription_tiers()})


def _apply_stripe_subscription_sync(data: dict[str, Any]) -> dict[str, Any]:
    """Apply entitlement update from Stripe adapter (HMAC-protected webhook)."""
    hid = data.get("hiring_agent_id")
    tier_id = data.get("tier_id")
    if not isinstance(hid, str) or not isinstance(tier_id, str):
        return {"ok": False, "error": "hiring_agent_id and tier_id required"}
    pstart = data.get("period_start_unix")
    pend = data.get("period_end_unix")
    if not isinstance(pstart, int) or not isinstance(pend, int):
        return {"ok": False, "error": "period_start_unix and period_end_unix required"}
    if pend <= pstart:
        return {"ok": False, "error": "invalid period"}
    status = str(data.get("status", "active")).lower()
    reset_used = bool(data.get("reset_used_calls", False))
    tiers = _subscription_tiers()
    spec = tiers.get(tier_id)
    if not spec and status not in ("canceled", "cancelled", "ended"):
        return {"ok": False, "error": "unknown tier_id", "tier_id": tier_id}
    stripe_meta = data.get("stripe") if isinstance(data.get("stripe"), dict) else {}
    base_meta = {
        "source": "stripe",
        "synced_at": datetime.now(UTC).isoformat(),
        **stripe_meta,
    }
    if status in ("canceled", "cancelled", "ended", "unpaid"):
        store.upsert_subscription_entitlement(
            hiring_agent_id=hid,
            tier_id=tier_id,
            included_calls=0,
            used_calls=0,
            period_start_unix=pstart,
            period_end_unix=pend,
            status="canceled",
            metadata=base_meta,
        )
        store._log_event(
            "subscription_sync_canceled",
            hiring_agent_id=hid,
            meta={"tier_id": tier_id},
        )
        return {"ok": True, "entitlement": store.get_subscription_entitlement(hid)}
    included = int(spec["included_calls"]) if spec else 0
    if included <= 0:
        return {"ok": False, "error": "tier has no included_calls"}
    if reset_used:
        used_calls = 0
    else:
        prev = store.get_subscription_entitlement(hid)
        used_calls = int(prev["used_calls"]) if prev else 0
        used_calls = min(used_calls, included)
    store.upsert_subscription_entitlement(
        hiring_agent_id=hid,
        tier_id=tier_id,
        included_calls=included,
        used_calls=used_calls,
        period_start_unix=pstart,
        period_end_unix=pend,
        status="active",
        metadata=base_meta,
    )
    store._log_event(
        "subscription_sync_active",
        hiring_agent_id=hid,
        meta={"tier_id": tier_id, "reset_used_calls": reset_used},
    )
    return {"ok": True, "entitlement": store.get_subscription_entitlement(hid)}


async def subscription_sync_webhook(request: Request) -> JSONResponse:
    """Stripe adapter forwards subscription lifecycle here (same HMAC as payment webhook)."""
    raw = await request.body()
    secret = os.environ.get("PAYMENT_WEBHOOK_SECRET", "").strip()
    if secret:
        sig = request.headers.get("x-payment-signature", "").strip()
        expected = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
        if not sig or not hmac.compare_digest(sig, expected):
            return JSONResponse({"error": "invalid signature"}, status_code=401)
    try:
        data = json.loads(raw.decode("utf-8")) if raw else {}
    except json.JSONDecodeError:
        return JSONResponse({"error": "invalid json"}, status_code=400)
    if not isinstance(data, dict):
        return JSONResponse({"error": "object required"}, status_code=400)
    store.init_payment_db()
    result = _apply_stripe_subscription_sync(data)
    status_code = 200 if result.get("ok") else 400
    return JSONResponse(result, status_code=status_code)


def payment_internal_routes() -> list[Route]:
    return [
        Route("/internal/webhooks/payment", payment_webhook, methods=["POST"]),
        Route(
            "/internal/webhooks/subscription-sync",
            subscription_sync_webhook,
            methods=["POST"],
        ),
        Route("/internal/payments/summary", payment_summary, methods=["GET"]),
        Route("/internal/payments/credits", payment_credit_grant, methods=["POST"]),
        Route("/internal/payments/subscriptions/tiers", payment_subscription_tiers, methods=["GET"]),
        Route("/internal/payments/subscriptions/grant", payment_subscription_grant, methods=["POST"]),
        Route("/internal/payments/subscriptions/assign-tier", payment_subscription_assign_tier, methods=["POST"]),
        Route("/internal/payments/subscriptions/{hiring_agent_id}", payment_subscription_get, methods=["GET"]),
    ]
