"""Structured audit evidence for SLAs and dispute handling."""

from __future__ import annotations

import platform
import sys
import time
from typing import Any

from tiers import TierSpec


def build_evidence(
    *,
    tier: TierSpec,
    identity: dict[str, Any],
    performance: dict[str, Any],
    warnings: list[str],
    trust_score: float,
    status: str,
    anti_abuse_notes: list[str],
) -> dict[str, Any]:
    """Return a versioned evidence object suitable for logs and customer export."""
    return {
        "schema": "trust_auditor.evidence.v1",
        "checked_at_unix": int(time.time()),
        "runtime": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
        },
        "tier": {"name": tier.name, "min_sample_for_approval": tier.min_sample_for_approval},
        "identity": {
            "valid": identity.get("valid"),
            "quorum": identity.get("quorum"),
            "sources": identity.get("sources"),
            "trust_tier_max": identity.get("trust_tier_max"),
        },
        "performance": {
            "success_rate": performance.get("success_rate"),
            "sample_size": performance.get("sample_size"),
            "aggregation": performance.get("aggregation"),
            "high_disagreement": performance.get("high_disagreement"),
            "sources": performance.get("sources"),
        },
        "result": {"trust_score": trust_score, "status": status},
        "warnings": warnings,
        "anti_abuse": anti_abuse_notes,
    }
