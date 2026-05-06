"""Payments: stub, prepaid credits, or live treasury gateway with idempotency + ledger."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from typing import Any

import httpx

import payment_store as store

logger = logging.getLogger(__name__)


def _gateway_base() -> str:
    return os.environ.get("AP2_GATEWAY_URL", "").strip().rstrip("/")


def _gateway_token() -> str:
    return os.environ.get("AP2_GATEWAY_TOKEN", "").strip()


def verification_fee_usd() -> float:
    return float(os.environ.get("VERIFICATION_FEE_USD", "0.10"))


def verification_fee_cents() -> int:
    return int(round(verification_fee_usd() * 100))


@dataclass
class PaymentMandate:
    authorized: bool
    mandate_id: str | None = None


def _currency() -> str:
    return os.environ.get("PAYMENT_CURRENCY", "USD").strip() or "USD"


def _mandates_url() -> str:
    base = _gateway_base()
    path = os.environ.get("AP2_GATEWAY_MANDATES_PATH", "/v1/mandates").strip()
    if not path.startswith("/"):
        path = "/" + path
    return f"{base}{path}"


def _refund_url(gateway_mandate_id: str) -> str:
    base = _gateway_base()
    tpl = os.environ.get(
        "AP2_GATEWAY_REFUND_PATH",
        "/v1/mandates/{mandate_id}/refund",
    ).strip()
    path = tpl.format(mandate_id=gateway_mandate_id)
    if not path.startswith("/"):
        path = "/" + path
    return f"{base}{path}"


def _build_gateway_json_body(
    *,
    amount_cents: int,
    currency: str,
    payer_agent_id: str,
    reason: str,
    idempotency_key: str,
) -> dict[str, Any]:
    tpl = os.environ.get("AP2_GATEWAY_JSON_BODY", "").strip()
    if tpl:
        raw = tpl.format(
            amount_cents=amount_cents,
            currency=currency,
            payer_agent_id=payer_agent_id,
            reason=json.dumps(reason)[1:-1],
            idempotency_key=idempotency_key,
            amount_usd=amount_cents / 100.0,
        )
        return json.loads(raw)
    return {
        "amount_usd": amount_cents / 100.0,
        "amount_cents": amount_cents,
        "currency": currency,
        "reason": reason,
        "payer_agent_id": payer_agent_id,
        "idempotency_key": idempotency_key,
    }


def _parse_gateway_response(data: dict[str, Any]) -> PaymentMandate:
    auth_key = os.environ.get("AP2_RESPONSE_AUTHORIZED_FIELD", "authorized")
    mid_key = os.environ.get("AP2_RESPONSE_MANDATE_ID_FIELD", "mandate_id")
    return PaymentMandate(
        authorized=bool(data.get(auth_key, False)),
        mandate_id=data.get(mid_key) if isinstance(data.get(mid_key), str) else None,
    )


async def _post_gateway_with_retries(
    *,
    url: str,
    headers: dict[str, str],
    body: dict[str, Any],
) -> httpx.Response:
    max_retries = int(os.environ.get("AP2_HTTP_MAX_RETRIES", "3"))
    backoff = float(os.environ.get("AP2_HTTP_RETRY_BACKOFF_SEC", "0.5"))
    last_exc: Exception | None = None
    async with httpx.AsyncClient(timeout=30.0) as client:
        for attempt in range(max_retries):
            try:
                response = await client.post(url, headers=headers, json=body)
                if response.status_code in (429, 500, 502, 503, 504) and attempt + 1 < max_retries:
                    await asyncio.sleep(backoff * (2**attempt))
                    continue
                return response
            except httpx.HTTPError as exc:
                last_exc = exc
                logger.warning("Gateway HTTP error attempt %s: %s", attempt + 1, exc)
                if attempt + 1 < max_retries:
                    await asyncio.sleep(backoff * (2**attempt))
                    continue
                raise
    raise last_exc or RuntimeError("gateway request failed")


async def _mandate_via_gateway(
    *,
    amount_cents: int,
    currency: str,
    reason: str,
    payer_agent_id: str,
    idempotency_key: str,
) -> PaymentMandate:
    if not _gateway_base():
        logger.error("AP2_MODE=live requires AP2_GATEWAY_URL")
        return PaymentMandate(authorized=False, mandate_id=None)

    headers = {"Content-Type": "application/json"}
    tok = _gateway_token()
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    idem_header = os.environ.get("AP2_IDEMPOTENCY_HEADER", "Idempotency-Key").strip()
    if idem_header:
        headers[idem_header] = idempotency_key

    body = _build_gateway_json_body(
        amount_cents=amount_cents,
        currency=currency,
        payer_agent_id=payer_agent_id,
        reason=reason,
        idempotency_key=idempotency_key,
    )
    url = _mandates_url()

    try:
        response = await _post_gateway_with_retries(url=url, headers=headers, body=body)
    except httpx.HTTPError as exc:
        logger.exception("AP2 gateway request failed: %s", exc)
        store._log_event(
            "mandate_gateway_error",
            hiring_agent_id=payer_agent_id,
            amount_cents=amount_cents,
            meta={"error": str(exc)},
        )
        return PaymentMandate(authorized=False, mandate_id=None)

    if response.status_code >= 400:
        logger.warning(
            "AP2 gateway error %s: %s", response.status_code, response.text[:500]
        )
        store._log_event(
            "mandate_gateway_http_error",
            hiring_agent_id=payer_agent_id,
            amount_cents=amount_cents,
            meta={"status": response.status_code, "body": response.text[:2000]},
        )
        return PaymentMandate(authorized=False, mandate_id=None)

    try:
        data = response.json()
    except ValueError:
        logger.warning("AP2 gateway returned non-JSON")
        return PaymentMandate(authorized=False, mandate_id=None)

    if not isinstance(data, dict):
        return PaymentMandate(authorized=False, mandate_id=None)

    return _parse_gateway_response(data)


async def request_mandate(
    amount_usd: float,
    reason: str,
    payer_agent_id: str,
    *,
    idempotency_key: str,
) -> PaymentMandate:
    """Request authorization; *idempotency_key* must be stable per logical verification."""
    cents = int(round(amount_usd * 100))
    currency = _currency()
    store.init_payment_db()
    cached = store.find_authorized_by_idempotency(idempotency_key)
    if cached:
        return PaymentMandate(
            authorized=True,
            mandate_id=cached.get("gateway_mandate_id") or cached.get("id"),
        )

    billing = os.environ.get("AP2_BILLING_MODE", "per_call").lower()
    if billing in ("subscription", "subscription_or_gateway"):
        sub = store.consume_subscription_call(payer_agent_id)
        if sub.get("ok"):
            store.insert_mandate(
                idempotency_key=idempotency_key,
                hiring_agent_id=payer_agent_id,
                amount_cents=cents,
                currency=currency,
                reason=reason,
                status="authorized",
                source="subscription",
                gateway_mandate_id=f"sub:{sub.get('tier_id', 'unknown')}",
                gateway_response_json=json.dumps(
                    {
                        "source": "subscription",
                        "tier_id": sub.get("tier_id"),
                        "remaining_calls": sub.get("remaining_calls"),
                        "period_end_unix": sub.get("period_end_unix"),
                    }
                ),
            )
            return PaymentMandate(
                authorized=True, mandate_id=f"subscription:{sub.get('tier_id', 'unknown')}"
            )
        if billing == "subscription":
            store._log_event(
                "mandate_subscription_denied",
                hiring_agent_id=payer_agent_id,
                amount_cents=cents,
                meta={"reason": sub.get("reason", "unknown")},
            )
            return PaymentMandate(authorized=False, mandate_id=None)

    if billing in ("credits", "credits_or_gateway"):
        if store.try_debit_credits(payer_agent_id, cents):
            store.insert_mandate(
                idempotency_key=idempotency_key,
                hiring_agent_id=payer_agent_id,
                amount_cents=cents,
                currency=currency,
                reason=reason,
                status="authorized",
                source="credits",
                gateway_mandate_id=None,
                gateway_response_json=json.dumps({"source": "prepaid_credits"}),
            )
            return PaymentMandate(authorized=True, mandate_id="credits")
        if billing == "credits":
            store._log_event(
                "mandate_insufficient_credits",
                hiring_agent_id=payer_agent_id,
                amount_cents=cents,
            )
            return PaymentMandate(authorized=False, mandate_id=None)

    mode = os.environ.get("AP2_MODE", "stub").lower()
    if mode == "stub":
        logger.info(
            "AP2 stub mandate: $%.2f for %s (payer=%s)",
            amount_usd,
            reason,
            payer_agent_id,
        )
        persist = os.environ.get("PAYMENTS_PERSIST_STUB", "").strip().lower() in (
            "1",
            "true",
            "yes",
        )
        if persist:
            store.insert_mandate(
                idempotency_key=idempotency_key,
                hiring_agent_id=payer_agent_id,
                amount_cents=cents,
                currency=currency,
                reason=reason,
                status="authorized",
                source="stub",
                gateway_mandate_id="stub-mandate",
                gateway_response_json=json.dumps({"stub": True}),
            )
        return PaymentMandate(authorized=True, mandate_id="stub-mandate")

    if mode == "live":
        result = await _mandate_via_gateway(
            amount_cents=cents,
            currency=currency,
            reason=reason,
            payer_agent_id=payer_agent_id,
            idempotency_key=idempotency_key,
        )
        if result.authorized:
            store.insert_mandate(
                idempotency_key=idempotency_key,
                hiring_agent_id=payer_agent_id,
                amount_cents=cents,
                currency=currency,
                reason=reason,
                status="authorized",
                source="gateway",
                gateway_mandate_id=result.mandate_id,
                gateway_response_json=json.dumps(
                    {"mandate_id": result.mandate_id, "authorized": True}
                ),
            )
        else:
            store._log_event(
                "mandate_denied",
                hiring_agent_id=payer_agent_id,
                amount_cents=cents,
                meta={"gateway_mandate_id": result.mandate_id},
            )
        return result

    logger.warning("Unknown AP2_MODE=%s; denying payment", mode)
    return PaymentMandate(authorized=False, mandate_id=None)


async def handle_payment_handshake(
    hiring_agent_id: str,
    *,
    idempotency_key: str | None = None,
) -> bool:
    """Return True when the hiring agent has paid or prepaid for this verification."""
    import hashlib
    import secrets

    idem = idempotency_key or hashlib.sha256(
        f"{hiring_agent_id}:{secrets.token_hex(16)}".encode()
    ).hexdigest()
    mandate = await request_mandate(
        verification_fee_usd(),
        "Agent Verification Fee",
        hiring_agent_id,
        idempotency_key=idem,
    )
    return mandate.authorized


def apply_webhook_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Sync: gateway callback for settlement / failure (configure webhook URL at PSP)."""
    store.init_payment_db()
    gid = data.get("gateway_mandate_id") or data.get("mandate_id")
    status = data.get("status")
    if not isinstance(gid, str) or not isinstance(status, str):
        return {"ok": False, "error": "gateway_mandate_id and status required"}
    ok = store.update_mandate_by_gateway_id(
        gid, status=status.lower(), meta=data
    )
    store._log_event(
        "webhook_applied",
        reference_id=gid,
        meta={"status": status, "updated": ok},
    )
    return {"ok": True, "updated": ok}


async def request_refund(gateway_mandate_id: str) -> bool:
    """POST refund to gateway; extend body/headers to match your PSP."""
    if not _gateway_base():
        return False
    headers = {"Content-Type": "application/json"}
    tok = _gateway_token()
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    url = _refund_url(gateway_mandate_id)
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                url, headers=headers, json={"mandate_id": gateway_mandate_id}
            )
        except httpx.HTTPError as exc:
            logger.exception("Refund failed: %s", exc)
            return False
    ok = response.status_code < 400
    store._log_event(
        "refund_requested",
        reference_id=gateway_mandate_id,
        meta={"http_status": response.status_code, "ok": ok},
    )
    if ok:
        store.update_mandate_by_gateway_id(
            gateway_mandate_id, status="refunded", meta={"refund_http": response.status_code}
        )
    return ok
