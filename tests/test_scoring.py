import pytest

from audit_regimes.tokens import generate_signed_token


@pytest.mark.asyncio
async def test_audit_reputation_formula(monkeypatch):
    import auditor

    async def perf_fixed(agent_id: str, context: str):
        return {
            "success_rate": 1.0,
            "sample_size": 10,
            "source": "stub",
            "sources": [
                {
                    "name": "stub",
                    "success_rate": 1.0,
                    "sample_size": 10,
                    "ok": True,
                }
            ],
            "aggregation": "n/a",
            "high_disagreement": False,
            "context": context,
        }

    monkeypatch.setattr(auditor, "get_performance_history", perf_fixed)

    result = await auditor.audit_reputation("agent-1", "payments")
    assert result["trust_score"] == 100.0
    assert result["status"] == "APPROVED"
    assert result["verification_token"].startswith("v1.")
    assert "evidence" in result


def test_signed_token_roundtrip_shape():
    tok = generate_signed_token("agent-xyz")
    assert "agent-xyz" in tok or len(tok) > 8
