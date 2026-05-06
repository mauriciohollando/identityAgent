"""Historical performance via one or more MCP-facing HTTP log services."""

from __future__ import annotations

import asyncio
import os
import statistics
from typing import Any

import httpx

from config import PERF_AGGREGATION
from config import list_base_urls
from audit_regimes.anti_abuse import disagreement_detected

DEFAULT_SUCCESS_RATE = 0.72


def _mcp_request_headers() -> dict[str, str]:
    token = os.environ.get("MCP_SERVER_BEARER_TOKEN", "").strip()
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}


async def _fetch_mcp_base(
    client: httpx.AsyncClient, base: str, target_agent_id: str, context: str
) -> dict[str, Any]:
    params = {"context": context} if context else None
    url = f"{base}/v1/agents/{target_agent_id}/transactions"
    try:
        response = await client.get(
            url, params=params, headers=_mcp_request_headers()
        )
        response.raise_for_status()
        payload = response.json()
        sr = float(payload.get("success_rate", DEFAULT_SUCCESS_RATE))
        sr = min(1.0, max(0.0, sr))
        return {
            "base": base,
            "success_rate": sr,
            "sample_size": int(payload.get("sample_size", 0)),
            "ok": True,
        }
    except (httpx.HTTPError, ValueError) as exc:
        return {"base": base, "ok": False, "error": str(exc)}


def _aggregate(success_rates: list[float]) -> float:
    if not success_rates:
        return DEFAULT_SUCCESS_RATE
    if PERF_AGGREGATION == "mean":
        return float(sum(success_rates) / len(success_rates))
    return float(statistics.median(success_rates))


async def get_performance_history(target_agent_id: str, context: str) -> dict[str, Any]:
    """Multi-source MCP aggregation with disagreement detection."""
    bases = list_base_urls("MCP_SERVER_URLS", "MCP_SERVER_BASE_URL")
    if not bases:
        seed = sum(ord(c) for c in target_agent_id) % 17
        success_rate = min(0.95, max(0.35, DEFAULT_SUCCESS_RATE + seed / 100))
        sample = 12 + seed
        return {
            "success_rate": success_rate,
            "sample_size": sample,
            "source": "stub",
            "sources": [
                {
                    "name": "stub",
                    "success_rate": success_rate,
                    "sample_size": sample,
                    "ok": True,
                }
            ],
            "aggregation": "n/a",
            "high_disagreement": False,
            "context": context,
        }

    async with httpx.AsyncClient(timeout=15.0) as client:
        rows = await asyncio.gather(
            *(_fetch_mcp_base(client, b, target_agent_id, context) for b in bases)
        )

    ok_rows = [r for r in rows if r.get("ok")]
    rates = [float(r["success_rate"]) for r in ok_rows]
    sample_size = sum(int(r.get("sample_size") or 0) for r in ok_rows)
    success_rate = _aggregate(rates)
    high = disagreement_detected(rates)

    return {
        "success_rate": success_rate,
        "sample_size": sample_size,
        "source": "mcp",
        "sources": list(rows),
        "aggregation": PERF_AGGREGATION,
        "high_disagreement": high,
        "context": context,
    }
