"""Lightweight risk signals (not a substitute for fraud systems at scale)."""

from __future__ import annotations

from typing import Any

from config import PERF_SOURCE_DISAGREEMENT_THRESHOLD
from tiers import TierSpec


def collect_performance_warnings(perf: dict[str, Any]) -> list[str]:
    """Return machine-readable warning codes from aggregated performance."""
    warnings: list[str] = []
    if perf.get("source") == "unavailable":
        warnings.append("NO_PERFORMANCE_DATA")
    if perf.get("high_disagreement"):
        warnings.append("HIGH_SOURCE_DISAGREEMENT")
    for src in perf.get("sources") or []:
        if isinstance(src, dict) and src.get("error"):
            warnings.append("SOURCE_UNAVAILABLE")
            break
    if perf.get("source") == "stub":
        warnings.append("STUB_PERFORMANCE_DATA")
    return warnings


def collect_identity_warnings(identity: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    if identity.get("registry_required") and not identity.get("sources"):
        warnings.append("NO_REGISTRY_CONFIGURED")
    for src in identity.get("sources") or []:
        if isinstance(src, dict) and src.get("error"):
            warnings.append("IDENTITY_SOURCE_ERROR")
    return warnings


def tier_sample_warnings(perf: dict[str, Any], tier: TierSpec) -> list[str]:
    src = perf.get("source")
    if tier.name == "enterprise" and src == "stub":
        return ["ENTERPRISE_REQUIRES_LIVE_MCP"]
    n = int(perf.get("sample_size") or 0)
    if src == "unavailable":
        return ["INSUFFICIENT_SAMPLE_FOR_TIER"]
    if n < tier.min_sample_for_approval and src != "stub":
        return ["INSUFFICIENT_SAMPLE_FOR_TIER"]
    if n < tier.min_sample_for_approval and src == "stub":
        return ["STUB_PERFORMANCE_DATA"]
    return []


def disagreement_detected(success_rates: list[float]) -> bool:
    if len(success_rates) < 2:
        return False
    lo, hi = min(success_rates), max(success_rates)
    return (hi - lo) > PERF_SOURCE_DISAGREEMENT_THRESHOLD
