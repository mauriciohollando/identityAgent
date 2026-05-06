import json
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from transaction_log import app as log_app
from transaction_log.store import aggregate_for_agent
from transaction_log.store import init_db
from transaction_log.store import insert_event


@pytest.fixture
def log_client(tmp_path, monkeypatch):
    monkeypatch.setenv("TRANSACTION_LOG_DB_PATH", str(tmp_path / "tl.db"))
    init_db()
    return TestClient(log_app.app)


def test_health(log_client):
    r = log_client.get("/health")
    assert r.status_code == 200


def test_ingest_and_aggregate(log_client):
    aid = "agent-demo"
    for _ in range(7):
        r = log_client.post(
            f"/v1/agents/{aid}/transactions",
            content=json.dumps({"outcome": "success", "context": "pay"}),
        )
        assert r.status_code == 201
    for _ in range(3):
        r = log_client.post(
            f"/v1/agents/{aid}/transactions",
            content=json.dumps({"outcome": "failure", "context": "pay"}),
        )
        assert r.status_code == 201

    r = log_client.get(f"/v1/agents/{aid}/transactions?context=pay")
    assert r.status_code == 200
    body = r.json()
    assert body["sample_size"] == 10
    assert body["success_rate"] == 0.7
    assert body["breakdown"]["success"] == 7
    assert body["breakdown"]["failure"] == 3


def test_disputed_excluded_from_rate_denominator(tmp_path, monkeypatch):
    monkeypatch.setenv("TRANSACTION_LOG_DB_PATH", str(tmp_path / "tl2.db"))
    init_db()
    insert_event(agent_id="a1", outcome="success", context="")
    insert_event(agent_id="a1", outcome="disputed", context="")
    insert_event(agent_id="a1", outcome="failure", context="")
    agg = aggregate_for_agent("a1")
    assert agg["sample_size"] == 2
    assert agg["success_rate"] == 0.5


def test_auth_rejects_without_bearer(log_client, monkeypatch):
    monkeypatch.setenv("LOG_SERVICE_API_KEY", "secret")
    r = log_client.get("/v1/agents/x/transactions")
    assert r.status_code == 401
    r = log_client.get(
        "/v1/agents/x/transactions",
        headers={"Authorization": "Bearer secret"},
    )
    assert r.status_code == 200
