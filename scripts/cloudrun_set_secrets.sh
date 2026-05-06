#!/usr/bin/env bash
set -euo pipefail

# Creates/updates required Secret Manager secrets for deploy script.
#
# Usage:
#   PROJECT_ID=... ./scripts/cloudrun_set_secrets.sh
#
# It will prompt for secret values.

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

read -r -s -p "GOOGLE_API_KEY: " GOOGLE_API_KEY
echo
read -r -s -p "AUDITOR_TOKEN_SECRET (random long string): " AUDITOR_TOKEN_SECRET
echo
read -r -s -p "AP2_GATEWAY_TOKEN: " AP2_GATEWAY_TOKEN
echo
read -r -s -p "PAYMENT_WEBHOOK_SECRET: " PAYMENT_WEBHOOK_SECRET
echo
read -r -s -p "PAYMENT_OPS_API_KEY: " PAYMENT_OPS_API_KEY
echo

upsert_secret "GOOGLE_API_KEY" "${GOOGLE_API_KEY}"
upsert_secret "AUDITOR_TOKEN_SECRET" "${AUDITOR_TOKEN_SECRET}"
upsert_secret "AP2_GATEWAY_TOKEN" "${AP2_GATEWAY_TOKEN}"
upsert_secret "PAYMENT_WEBHOOK_SECRET" "${PAYMENT_WEBHOOK_SECRET}"
upsert_secret "PAYMENT_OPS_API_KEY" "${PAYMENT_OPS_API_KEY}"

echo "Secrets created/updated in project ${PROJECT_ID}."
