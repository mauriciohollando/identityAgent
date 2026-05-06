"""Stripe gateway adapter exposing AP2-like mandate endpoints."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
from typing import Any

import httpx
import stripe
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from stripe_adapter import store

logger = logging.getLogger(__name__)


def _require_bearer(request: Request, env_key: str) -> JSONResponse | None:
    token = os.environ.get(env_key, "").strip()
    if not token:
        return JSONResponse({"error": f"{env_key} not configured"}, status_code=503)
    auth = request.headers.get("authorization", "")
    if auth != f"Bearer {token}":
        return JSONResponse({"error": "forbidden"}, status_code=403)
    return None


def _authorize_client(request: Request) -> JSONResponse | None:
    return _require_bearer(request, "STRIPE_ADAPTER_CLIENT_TOKEN")


def _authorize_ops(request: Request) -> JSONResponse | None:
    return _require_bearer(request, "STRIPE_ADAPTER_OPS_TOKEN")


def _stripe_key() -> str:
    return os.environ.get("STRIPE_SECRET_KEY", "").strip()


def _stripe_config() -> None:
    key = _stripe_key()
    if not key:
        raise RuntimeError("STRIPE_SECRET_KEY is required")
    stripe.api_key = key


def _webhook_target() -> str:
    return os.environ.get("AUDITOR_WEBHOOK_URL", "").strip()


def _auditor_subscription_sync_url() -> str:
    explicit = os.environ.get("AUDITOR_SUBSCRIPTION_SYNC_URL", "").strip()
    if explicit:
        return explicit
    payment_url = _webhook_target().rstrip("/")
    if payment_url.endswith("/internal/webhooks/payment"):
        return payment_url[: -len("payment")] + "subscription-sync"
    return ""


def _auditor_webhook_secret() -> str:
    return os.environ.get("PAYMENT_WEBHOOK_SECRET", "").strip()


def _stripe_price_to_tier() -> dict[str, str]:
    raw = os.environ.get("STRIPE_PRICE_TO_TIER_JSON", "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    return {
        str(k): str(v)
        for k, v in data.items()
        if isinstance(k, str) and isinstance(v, str)
    }


def _tier_to_price_id(tier: str) -> str | None:
    """Pick a stable price id for a tier (STRIPE_PRICE_TO_TIER_JSON may list many)."""
    t = tier.strip().lower()
    candidates = sorted(
        pid for pid, label in _stripe_price_to_tier().items() if label.lower() == t
    )
    return candidates[0] if candidates else None


def _subscription_price_catalog() -> dict[str, str]:
    """tier_id -> price_id for API consumers (stable: lexicographically first price per tier)."""
    inv = _stripe_price_to_tier()
    out: dict[str, str] = {}
    for price_id in sorted(inv.keys()):
        tier = inv[price_id]
        if tier not in out:
            out[tier] = price_id
    return out


def _subscription_to_dict(sub: Any) -> dict[str, Any]:
    if isinstance(sub, dict):
        return sub
    if hasattr(sub, "to_dict"):
        d = sub.to_dict()
        return d if isinstance(d, dict) else {}
    try:
        return dict(sub)
    except Exception:
        return {}


def _tier_id_from_subscription_dict(sub_d: dict[str, Any]) -> str | None:
    meta = sub_d.get("metadata") if isinstance(sub_d.get("metadata"), dict) else {}
    if meta.get("tier_id"):
        return str(meta["tier_id"])
    items = sub_d.get("items")
    lines: list[Any] = []
    if isinstance(items, dict):
        lines = list(items.get("data") or [])
    elif isinstance(items, list):
        lines = items
    price_id: str | None = None
    if lines and isinstance(lines[0], dict):
        price = lines[0].get("price")
        if isinstance(price, dict):
            pid = price.get("id")
            price_id = str(pid) if pid else None
        elif isinstance(price, str):
            price_id = price
    mapping = _stripe_price_to_tier()
    if price_id and price_id in mapping:
        return mapping[price_id]
    return None


def _subscription_entitlement_status(sub_d: dict[str, Any]) -> str:
    s = str(sub_d.get("status", "")).lower()
    if s in ("active", "trialing", "past_due"):
        return "active"
    return "canceled"


def _stripe_expand_id(obj: Any) -> str | None:
    if isinstance(obj, str) and obj:
        return obj
    if isinstance(obj, dict):
        sid = obj.get("id")
        return str(sid) if sid else None
    return None


async def _forward_subscription_sync(payload: dict[str, Any]) -> None:
    target = _auditor_subscription_sync_url()
    if not target:
        return
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    sec = _auditor_webhook_secret()
    if sec:
        headers["X-Payment-Signature"] = hmac.new(
            sec.encode("utf-8"), raw, hashlib.sha256
        ).hexdigest()
    async with httpx.AsyncClient(timeout=25.0) as client:
        resp = await client.post(target, content=raw, headers=headers)
    if resp.status_code >= 400:
        logger.warning(
            "subscription_sync forward failed status=%s target=%s body=%s",
            resp.status_code,
            target,
            (resp.text or "")[:800],
        )


async def _sync_subscription_to_auditor(
    payer_agent_id: str,
    subscription: Any,
    *,
    reset_used_calls: bool,
    extra_stripe: dict[str, Any] | None = None,
) -> None:
    sub_d = _subscription_to_dict(subscription)
    ent_status = _subscription_entitlement_status(sub_d)
    tier_id = _tier_id_from_subscription_dict(sub_d)
    cps = sub_d.get("current_period_start")
    cpe = sub_d.get("current_period_end")
    if not isinstance(cps, int) or not isinstance(cpe, int):
        return
    stripe_info: dict[str, Any] = {
        "subscription_id": sub_d.get("id"),
        "subscription_status": sub_d.get("status"),
    }
    if extra_stripe:
        stripe_info.update(extra_stripe)
    if ent_status == "canceled":
        payload: dict[str, Any] = {
            "hiring_agent_id": payer_agent_id,
            "tier_id": tier_id or "unknown",
            "period_start_unix": cps,
            "period_end_unix": cpe,
            "status": "canceled",
            "reset_used_calls": True,
            "stripe": stripe_info,
        }
        await _forward_subscription_sync(payload)
        return
    if not tier_id:
        return
    payload = {
        "hiring_agent_id": payer_agent_id,
        "tier_id": tier_id,
        "period_start_unix": cps,
        "period_end_unix": cpe,
        "status": "active",
        "reset_used_calls": reset_used_calls,
        "stripe": stripe_info,
    }
    await _forward_subscription_sync(payload)


def _status_from_pi(pi_status: str) -> tuple[bool, str]:
    s = (pi_status or "").lower()
    if s in ("succeeded", "processing", "requires_capture", "requires_confirmation"):
        return True, "authorized"
    if s in ("requires_payment_method", "canceled"):
        return False, "failed"
    return False, "failed"


async def _forward_to_auditor_webhook(payload: dict[str, Any]) -> None:
    target = _webhook_target()
    if not target:
        return
    raw = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    sec = _auditor_webhook_secret()
    if sec:
        headers["X-Payment-Signature"] = hmac.new(
            sec.encode("utf-8"), raw, hashlib.sha256
        ).hexdigest()
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(target, content=raw, headers=headers)
    if resp.status_code >= 400:
        logger.warning(
            "payment webhook forward failed status=%s target=%s body=%s",
            resp.status_code,
            target,
            (resp.text or "")[:800],
        )


async def health(_: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "stripe_adapter"})


async def upsert_mapping(request: Request) -> JSONResponse:
    if err := _authorize_ops(request):
        return err
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return JSONResponse({"error": "invalid json"}, status_code=400)
    if not isinstance(body, dict):
        return JSONResponse({"error": "object body required"}, status_code=400)
    payer = body.get("payer_agent_id")
    customer = body.get("stripe_customer_id")
    if not isinstance(payer, str) or not isinstance(customer, str):
        return JSONResponse(
            {"error": "payer_agent_id and stripe_customer_id are required"},
            status_code=400,
        )
    pm = body.get("stripe_payment_method_id")
    pm_val = pm if isinstance(pm, str) else None
    meta = body.get("metadata") if isinstance(body.get("metadata"), dict) else None
    store.upsert_payer_mapping(
        payer_agent_id=payer,
        stripe_customer_id=customer,
        stripe_payment_method_id=pm_val,
        metadata=meta,
    )
    return JSONResponse({"ok": True})


async def get_mapping(request: Request) -> JSONResponse:
    if err := _authorize_ops(request):
        return err
    payer = request.path_params["payer_agent_id"]
    row = store.get_payer_mapping(payer)
    if not row:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse(row)


async def subscription_prices(request: Request) -> JSONResponse:
    """Tier → Stripe price ids from STRIPE_PRICE_TO_TIER_JSON (for Checkout UI)."""
    if err := _authorize_ops(request):
        return err
    return JSONResponse({"tiers": _subscription_price_catalog()})


async def create_checkout_session(request: Request) -> JSONResponse:
    """Stripe Checkout (subscription). Ops-only. See docs/STRIPE_ADAPTER_SETUP.md."""
    if err := _authorize_ops(request):
        return err
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return JSONResponse({"error": "invalid json"}, status_code=400)
    if not isinstance(body, dict):
        return JSONResponse({"error": "object body required"}, status_code=400)

    payer = body.get("payer_agent_id")
    success_url = body.get("success_url")
    cancel_url = body.get("cancel_url")
    price_id = body.get("price_id") if isinstance(body.get("price_id"), str) else None
    tier = body.get("tier_id") if isinstance(body.get("tier_id"), str) else None
    if isinstance(body.get("tier"), str) and not tier:
        tier = str(body["tier"])
    customer_email = (
        body.get("customer_email") if isinstance(body.get("customer_email"), str) else None
    )
    auto_customer = bool(body.get("auto_provision_customer", True))

    if not isinstance(payer, str) or not payer.strip():
        return JSONResponse({"error": "payer_agent_id required"}, status_code=400)
    if not isinstance(success_url, str) or not isinstance(cancel_url, str):
        return JSONResponse(
            {"error": "success_url and cancel_url required (https://…)"},
            status_code=400,
        )

    resolved_price = price_id
    resolved_tier: str | None = None
    if resolved_price:
        inv = _stripe_price_to_tier()
        resolved_tier = inv.get(resolved_price)
    elif tier:
        resolved_tier = tier.strip().lower()
        resolved_price = _tier_to_price_id(resolved_tier)
    if not resolved_price:
        return JSONResponse(
            {"error": "price_id or tier_id required (tier must exist in STRIPE_PRICE_TO_TIER_JSON)"},
            status_code=400,
        )

    mapping = store.get_payer_mapping(payer)
    customer_id: str | None = mapping["stripe_customer_id"] if mapping else None

    try:
        _stripe_config()
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc)}, status_code=503)

    def _ensure_customer() -> str:
        nonlocal customer_id
        if customer_id:
            return customer_id
        if not auto_customer:
            raise RuntimeError("no payer mapping; set auto_provision_customer or create mapping")
        if not customer_email:
            raise RuntimeError(
                "no payer mapping; provide customer_email to auto-provision Stripe customer"
            )
        cust = stripe.Customer.create(
            email=customer_email,
            metadata={"payer_agent_id": payer.strip()},
        )
        customer_id = cust.id
        store.upsert_payer_mapping(
            payer_agent_id=payer.strip(),
            stripe_customer_id=customer_id,
            stripe_payment_method_id=None,
            metadata={"source": "checkout_auto_provision"},
        )
        return customer_id

    def _create_session() -> Any:
        cid = _ensure_customer()
        tier_meta = resolved_tier or _stripe_price_to_tier().get(resolved_price) or "unknown"
        return stripe.checkout.Session.create(
            mode="subscription",
            customer=cid,
            client_reference_id=payer.strip(),
            line_items=[{"price": resolved_price, "quantity": 1}],
            success_url=success_url,
            cancel_url=cancel_url,
            subscription_data={
                "metadata": {
                    "payer_agent_id": payer.strip(),
                    "tier_id": str(tier_meta),
                }
            },
            metadata={"payer_agent_id": payer.strip()},
        )

    try:
        session = await request.app.state.to_thread(_create_session)
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except Exception as exc:
        logger.warning("checkout.Session.create failed: %s", exc)
        return JSONResponse({"error": str(exc)}, status_code=502)

    url = getattr(session, "url", None) if session is not None else None
    sid = getattr(session, "id", None) if session is not None else None
    return JSONResponse({"checkout_url": url, "checkout_session_id": sid})


async def create_billing_portal_session(request: Request) -> JSONResponse:
    """Stripe Customer Portal (payment method, cancel, invoices). Ops-only."""
    if err := _authorize_ops(request):
        return err
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return JSONResponse({"error": "invalid json"}, status_code=400)
    if not isinstance(body, dict):
        return JSONResponse({"error": "object body required"}, status_code=400)
    payer = body.get("payer_agent_id")
    return_url = body.get("return_url")
    if not isinstance(payer, str) or not payer.strip():
        return JSONResponse({"error": "payer_agent_id required"}, status_code=400)
    if not isinstance(return_url, str) or not return_url.strip():
        return JSONResponse({"error": "return_url required"}, status_code=400)

    mapping = store.get_payer_mapping(payer.strip())
    if not mapping:
        return JSONResponse({"error": "payer mapping not found"}, status_code=404)

    try:
        _stripe_config()
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc)}, status_code=503)

    def _portal() -> Any:
        return stripe.billing_portal.Session.create(
            customer=mapping["stripe_customer_id"],
            return_url=return_url.strip(),
        )

    try:
        portal = await request.app.state.to_thread(_portal)
    except Exception as exc:
        logger.warning("billing_portal.Session.create failed: %s", exc)
        return JSONResponse({"error": str(exc)}, status_code=502)

    url = getattr(portal, "url", None)
    return JSONResponse({"portal_url": url})


async def create_mandate(request: Request) -> JSONResponse:
    if err := _authorize_client(request):
        return err
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return JSONResponse({"error": "invalid json"}, status_code=400)
    if not isinstance(body, dict):
        return JSONResponse({"error": "object body required"}, status_code=400)

    payer = body.get("payer_agent_id")
    reason = body.get("reason", "Agent Verification Fee")
    idem = body.get("idempotency_key")
    if not isinstance(payer, str) or not isinstance(idem, str):
        return JSONResponse(
            {"error": "payer_agent_id and idempotency_key are required"},
            status_code=400,
        )
    if not isinstance(reason, str):
        return JSONResponse({"error": "reason must be string"}, status_code=400)

    cents = body.get("amount_cents")
    usd = body.get("amount_usd")
    if isinstance(cents, int):
        amount_cents = cents
    elif isinstance(usd, (int, float)):
        amount_cents = int(round(float(usd) * 100))
    else:
        return JSONResponse(
            {"error": "amount_cents or amount_usd required"},
            status_code=400,
        )
    if amount_cents <= 0:
        return JSONResponse({"error": "amount must be > 0"}, status_code=400)

    currency = (
        body.get("currency")
        if isinstance(body.get("currency"), str)
        else os.environ.get("PAYMENT_CURRENCY", "USD")
    )
    currency = currency.lower()

    cached = store.get_mandate_by_idempotency(idem)
    if cached:
        auth = str(cached.get("status", "")).lower() in (
            "authorized",
            "settled",
            "processing",
            "succeeded",
        )
        return JSONResponse(
            {
                "authorized": auth,
                "mandate_id": cached["mandate_id"],
                "status": cached.get("status"),
                "idempotent_replay": True,
            }
        )

    mapping = store.get_payer_mapping(payer)
    if not mapping:
        return JSONResponse(
            {
                "authorized": False,
                "error": "payer mapping not found",
                "payer_agent_id": payer,
            },
            status_code=402,
        )

    try:
        _stripe_config()
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc)}, status_code=503)

    customer_id = mapping["stripe_customer_id"]
    payment_method = mapping.get("stripe_payment_method_id")

    def _create_pi() -> Any:
        params: dict[str, Any] = {
            "amount": amount_cents,
            "currency": currency,
            "customer": customer_id,
            "description": reason,
            "metadata": {"payer_agent_id": payer},
            "confirm": True,
            "off_session": True,
        }
        if payment_method:
            params["payment_method"] = payment_method
        else:
            params["automatic_payment_methods"] = {"enabled": True}
        return stripe.PaymentIntent.create(**params, idempotency_key=idem)

    try:
        pi = await request.app.state.to_thread(_create_pi)
    except Exception as exc:
        mid = store.create_mandate(
            idempotency_key=idem,
            payer_agent_id=payer,
            amount_cents=amount_cents,
            currency=currency,
            reason=reason,
            status="failed",
            gateway_response={"error": str(exc)},
        )
        return JSONResponse(
            {"authorized": False, "mandate_id": mid, "status": "failed", "error": str(exc)},
            status_code=402,
        )

    authorized, mapped_status = _status_from_pi(getattr(pi, "status", ""))
    mandate_id = store.create_mandate(
        idempotency_key=idem,
        payer_agent_id=payer,
        amount_cents=amount_cents,
        currency=currency,
        reason=reason,
        status=mapped_status,
        stripe_payment_intent_id=getattr(pi, "id", None),
        gateway_response={"stripe_status": getattr(pi, "status", None)},
    )

    if mapped_status in ("authorized", "settled"):
        await _forward_to_auditor_webhook(
            {
                "gateway_mandate_id": mandate_id,
                "status": "authorized",
                "stripe_payment_intent_id": getattr(pi, "id", None),
            }
        )

    return JSONResponse(
        {
            "authorized": authorized,
            "mandate_id": mandate_id,
            "status": mapped_status,
            "stripe_payment_intent_id": getattr(pi, "id", None),
        },
        status_code=200 if authorized else 402,
    )


async def refund_mandate(request: Request) -> JSONResponse:
    if err := _authorize_client(request):
        return err
    mandate_id = request.path_params["mandate_id"]
    mandate = store.get_mandate(mandate_id)
    if not mandate:
        return JSONResponse({"error": "mandate not found"}, status_code=404)
    pi_id = mandate.get("stripe_payment_intent_id")
    if not isinstance(pi_id, str) or not pi_id:
        return JSONResponse({"error": "no stripe payment intent for mandate"}, status_code=400)
    try:
        _stripe_config()
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc)}, status_code=503)

    def _refund() -> Any:
        return stripe.Refund.create(payment_intent=pi_id)

    try:
        refund = await request.app.state.to_thread(_refund)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    store.update_mandate(
        mandate_id,
        status="refunded",
        stripe_refund_id=getattr(refund, "id", None),
        gateway_response={"refund_status": getattr(refund, "status", None)},
    )
    await _forward_to_auditor_webhook(
        {
            "gateway_mandate_id": mandate_id,
            "status": "refunded",
            "stripe_refund_id": getattr(refund, "id", None),
        }
    )
    return JSONResponse({"ok": True, "refund_id": getattr(refund, "id", None)})


async def stripe_webhook(request: Request) -> JSONResponse:
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "").strip()
    if not secret:
        return JSONResponse({"error": "STRIPE_WEBHOOK_SECRET not configured"}, status_code=503)
    try:
        event = stripe.Webhook.construct_event(payload=payload, sig_header=sig, secret=secret)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)

    etype = event.get("type")
    data = event.get("data", {}).get("object", {})
    if not isinstance(data, dict):
        return JSONResponse({"ok": True, "ignored": True})

    if etype in ("payment_intent.succeeded", "payment_intent.payment_failed", "payment_intent.canceled"):
        pi_id = data.get("id")
        if isinstance(pi_id, str):
            mandate = store.find_mandate_by_pi(pi_id)
            if mandate:
                if etype == "payment_intent.succeeded":
                    status = "settled"
                elif etype == "payment_intent.payment_failed":
                    status = "failed"
                else:
                    status = "canceled"
                store.update_mandate(
                    mandate["mandate_id"],
                    status=status,
                    gateway_response={"stripe_event": etype},
                )
                await _forward_to_auditor_webhook(
                    {
                        "gateway_mandate_id": mandate["mandate_id"],
                        "status": status,
                        "stripe_payment_intent_id": pi_id,
                    }
                )

    if etype == "charge.refunded":
        pi_id = data.get("payment_intent")
        if isinstance(pi_id, str):
            mandate = store.find_mandate_by_pi(pi_id)
            if mandate:
                store.update_mandate(
                    mandate["mandate_id"],
                    status="refunded",
                    gateway_response={"stripe_event": etype},
                )
                await _forward_to_auditor_webhook(
                    {
                        "gateway_mandate_id": mandate["mandate_id"],
                        "status": "refunded",
                        "stripe_payment_intent_id": pi_id,
                    }
                )

    if etype == "invoice.paid":
        inv = data
        sub_id = inv.get("subscription")
        if sub_id:
            cust = _stripe_expand_id(inv.get("customer"))
            if cust:
                mapping = store.find_payer_by_stripe_customer_id(cust)
                if mapping:
                    try:
                        _stripe_config()

                        def _retrieve_sub() -> Any:
                            return stripe.Subscription.retrieve(str(sub_id))

                        sub_obj = await request.app.state.to_thread(_retrieve_sub)
                        await _sync_subscription_to_auditor(
                            mapping["payer_agent_id"],
                            sub_obj,
                            reset_used_calls=True,
                            extra_stripe={
                                "invoice_id": inv.get("id"),
                                "event_type": etype,
                            },
                        )
                    except Exception as exc:
                        logger.warning("invoice.paid subscription sync failed: %s", exc)

    if etype in ("customer.subscription.updated", "customer.subscription.deleted"):
        sub_data = data
        cust = _stripe_expand_id(sub_data.get("customer"))
        if cust:
            mapping = store.find_payer_by_stripe_customer_id(cust)
            if mapping:
                reset = etype == "customer.subscription.deleted"
                try:
                    await _sync_subscription_to_auditor(
                        mapping["payer_agent_id"],
                        sub_data,
                        reset_used_calls=reset,
                        extra_stripe={"event_type": etype},
                    )
                except Exception as exc:
                    logger.warning("subscription webhook sync failed: %s", exc)

    return JSONResponse({"ok": True})


def _to_thread(func):
    import asyncio

    return asyncio.to_thread(func)


routes = [
    Route("/health", health, methods=["GET"]),
    Route("/v1/admin/mappings", upsert_mapping, methods=["POST"]),
    Route("/v1/admin/mappings/{payer_agent_id}", get_mapping, methods=["GET"]),
    Route("/v1/subscription/prices", subscription_prices, methods=["GET"]),
    Route("/v1/checkout/sessions", create_checkout_session, methods=["POST"]),
    Route("/v1/billing/portal-sessions", create_billing_portal_session, methods=["POST"]),
    Route("/v1/mandates", create_mandate, methods=["POST"]),
    Route("/v1/mandates/{mandate_id}/refund", refund_mandate, methods=["POST"]),
    Route("/v1/stripe/webhook", stripe_webhook, methods=["POST"]),
]

app = Starlette(routes=routes)
app.state.to_thread = _to_thread

