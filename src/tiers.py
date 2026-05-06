"""Verification depth by tier (standard vs enterprise)."""

from __future__ import annotations

from dataclasses import dataclass

from config import DEFAULT_VERIFICATION_TIER
from config import MIN_SAMPLE_SIZE_ENTERPRISE
from config import MIN_SAMPLE_SIZE_STANDARD


@dataclass(frozen=True)
class TierSpec:
    name: str
    min_sample_for_approval: int
    description: str


def resolve_tier(name: str | None) -> TierSpec:
    key = (name or DEFAULT_VERIFICATION_TIER or "standard").lower()
    if key == "enterprise":
        return TierSpec(
            name="enterprise",
            min_sample_for_approval=MIN_SAMPLE_SIZE_ENTERPRISE,
            description="Deeper history requirements; stricter sample floors.",
        )
    return TierSpec(
        name="standard",
        min_sample_for_approval=MIN_SAMPLE_SIZE_STANDARD,
        description="Default verification depth.",
    )
