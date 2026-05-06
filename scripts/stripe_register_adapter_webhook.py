#!/usr/bin/env python3
"""Create or update a Stripe webhook endpoint for the stripe_adapter service.

Uses STRIPE_SECRET_KEY from the environment (e.g. export from Secret Manager).

Example:
  export STRIPE_SECRET_KEY=$(gcloud secrets versions access latest --secret=STRIPE_SECRET_KEY --project=YOUR_PROJECT)
  python scripts/stripe_register_adapter_webhook.py \\
    --url https://your-adapter.run.app/v1/stripe/webhook

On first create, Stripe prints a signing secret (whsec_...). Store it in Secret Manager
as STRIPE_WEBHOOK_SECRET for the adapter. Updates to an existing endpoint keep the same secret.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import stripe

# Events handled by src/stripe_adapter/app.py stripe_webhook
DEFAULT_EVENTS = [
    "payment_intent.succeeded",
    "payment_intent.payment_failed",
    "payment_intent.canceled",
    "charge.refunded",
    "invoice.paid",
    "customer.subscription.updated",
    "customer.subscription.deleted",
]


def _norm_url(url: str) -> str:
    u = url.strip().rstrip("/")
    if not u.endswith("/v1/stripe/webhook"):
        u = f"{u}/v1/stripe/webhook"
    return u


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--url",
        default="",
        help="Adapter base URL or full webhook URL (…/v1/stripe/webhook); required unless --list-prices",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned actions only",
    )
    ap.add_argument(
        "--list-prices",
        action="store_true",
        help="List active recurring prices (for STRIPE_PRICE_TO_TIER_JSON); no webhook changes",
    )
    args = ap.parse_args()

    if args.dry_run:
        if not args.url.strip():
            print("--url is required for --dry-run", file=sys.stderr)
            return 2
        print(f"Would ensure webhook: {_norm_url(args.url)}")
        print("Events:", ", ".join(DEFAULT_EVENTS))
        return 0

    key = os.environ.get("STRIPE_SECRET_KEY", "").strip()
    if not key:
        print("STRIPE_SECRET_KEY is not set", file=sys.stderr)
        return 1

    stripe.api_key = key

    if args.list_prices:
        prices = stripe.Price.list(active=True, limit=100)
        rows = []
        for p in prices.auto_paging_iter():
            if getattr(p, "recurring", None):
                rows.append(
                    {
                        "id": p.id,
                        "nickname": getattr(p, "nickname", None) or "",
                        "product": getattr(p, "product", None),
                        "unit_amount": p.unit_amount,
                        "currency": p.currency,
                    }
                )
        print(json.dumps(rows, indent=2))
        print(
            "\nBuild STRIPE_PRICE_TO_TIER_JSON mapping price_… ids to starter|growth|scale.",
            file=sys.stderr,
        )
        return 0

    if not args.url.strip():
        print("--url is required", file=sys.stderr)
        return 2

    target = _norm_url(args.url)

    existing_id = None
    for we in stripe.WebhookEndpoint.list(limit=100).auto_paging_iter():
        if (we.url or "").rstrip("/") == target:
            existing_id = we.id
            break

    if existing_id:
        stripe.WebhookEndpoint.modify(existing_id, enabled_events=DEFAULT_EVENTS)
        print(f"Updated webhook endpoint {existing_id} ({target})")
        print("Signing secret unchanged — keep existing STRIPE_WEBHOOK_SECRET.")
        return 0

    created = stripe.WebhookEndpoint.create(
        url=target,
        enabled_events=DEFAULT_EVENTS,
        description="identityAgent stripe_adapter (mandates + subscription sync)",
    )
    secret = getattr(created, "secret", None) or ""
    print(f"Created webhook endpoint {created.id} ({target})")
    if secret:
        print("Set STRIPE_WEBHOOK_SECRET in Secret Manager to:")
        print(secret)
    else:
        print("Retrieve signing secret from Stripe Dashboard → Webhooks → this endpoint.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
