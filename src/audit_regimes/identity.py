"""Cryptographic and registry-backed identity checks (multi-registry)."""

from __future__ import annotations

import asyncio
import os
import re
from typing import Any, Final

import httpx

from config import IDENTITY_REGISTRY_QUORUM
from config import list_base_urls

_AGENT_ID_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^[a-zA-Z0-9][a-zA-Z0-9._:-]{1,255}$"
)

# Registry trust_tier ordering (see docs/GO_TO_MARKET_IDENTITY.md).
TIER_RANK: Final[dict[str, int]] = {
    "registered": 0,
    "operator_verified": 1,
    "partner_attested": 2,
}


def _max_trust_tier_from_sources(sources: list[dict[str, Any]]) -> str | None:
    best: str | None = None
    best_rank = -1
    for s in sources:
        raw = s.get("raw")
        tier: str | None = None
        if isinstance(raw, dict):
            t = raw.get("trust_tier")
            if isinstance(t, str):
                tier = t
        if tier is None and s.get("registered"):
            tier = "registered"
        if not isinstance(tier, str):
            continue
        r = TIER_RANK.get(tier, -1)
        if r > best_rank:
            best_rank = r
            best = tier
    return best


def _registry_headers() -> dict[str, str]:
    token = os.environ.get("IDENTITY_REGISTRY_BEARER_TOKEN", "").strip()
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}


async def _fetch_registry(
    client: httpx.AsyncClient, base: str, target_agent_id: str
) -> dict[str, Any]:
    url = f"{base}/agents/{target_agent_id}/status"
    try:
        response = await client.get(url, headers=_registry_headers())
        if response.status_code != 200:
            return {
                "base": base,
                "registered": False,
                "http_status": response.status_code,
            }
        data = response.json()
        return {
            "base": base,
            "registered": bool(data.get("registered", False)),
            "raw": data,
        }
    except (httpx.HTTPError, ValueError) as exc:
        return {"base": base, "registered": False, "error": str(exc)}


def _quorum(results: list[bool], mode: str) -> bool:
    if not results:
        return False
    if mode == "any":
        return any(results)
    if mode == "majority":
        return sum(1 for r in results if r) > len(results) / 2
    # default: all
    return all(results)


async def verify_identity_full(target_agent_id: str) -> dict[str, Any]:
    """Structured identity result for evidence and ``valid`` for scoring."""
    if not target_agent_id or not _AGENT_ID_PATTERN.match(target_agent_id):
        return {
            "valid": False,
            "quorum": IDENTITY_REGISTRY_QUORUM,
            "sources": [],
            "registry_required": False,
            "trust_tier_max": None,
        }

    bases = list_base_urls("IDENTITY_REGISTRY_URLS", "IDENTITY_REGISTRY_URL")
    if not bases:
        return {
            "valid": True,
            "quorum": "n/a",
            "sources": [{"name": "format_only", "registered": True}],
            "registry_required": False,
            "trust_tier_max": None,
        }

    async with httpx.AsyncClient(timeout=10.0) as client:
        resolved = list(
            await asyncio.gather(
                *(_fetch_registry(client, b, target_agent_id) for b in bases)
            )
        )

    registered_flags = [bool(r.get("registered")) for r in resolved]
    valid = _quorum(registered_flags, IDENTITY_REGISTRY_QUORUM)
    return {
        "valid": valid,
        "quorum": IDENTITY_REGISTRY_QUORUM,
        "sources": resolved,
        "registry_required": True,
        "trust_tier_max": _max_trust_tier_from_sources(resolved),
    }


async def verify_identity_cryptographic(target_agent_id: str) -> bool:
    """Backward-compatible boolean."""
    full = await verify_identity_full(target_agent_id)
    return bool(full.get("valid"))
