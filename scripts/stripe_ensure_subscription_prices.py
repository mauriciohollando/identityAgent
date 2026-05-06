#!/usr/bin/env python3
"""Create Stripe Products + monthly Prices for auditor tiers (starter, growth, scale).

Idempotent: matches existing products via metadata `identity_agent_tier`. Re-run safe.

Uses STRIPE_SECRET_KEY from the environment.

Example:
  export STRIPE_SECRET_KEY=$(gcloud secrets versions access latest --secret=STRIPE_SECRET_KEY --project=YOUR_PROJECT)
  python scripts/stripe_ensure_subscription_prices.py
  python scripts/stripe_ensure_subscription_prices.py --json-only   # print STRIPE_PRICE_TO_TIER_JSON only

Default monthly amounts (USD cents): starter=4900, growth=19900, scale=49900.
Override: --starter-cents 2900 --growth-cents 9900 --scale-cents 29900
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import stripe

TIER_ORDER = ("starter", "growth", "scale")


def _ensure_tier(
    tier: str,
    amount_cents: int,
    *,
    dry_run: bool,
) -> tuple[str, str]:
    """Return (product_id, price_id)."""
    if dry_run:
        return (f"prod_{tier}_dry", f"price_{tier}_dry")

    products = list(stripe.Product.list(active=True, limit=100).auto_paging_iter())

    def _meta_tier(p: stripe.Product) -> str | None:
        m = getattr(p, "metadata", None)
        if not m:
            return None
        v = m.get("identity_agent_tier") if isinstance(m, dict) else getattr(m, "identity_agent_tier", None)
        return str(v) if v else None

    prod = next((p for p in products if _meta_tier(p) == tier), None)
    if not prod:
        prod = stripe.Product.create(
            name=f"Verification subscription — {tier}",
            metadata={"identity_agent_tier": tier},
        )

    prices = stripe.Price.list(product=prod.id, active=True, limit=20).data
    monthly = next(
        (
            pr
            for pr in prices
            if pr.recurring
            and getattr(pr.recurring, "interval", None) == "month"
            and pr.currency == "usd"
        ),
        None,
    )
    if not monthly:
        monthly = stripe.Price.create(
            product=prod.id,
            unit_amount=amount_cents,
            currency="usd",
            recurring={"interval": "month"},
            metadata={"identity_agent_tier": tier},
        )
    return prod.id, monthly.id


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--starter-cents", type=int, default=4900)
    ap.add_argument("--growth-cents", type=int, default=19900)
    ap.add_argument("--scale-cents", type=int, default=49900)
    ap.add_argument(
        "--json-only",
        action="store_true",
        help="Print only STRIPE_PRICE_TO_TIER_JSON (one line)",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not call Stripe; print placeholder mapping",
    )
    args = ap.parse_args()

    amounts = {
        "starter": args.starter_cents,
        "growth": args.growth_cents,
        "scale": args.scale_cents,
    }

    key = os.environ.get("STRIPE_SECRET_KEY", "").strip()
    if not key and not args.dry_run:
        print("STRIPE_SECRET_KEY is not set", file=sys.stderr)
        return 1
    if key:
        stripe.api_key = key

    mapping: dict[str, str] = {}
    report: list[dict[str, str]] = []
    for tier in TIER_ORDER:
        pid, price_id = _ensure_tier(tier, amounts[tier], dry_run=args.dry_run)
        mapping[price_id] = tier
        report.append(
            {"tier": tier, "product_id": pid, "price_id": price_id, "usd_cents": str(amounts[tier])}
        )

    tier_json = json.dumps(mapping, separators=(",", ":"))

    if args.json_only:
        print(tier_json)
        return 0

    print(json.dumps(report, indent=2))
    print(
        "\nCloud Run: gcloud commas break --update-env-vars; store as Secret Manager "
        "secret STRIPE_PRICE_TO_TIER_JSON and use --update-secrets "
        "STRIPE_PRICE_TO_TIER_JSON=STRIPE_PRICE_TO_TIER_JSON:latest",
        file=sys.stderr,
    )
    print(f"STRIPE_PRICE_TO_TIER_JSON={tier_json}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
