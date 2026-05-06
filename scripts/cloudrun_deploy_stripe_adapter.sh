#!/usr/bin/env bash
set -euo pipefail

# Deploy Stripe adapter service to Cloud Run.
#
# Required:
#   PROJECT_ID
#   REGION
#   ADAPTER_SERVICE_NAME
#   AUDITOR_WEBHOOK_URL
#
# Optional:
#   ADAPTER_IMAGE (default gcr.io/$PROJECT_ID/$ADAPTER_SERVICE_NAME)
#   AUDITOR_SUBSCRIPTION_SYNC_URL (auditor .../internal/webhooks/subscription-sync)
#   STRIPE_PRICE_TO_TIER_JSON (JSON map of Stripe Price id -> tier id)

req() {
  local v="$1"
  if [[ -z "${!v:-}" ]]; then
    echo "Missing required env var: $v" >&2
    exit 1
  fi
}

req PROJECT_ID
req REGION
req ADAPTER_SERVICE_NAME
req AUDITOR_WEBHOOK_URL

ADAPTER_IMAGE="${ADAPTER_IMAGE:-gcr.io/${PROJECT_ID}/${ADAPTER_SERVICE_NAME}}"

echo "Building adapter image: ${ADAPTER_IMAGE}"
gcloud builds submit \
  --project "${PROJECT_ID}" \
  --config cloudbuild.stripeadapter.yaml \
  --substitutions "_ADAPTER_IMAGE=${ADAPTER_IMAGE}" \
  .

ENV_VARS=(
  "AUDITOR_WEBHOOK_URL=${AUDITOR_WEBHOOK_URL}"
  "PAYMENT_CURRENCY=USD"
)
if [[ -n "${AUDITOR_SUBSCRIPTION_SYNC_URL:-}" ]]; then
  ENV_VARS+=("AUDITOR_SUBSCRIPTION_SYNC_URL=${AUDITOR_SUBSCRIPTION_SYNC_URL}")
fi
if [[ -n "${STRIPE_PRICE_TO_TIER_JSON:-}" ]]; then
  ENV_VARS+=("STRIPE_PRICE_TO_TIER_JSON=${STRIPE_PRICE_TO_TIER_JSON}")
fi

ENV_FILE="$(mktemp)"
{
  for item in "${ENV_VARS[@]}"; do
    key="${item%%=*}"
    val="${item#*=}"
    printf "%s: \"%s\"\n" "${key}" "${val//\"/\\\"}"
  done
} > "${ENV_FILE}"

echo "Deploying adapter service: ${ADAPTER_SERVICE_NAME}"
gcloud run deploy "${ADAPTER_SERVICE_NAME}" \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --image "${ADAPTER_IMAGE}" \
  --allow-unauthenticated \
  --env-vars-file "${ENV_FILE}" \
  --set-secrets "STRIPE_SECRET_KEY=STRIPE_SECRET_KEY:latest,STRIPE_WEBHOOK_SECRET=STRIPE_WEBHOOK_SECRET:latest,STRIPE_ADAPTER_CLIENT_TOKEN=STRIPE_ADAPTER_CLIENT_TOKEN:latest,STRIPE_ADAPTER_OPS_TOKEN=STRIPE_ADAPTER_OPS_TOKEN:latest,PAYMENT_WEBHOOK_SECRET=PAYMENT_WEBHOOK_SECRET:latest"
rm -f "${ENV_FILE}"

echo "Adapter deployed."
