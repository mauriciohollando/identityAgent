#!/usr/bin/env bash
set -euo pipefail

# Creates/updates required secrets for Stripe adapter service.
#
# Required env:
#   PROJECT_ID

req() {
  local v="$1"
  if [[ -z "${!v:-}" ]]; then
    echo "Missing required env var: $v" >&2
    exit 1
  fi
}

req PROJECT_ID

upsert_secret() {
  local name="$1"
  local value="$2"
  if gcloud secrets describe "${name}" --project "${PROJECT_ID}" >/dev/null 2>&1; then
    printf '%s' "${value}" | gcloud secrets versions add "${name}" \
      --project "${PROJECT_ID}" \
      --data-file=-
  else
    printf '%s' "${value}" | gcloud secrets create "${name}" \
      --project "${PROJECT_ID}" \
      --replication-policy=automatic \
      --data-file=-
  fi
}

read -r -s -p "STRIPE_SECRET_KEY: " STRIPE_SECRET_KEY
echo
read -r -s -p "STRIPE_WEBHOOK_SECRET: " STRIPE_WEBHOOK_SECRET
echo
read -r -s -p "STRIPE_ADAPTER_CLIENT_TOKEN (shared with auditor AP2_GATEWAY_TOKEN): " STRIPE_ADAPTER_CLIENT_TOKEN
echo
read -r -s -p "STRIPE_ADAPTER_OPS_TOKEN: " STRIPE_ADAPTER_OPS_TOKEN
echo
read -r -s -p "PAYMENT_WEBHOOK_SECRET (must match auditor; signs subscription-sync): " PAYMENT_WEBHOOK_SECRET
echo

upsert_secret "STRIPE_SECRET_KEY" "${STRIPE_SECRET_KEY}"
upsert_secret "STRIPE_WEBHOOK_SECRET" "${STRIPE_WEBHOOK_SECRET}"
upsert_secret "STRIPE_ADAPTER_CLIENT_TOKEN" "${STRIPE_ADAPTER_CLIENT_TOKEN}"
upsert_secret "STRIPE_ADAPTER_OPS_TOKEN" "${STRIPE_ADAPTER_OPS_TOKEN}"
upsert_secret "PAYMENT_WEBHOOK_SECRET" "${PAYMENT_WEBHOOK_SECRET}"

echo "Stripe adapter secrets created/updated."
