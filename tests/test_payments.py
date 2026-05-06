import pytest

from payments import handle_payment_handshake


@pytest.mark.asyncio
async def test_stub_payment_always_authorized(monkeypatch):
    monkeypatch.setenv("AP2_MODE", "stub")
    assert await handle_payment_handshake("hiring-1") is True


@pytest.mark.asyncio
async def test_unknown_mode_denies(monkeypatch):
    monkeypatch.setenv("AP2_MODE", "invalid")
    assert await handle_payment_handshake("hiring-1") is False
