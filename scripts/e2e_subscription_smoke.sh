#!/usr/bin/env bash
set -euo pipefail
#
# Smoke checks for subscription selling + sync (adapter + optional auditor).
#
# Required:
#   ADAPTER_URL   e.g. https://your-adapter.run.app
#   OPS_TOKEN     STRIPE_ADAPTER_OPS_TOKEN (Bearer)
#
# Optional:
#   PAYER_ID      payer_agent_id (default: e2e-smoke-payer)
#   OPEN_CHECKOUT if set to 1, print checkout curl (still need success/cancel URLs)
#   SUCCESS_URL, CANCEL_URL for OPEN_CHECKOUT=1
#   AUDITOR_URL   if set, GET subscription entitlement after sync (needs PAYMENT_OPS_API_KEY)
#   PAYMENT_OPS_API_KEY
#
# Example:
#   export ADAPTER_URL=https://reputation-auditor-payments-xxx.run.app
#   export OPS_TOKEN=...
#   ./scripts/e2e_subscription_smoke.sh

req() {
  local v="$1"
  if [[ -z "${!v:-}" ]]; then
    echo "Missing env var: $v" >&2
    exit 1
  fi
}

req ADAPTER_URL
req OPS_TOKEN

PAYER_ID="${PAYER_ID:-e2e-smoke-payer}"
BASE="${ADAPTER_URL%/}"

echo "== health"
curl -sfS "${BASE}/health"
echo

echo "== subscription price catalog"
curl -sfS "${BASE}/v1/subscription/prices" \
  -H "Authorization: Bearer ${OPS_TOKEN}"
echo

echo "== mapping (404 expected if not provisioned)"
curl -sS -o /dev/null -w "%{http_code}\n" \
  "${BASE}/v1/admin/mappings/${PAYER_ID}" \
  -H "Authorization: Bearer ${OPS_TOKEN}" || true

if [[ "${OPEN_CHECKOUT:-0}" == "1" ]]; then
  req SUCCESS_URL
  req CANCEL_URL
  TIER="${CHECKOUT_TIER:-starter}"
  echo "== checkout session (${TIER})"
  curl -sfS "${BASE}/v1/checkout/sessions" \
    -H "Authorization: Bearer ${OPS_TOKEN}" \
    -H "content-type: application/json" \
    -d "{\"payer_agent_id\":\"${PAYER_ID}\",\"tier_id\":\"${TIER}\",\"success_url\":\"${SUCCESS_URL}\",\"cancel_url\":\"${CANCEL_URL}\",\"customer_email\":\"smoke@example.com\"}"
  echo
fi

if [[ -n "${AUDITOR_URL:-}" && -n "${PAYMENT_OPS_API_KEY:-}" ]]; then
  ABASE="${AUDITOR_URL%/}"
  echo "== auditor entitlement (ops)"
  curl -sfS "${ABASE}/internal/payments/subscriptions/${PAYER_ID}" \
    -H "Authorization: Bearer ${PAYMENT_OPS_API_KEY}"
  echo
fi

echo "Done. Complete a real Checkout in Stripe test mode, then re-run with AUDITOR_URL + PAYMENT_OPS_API_KEY to verify entitlement."
