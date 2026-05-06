import json

import pytest
from starlette.testclient import TestClient

import dev_api


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DISPUTES_DB_PATH", str(tmp_path / "disputes.db"))
    return TestClient(dev_api.app)


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_metrics(client):
    r = client.get("/metrics")
    assert r.status_code == 200
    assert "trust_auditor_identity_checks_total" in r.text


def test_verify_identity(client):
    r = client.post(
        "/v1/verify-identity",
        content=json.dumps({"target_agent_id": "valid-agent-1"}),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["target_agent_id"] == "valid-agent-1"
    assert "identity_valid" in body
    assert "evidence" in body


def test_audit_reputation(client):
    r = client.post(
        "/v1/audit-reputation",
        content=json.dumps(
            {"target_agent_id": "valid-agent-2", "context": "unit-test"}
        ),
    )
    assert r.status_code == 200
    body = r.json()
    assert "trust_score" in body
    assert "verification_token" in body
    assert body["status"] in ("APPROVED", "FLAGGED", "REVIEW_REQUIRED")
    assert "warnings" in body


def test_enterprise_tier_stub_requires_review(client):
    r = client.post(
        "/v1/audit-reputation",
        content=json.dumps({"target_agent_id": "valid-agent-3", "context": "x"}),
        headers={"X-Verification-Tier": "enterprise"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "REVIEW_REQUIRED"
    assert "ENTERPRISE_REQUIRES_LIVE_MCP" in r.json()["warnings"]


def test_create_dispute(client):
    r = client.post(
        "/v1/disputes",
        content=json.dumps(
            {
                "target_agent_id": "agent-x",
                "reason": "score seems wrong",
                "verification_token": "v1.abc",
            }
        ),
    )
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "received"
    assert len(body["dispute_id"]) == 36
