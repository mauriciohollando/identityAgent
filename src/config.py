"""Environment-driven configuration (no extra config framework)."""

from __future__ import annotations

import os
from typing import Final


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def allow_performance_stub() -> bool:
    """Synthetic performance when MCP is unset (dev/demo only).

    When ``AP2_MODE=live``, stubs are **off** unless
    ``TRUST_AUDITOR_ALLOW_PERFORMANCE_STUB=true`` is set explicitly (emergency dev only).
    """
    explicit = os.environ.get("TRUST_AUDITOR_ALLOW_PERFORMANCE_STUB", "").strip().lower()
    if explicit in ("1", "true", "yes"):
        return True
    if explicit in ("0", "false", "no"):
        return False
    mode = os.environ.get("AP2_MODE", "stub").lower()
    return mode != "live"


def list_base_urls(env_list: str, env_single: str | None = None) -> list[str]:
    """Comma-separated bases in *env_list*, else single *env_single* env."""
    raw = os.environ.get(env_list, "").strip()
    out = [x.strip().rstrip("/") for x in raw.split(",") if x.strip()]
    if out:
        return out
    if env_single:
        one = os.environ.get(env_single, "").strip().rstrip("/")
        if one:
            return [one]
    return []


# --- Identity ---
IDENTITY_REGISTRY_QUORUM: Final[str] = os.environ.get(
    "IDENTITY_REGISTRY_QUORUM", "all"
).lower()
# all | any | majority

# --- Performance / MCP ---
PERF_AGGREGATION: Final[str] = os.environ.get("PERF_AGGREGATION", "median").lower()
# median | mean
PERF_SOURCE_DISAGREEMENT_THRESHOLD: Final[float] = _env_float(
    "PERF_SOURCE_DISAGREEMENT_THRESHOLD", 0.25
)
# If max(sr)-min(sr) across live sources exceeds this, flag high_disagreement.

# --- Tiers (standard | enterprise) ---
DEFAULT_VERIFICATION_TIER: Final[str] = os.environ.get(
    "VERIFICATION_TIER", "standard"
).lower()

# --- Anti-abuse ---
RATE_LIMIT_PER_MINUTE: Final[int] = _env_int("RATE_LIMIT_PER_MINUTE", 120)
MIN_SAMPLE_SIZE_STANDARD: Final[int] = _env_int("MIN_SAMPLE_SIZE_STANDARD", 5)
MIN_SAMPLE_SIZE_ENTERPRISE: Final[int] = _env_int("MIN_SAMPLE_SIZE_ENTERPRISE", 30)

# --- AP2 ---
AP2_GATEWAY_URL: Final[str] = os.environ.get("AP2_GATEWAY_URL", "").rstrip("/")
AP2_GATEWAY_TOKEN: Final[str] = os.environ.get("AP2_GATEWAY_TOKEN", "")

# --- Disputes ---
DISPUTES_DB_PATH: Final[str] = os.environ.get(
    "DISPUTES_DB_PATH", "./data/disputes.db"
)

# --- Public ---
DISPUTE_FILING_URL: Final[str] = os.environ.get(
    "DISPUTE_FILING_URL", ""
).strip()  # e.g. https://trust.example.com/v1/disputes
