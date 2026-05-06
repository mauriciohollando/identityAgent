import hashlib
import hmac
import json
import time
import httpx
import pytest
from starlette.testclient import TestClient

import payment_store as store
from payment_routes import payment_internal_routes
from starlette.applications import Starlette


@pytest.fixture
def pay_app(tmp_path, monkeypatch):
    monkeypatch.setenv("PAYMENT_LEDGER_DB_PATH", str(tmp_path / "pay.db"))
    monkeypatch.setenv("PAYMENT_OPS_API_KEY", "ops")
    monkeypatch.setenv("PAYMENT_WEBHOOK_SECRET", "whsec")
    store.init_payment_db()
    return Starlette(routes=payment_internal_routes())


@pytest.fixture
def pay_client(pay_app):
    return TestClient(pay_app)


@pytest.mark.asyncio
async def test_stub_idempotency_persist(monkeypatch, tmp_path):
    monkeypatch.setenv("PAYMENT_LEDGER_DB_PATH", str(tmp_path / "p.db"))
    monkeypatch.setenv("AP2_MODE", "stub")
    monkeypatch.setenv("PAYMENTS_PERSIST_STUB", "true")
    store.init_payment_db()
    import payments

    idem = "same-key"
    assert await payments.handle_payment_handshake("h1", idempotency_key=idem) is True
    assert await payments.handle_payment_handshake("h1", idempotency_key=idem) is True
    with store._connect() as conn:
        n = conn.execute("SELECT COUNT(*) FROM mandates").fetchone()[0]
    assert n == 1


@pytest.mark.asyncio
async def test_credits_billing(monkeypatch, tmp_path):
    monkeypatch.setenv("PAYMENT_LEDGER_DB_PATH", str(tmp_path / "c.db"))
    monkeypatch.setenv("AP2_MODE", "stub")
    monkeypatch.setenv("AP2_BILLING_MODE", "credits")
    monkeypatch.setenv("VERIFICATION_FEE_USD", "0.10")
    store.init_payment_db()
    store.add_credits("buyer", 50, note="test")
    import payments

    assert await payments.handle_payment_handshake(
        "buyer", idempotency_key="a"
    ) is True
    assert store.get_credit_balance("buyer") == 40
    assert await payments.handle_payment_handshake(
        "buyer", idempotency_key="a"
    ) is True
    assert store.get_credit_balance("buyer") == 40


@pytest.mark.asyncio
async def test_live_gateway_success(monkeypatch, tmp_path):
    monkeypatch.setenv("PAYMENT_LEDGER_DB_PATH", str(tmp_path / "l.db"))
    monkeypatch.setenv("AP2_MODE", "live")
    monkeypatch.setenv("AP2_GATEWAY_URL", "https://gw.example")
    store.init_payment_db()
    import payments

    async def fake_post(**kwargs):
        return httpx.Response(200, json={"authorized": True, "mandate_id": "m-1"})

    monkeypatch.setattr(payments, "_post_gateway_with_retries", fake_post)
    m = await payments.request_mandate(
        0.1,
        "fee",
        "payer",
        idempotency_key="idem-1",
    )
    assert m.authorized and m.mandate_id == "m-1"
    row = store.find_authorized_by_idempotency("idem-1")
    assert row is not None
    assert row["gateway_mandate_id"] == "m-1"


def test_ops_summary_and_credits(pay_client):
    r = pay_client.get("/internal/payments/summary")
    assert r.status_code == 403
    ok = pay_client.post(
        "/internal/payments/credits",
        headers={"Authorization": "Bearer ops"},
        content=json.dumps({"hiring_agent_id": "z", "amount_cents": 500}),
    )
    assert ok.status_code == 200
    assert ok.json()["balance_cents"] == 500


def test_webhook_signature(pay_client):
    body = json.dumps(
        {"gateway_mandate_id": "m-ext", "status": "settled"}
    ).encode()
    sig = hmac.new(b"whsec", body, hashlib.sha256).hexdigest()
    store.init_payment_db()
    store.insert_mandate(
        idempotency_key="k1",
        hiring_agent_id="h",
        amount_cents=10,
        currency="USD",
        reason="r",
        status="authorized",
        source="gateway",
        gateway_mandate_id="m-ext",
    )
    r = pay_client.post(
        "/internal/webhooks/payment",
        content=body,
        headers={"X-Payment-Signature": sig},
    )
    assert r.status_code == 200


def test_subscription_sync_webhook(pay_client, monkeypatch):
    monkeypatch.setenv(
        "AP2_SUBSCRIPTION_TIERS_JSON",
        json.dumps({"starter": {"included_calls": 10, "period_days": 30}}),
    )
    payload = {
        "hiring_agent_id": "buyer-x",
        "tier_id": "starter",
        "period_start_unix": 1000,
        "period_end_unix": 2000,
        "status": "active",
        "reset_used_calls": True,
        "stripe": {"event_type": "invoice.paid"},
    }
    raw = json.dumps(payload).encode()
    sig = hmac.new(b"whsec", raw, hashlib.sha256).hexdigest()
    r = pay_client.post(
        "/internal/webhooks/subscription-sync",
        content=raw,
        headers={"X-Payment-Signature": sig},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    ent = body["entitlement"]
    assert ent["hiring_agent_id"] == "buyer-x"
    assert ent["included_calls"] == 10
    assert ent["used_calls"] == 0


@pytest.mark.asyncio
async def test_subscription_billing(monkeypatch, tmp_path):
    monkeypatch.setenv("PAYMENT_LEDGER_DB_PATH", str(tmp_path / "s.db"))
    monkeypatch.setenv("AP2_MODE", "stub")
    monkeypatch.setenv("AP2_BILLING_MODE", "subscription")
    monkeypatch.setenv("VERIFICATION_FEE_USD", "0.10")
    store.init_payment_db()
    now = int(time.time())
    store.upsert_subscription_entitlement(
        hiring_agent_id="sub-buyer",
        tier_id="starter",
        included_calls=2,
        used_calls=0,
        period_start_unix=now - 100,
        period_end_unix=now + 3600,
        status="active",
    )
    import payments

    assert await payments.handle_payment_handshake("sub-buyer", idempotency_key="s1") is True
    assert await payments.handle_payment_handshake("sub-buyer", idempotency_key="s2") is True
    assert await payments.handle_payment_handshake("sub-buyer", idempotency_key="s3") is False
    ent = store.get_subscription_entitlement("sub-buyer")
    assert ent is not None
    assert ent["used_calls"] == 2
    assert ent["remaining_calls"] == 0


def test_subscription_routes(pay_client):
    grant = pay_client.post(
        "/internal/payments/subscriptions/grant",
        headers={"Authorization": "Bearer ops"},
        content=json.dumps(
            {
                "hiring_agent_id": "team-a",
                "tier_id": "starter",
                "included_calls": 100,
                "period_days": 30,
            }
        ),
    )
    assert grant.status_code == 200
    get_one = pay_client.get(
        "/internal/payments/subscriptions/team-a",
        headers={"Authorization": "Bearer ops"},
    )
    assert get_one.status_code == 200
    payload = get_one.json()
    assert payload["hiring_agent_id"] == "team-a"
    assert payload["tier_id"] == "starter"
    assert payload["included_calls"] == 100
