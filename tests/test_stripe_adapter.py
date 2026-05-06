import json

import httpx
import pytest
from starlette.testclient import TestClient

from stripe_adapter import app as adapter
from stripe_adapter import store as sstore


@pytest.fixture
def stripe_client(tmp_path, monkeypatch):
    monkeypatch.setenv("STRIPE_ADAPTER_DB_PATH", str(tmp_path / "sa.db"))
    monkeypatch.setenv("STRIPE_ADAPTER_CLIENT_TOKEN", "clienttok")
    monkeypatch.setenv("STRIPE_ADAPTER_OPS_TOKEN", "opstok")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_123")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    sstore.init_db()
    return TestClient(adapter.app)


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_mapping_and_mandate_success(stripe_client, monkeypatch):
    mr = stripe_client.post(
        "/v1/admin/mappings",
        headers=_bearer("opstok"),
        content=json.dumps(
            {
                "payer_agent_id": "payer-1",
                "stripe_customer_id": "cus_123",
                "stripe_payment_method_id": "pm_123",
            }
        ),
    )
    assert mr.status_code == 200

    class PI:
        id = "pi_123"
        status = "succeeded"

    monkeypatch.setattr(adapter.stripe.PaymentIntent, "create", lambda **kwargs: PI())

    r = stripe_client.post(
        "/v1/mandates",
        headers=_bearer("clienttok"),
        content=json.dumps(
            {
                "amount_usd": 0.10,
                "currency": "USD",
                "reason": "fee",
                "payer_agent_id": "payer-1",
                "idempotency_key": "idem-1",
            }
        ),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["authorized"] is True
    assert body["status"] == "authorized"
    assert body["stripe_payment_intent_id"] == "pi_123"


def test_mandate_requires_mapping(stripe_client):
    r = stripe_client.post(
        "/v1/mandates",
        headers=_bearer("clienttok"),
        content=json.dumps(
            {
                "amount_usd": 0.10,
                "payer_agent_id": "unknown",
                "idempotency_key": "idem-2",
            }
        ),
    )
    assert r.status_code == 402
    assert r.json()["authorized"] is False


def test_webhook_updates_mandate(stripe_client, monkeypatch):
    sstore.upsert_payer_mapping(
        payer_agent_id="payer-2",
        stripe_customer_id="cus_2",
        stripe_payment_method_id="pm_2",
    )
    mid = sstore.create_mandate(
        idempotency_key="idem-x",
        payer_agent_id="payer-2",
        amount_cents=10,
        currency="USD",
        reason="r",
        status="authorized",
        stripe_payment_intent_id="pi_x",
    )

    monkeypatch.setattr(
        adapter.stripe.Webhook,
        "construct_event",
        lambda payload, sig_header, secret: {
            "type": "payment_intent.succeeded",
            "data": {"object": {"id": "pi_x"}},
        },
    )

    r = stripe_client.post(
        "/v1/stripe/webhook",
        headers={"stripe-signature": "ok"},
        content=b"{}",
    )
    assert r.status_code == 200
    row = sstore.get_mandate(mid)
    assert row is not None
    assert row["status"] == "settled"


def test_invoice_paid_forwards_subscription_sync(stripe_client, monkeypatch):
    monkeypatch.setenv(
        "AUDITOR_WEBHOOK_URL",
        "http://auditor.example/internal/webhooks/payment",
    )
    sstore.upsert_payer_mapping(
        payer_agent_id="sub-payer",
        stripe_customer_id="cus_sub9",
        stripe_payment_method_id="pm_x",
    )
    posted: list[tuple[str, dict]] = []

    class FakeClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def post(self, url, content=None, headers=None):
            posted.append((url, json.loads(content.decode())))
            return httpx.Response(200, json={"ok": True})

    monkeypatch.setattr(adapter.httpx, "AsyncClient", lambda **kwargs: FakeClient())

    def fake_retrieve(sid, *args, **kwargs):
        return {
            "id": sid,
            "status": "active",
            "customer": "cus_sub9",
            "current_period_start": 1_700_000_000,
            "current_period_end": 1_700_086_400,
            "metadata": {"tier_id": "starter"},
            "items": {"data": []},
        }

    monkeypatch.setattr(adapter.stripe.Subscription, "retrieve", fake_retrieve)

    monkeypatch.setattr(
        adapter.stripe.Webhook,
        "construct_event",
        lambda payload, sig_header, secret: {
            "type": "invoice.paid",
            "data": {
                "object": {
                    "id": "in_test",
                    "customer": "cus_sub9",
                    "subscription": "sub_test1",
                }
            },
        },
    )

    r = stripe_client.post(
        "/v1/stripe/webhook",
        headers={"stripe-signature": "sig"},
        content=b"{}",
    )
    assert r.status_code == 200
    assert len(posted) == 1
    assert posted[0][0] == "http://auditor.example/internal/webhooks/subscription-sync"
    assert posted[0][1]["hiring_agent_id"] == "sub-payer"
    assert posted[0][1]["tier_id"] == "starter"
    assert posted[0][1]["reset_used_calls"] is True


def test_subscription_prices_catalog(stripe_client, monkeypatch):
    monkeypatch.setenv(
        "STRIPE_PRICE_TO_TIER_JSON",
        '{"price_b":"growth","price_a":"starter"}',
    )
    r = stripe_client.get("/v1/subscription/prices", headers=_bearer("opstok"))
    assert r.status_code == 200
    assert r.json()["tiers"] == {"starter": "price_a", "growth": "price_b"}


def test_checkout_session(stripe_client, monkeypatch):
    monkeypatch.setenv(
        "STRIPE_PRICE_TO_TIER_JSON",
        '{"price_x":"starter"}',
    )
    sstore.upsert_payer_mapping(
        payer_agent_id="buyer-a",
        stripe_customer_id="cus_a",
        stripe_payment_method_id=None,
    )

    class CS:
        id = "cs_test_1"
        url = "https://checkout.stripe.test/c/pay/cs_test_1"

    monkeypatch.setattr(adapter.stripe.checkout.Session, "create", lambda **kw: CS())

    r = stripe_client.post(
        "/v1/checkout/sessions",
        headers=_bearer("opstok"),
        content=json.dumps(
            {
                "payer_agent_id": "buyer-a",
                "tier_id": "starter",
                "success_url": "https://app.example/success?session_id={CHECKOUT_SESSION_ID}",
                "cancel_url": "https://app.example/cancel",
            }
        ),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["checkout_session_id"] == "cs_test_1"
    assert body["checkout_url"].startswith("https://checkout.stripe.test/")


def test_billing_portal_session(stripe_client, monkeypatch):
    sstore.upsert_payer_mapping(
        payer_agent_id="buyer-b",
        stripe_customer_id="cus_b",
        stripe_payment_method_id=None,
    )

    class PS:
        url = "https://billing.stripe.test/session/ps_1"

    monkeypatch.setattr(adapter.stripe.billing_portal.Session, "create", lambda **kw: PS())

    r = stripe_client.post(
        "/v1/billing/portal-sessions",
        headers=_bearer("opstok"),
        content=json.dumps(
            {
                "payer_agent_id": "buyer-b",
                "return_url": "https://app.example/account",
            }
        ),
    )
    assert r.status_code == 200
    assert r.json()["portal_url"].startswith("https://billing.stripe.test/")
