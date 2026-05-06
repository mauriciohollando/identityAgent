import json

import pytest
from starlette.testclient import TestClient

from identity_registry import app as reg_app
from identity_registry.store import get_status_payload
from identity_registry.store import init_db


@pytest.fixture
def reg_client(tmp_path, monkeypatch):
    monkeypatch.setenv("IDENTITY_REGISTRY_DB_PATH", str(tmp_path / "reg.db"))
    init_db()
    return TestClient(reg_app.app)


def test_health(reg_client):
    assert reg_client.get("/health").status_code == 200


def test_unknown_agent_status(reg_client):
    r = reg_client.get("/agents/nope/status")
    assert r.status_code == 404
    assert r.json()["registered"] is False


def test_register_status_and_key(reg_client):
    r = reg_client.post(
        "/v1/agents",
        content=json.dumps(
            {
                "agent_id": "acme-agent-1",
                "operator_name": "ACME",
                "operator_contact": "ops@acme.example",
                "kyc_verified": True,
                "public_key": "-----BEGIN PUBLIC KEY-----\nMIIB\n-----END PUBLIC KEY-----",
                "algorithm": "RSA",
            }
        ),
    )
    assert r.status_code == 201
    body = r.json()
    assert body["registered"] is True
    assert body["trust_tier"] == "registered"
    assert body["active_key_count"] == 1

    r2 = reg_client.get("/agents/acme-agent-1/status")
    assert r2.status_code == 200
    assert r2.json()["registered"] is True


def test_suspend_and_revoke(reg_client):
    reg_client.post(
        "/v1/agents",
        content=json.dumps({"agent_id": "x1", "public_key": "pk"}),
    )
    reg_client.post("/v1/agents/x1/suspend")
    assert get_status_payload("x1")["registered"] is False
    reg_client.post("/v1/agents/x1/activate")
    assert get_status_payload("x1")["registered"] is True
    reg_client.post("/v1/agents/x1/revoke")
    assert get_status_payload("x1")["registered"] is False


def test_require_kyc(monkeypatch, reg_client):
    monkeypatch.setenv("REGISTRY_REQUIRE_KYC", "1")
    reg_client.post(
        "/v1/agents",
        content=json.dumps({"agent_id": "k1", "kyc_verified": False}),
    )
    st = get_status_payload("k1")
    assert st["registered"] is False
    assert "KYC_REQUIRED" in st["flags"]


def test_registry_auth(reg_client, monkeypatch):
    monkeypatch.setenv("REGISTRY_SERVICE_API_KEY", "rsecret")
    assert reg_client.get("/agents/x/status").status_code == 401
    ok = reg_client.get(
        "/agents/x/status",
        headers={"Authorization": "Bearer rsecret"},
    )
    assert ok.status_code == 404


def test_operator_attest(reg_client, monkeypatch):
    monkeypatch.setenv("REGISTRY_ADMIN_API_KEY", "adminsekrit")
    reg_client.post(
        "/v1/agents",
        content=json.dumps({"agent_id": "vip1", "public_key": "k"}),
    )
    r = reg_client.post(
        "/v1/admin/agents/vip1/attest/operator",
        content=json.dumps({"attestor": "reviewer@example.com", "notes": "KYB ok"}),
        headers={"Authorization": "Bearer adminsekrit"},
    )
    assert r.status_code == 200
    assert r.json()["trust_tier"] == "operator_verified"
    assert r.json()["attestor"] == "reviewer@example.com"


def test_partner_attest(reg_client, monkeypatch):
    monkeypatch.setenv("PARTNER_ATTESTATION_TOKEN", "parttok")
    reg_client.post(
        "/v1/agents",
        content=json.dumps({"agent_id": "p1", "public_key": "k"}),
    )
    r = reg_client.post(
        "/v1/partner/v1/agents/p1/attest",
        content=json.dumps(
            {
                "partner_id": "marketplace-alpha",
                "partner_ref": "acct_01JQ",
                "attestor": "partner-webhook",
            }
        ),
        headers={"X-Partner-Attestation-Token": "parttok"},
    )
    assert r.status_code == 200
    assert r.json()["trust_tier"] == "partner_attested"
    assert r.json()["partner_id"] == "marketplace-alpha"


@pytest.mark.asyncio
async def test_auditor_trust_tier_max_in_evidence(monkeypatch):
    import auditor

    async def fake_full(agent_id: str):
        return {
            "valid": True,
            "quorum": "all",
            "registry_required": True,
            "trust_tier_max": "operator_verified",
            "sources": [
                {
                    "base": "http://mock",
                    "registered": True,
                    "raw": {"trust_tier": "operator_verified", "registered": True},
                }
            ],
        }

    monkeypatch.setattr(auditor, "verify_identity_full", fake_full)
    out = await auditor.verify_identity("any-id")
    assert out["evidence"]["identity"]["trust_tier_max"] == "operator_verified"
