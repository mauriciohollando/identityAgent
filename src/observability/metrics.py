"""Minimal Prometheus text exposition (no extra dependencies)."""

from __future__ import annotations

import threading

_lock = threading.Lock()
_identity_checks = 0
_full_verifications = 0
_rate_limited = 0


def inc_identity_check() -> None:
    global _identity_checks
    with _lock:
        _identity_checks += 1


def inc_verification() -> None:
    global _full_verifications
    with _lock:
        _full_verifications += 1


def inc_rate_limited() -> None:
    global _rate_limited
    with _lock:
        _rate_limited += 1


def render_prometheus() -> str:
    with _lock:
        ic, fv, rl = _identity_checks, _full_verifications, _rate_limited
    lines = [
        "# HELP trust_auditor_identity_checks_total Identity tool invocations.",
        "# TYPE trust_auditor_identity_checks_total counter",
        f"trust_auditor_identity_checks_total {ic}",
        "# HELP trust_auditor_full_verifications_total Full reputation audits.",
        "# TYPE trust_auditor_full_verifications_total counter",
        f"trust_auditor_full_verifications_total {fv}",
        "# HELP trust_auditor_rate_limited_total Rejected requests (rate limit).",
        "# TYPE trust_auditor_rate_limited_total counter",
        f"trust_auditor_rate_limited_total {rl}",
        "",
    ]
    return "\n".join(lines)
