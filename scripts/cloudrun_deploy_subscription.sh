#!/usr/bin/env bash
set -euo pipefail

# Deploy Trust Auditor to Cloud Run with subscription-tier billing.
#
# Required env vars:
#   PROJECT_ID, REGION, SERVICE_NAME, AP2_GATEWAY_URL
# Optional:
#   AP2_SUBSCRIPTION_TIERS_JSON
#   MCP_SERVER_BASE_URL, IDENTITY_REGISTRY_URL, DISPUTE_FILING_URL
#   IMAGE_NAME (default: gcr.io/$PROJECT_ID/$SERVICE_NAME)

req() {
  local v="$1"
  if [[ -z "${!v:-}" ]]; then
    echo "Missing required env var: $v" >&2
    exit 1
  fi
}

req PROJECT_ID
req REGION
req SERVICE_NAME
req AP2_GATEWAY_URL

IMAGE_NAME="${IMAGE_NAME:-gcr.io/${PROJECT_ID}/${SERVICE_NAME}}"
MCP_SERVER_BASE_URL="${MCP_SERVER_BASE_URL:-}"
IDENTITY_REGISTRY_URL="${IDENTITY_REGISTRY_URL:-}"
DISPUTE_FILING_URL="${DISPUTE_FILING_URL:-}"
AP2_SUBSCRIPTION_TIERS_JSON="${AP2_SUBSCRIPTION_TIERS_JSON:-{\"starter\":{\"included_calls\":500,\"period_days\":30},\"growth\":{\"included_calls\":5000,\"period_days\":30},\"scale\":{\"included_calls\":30000,\"period_days\":30}}}"

echo "Building image: ${IMAGE_NAME}"
gcloud builds submit --project "${PROJECT_ID}" --tag "${IMAGE_NAME}"

ENV_VARS=(
  "AGENT_PUBLIC_BASE_URL=https://${SERVICE_NAME}-${PROJECT_ID}.${REGION}.run.app/"
  "AP2_MODE=live"
  "AP2_BILLING_MODE=subscription"
  "AP2_SUBSCRIPTION_TIERS_JSON=${AP2_SUBSCRIPTION_TIERS_JSON}"
  "AP2_GATEWAY_URL=${AP2_GATEWAY_URL}"
  "AP2_GATEWAY_MANDATES_PATH=/v1/mandates"
  "AP2_HTTP_MAX_RETRIES=3"
  "AP2_HTTP_RETRY_BACKOFF_SEC=0.5"
  "PAYMENT_CURRENCY=USD"
  "VERIFICATION_FEE_USD=0.10"
  "RATE_LIMIT_PER_MINUTE=120"
)

if [[ -n "${MCP_SERVER_BASE_URL}" ]]; then
  ENV_VARS+=("MCP_SERVER_BASE_URL=${MCP_SERVER_BASE_URL}")
fi
if [[ -n "${IDENTITY_REGISTRY_URL}" ]]; then
  ENV_VARS+=("IDENTITY_REGISTRY_URL=${IDENTITY_REGISTRY_URL}")
fi
if [[ -n "${DISPUTE_FILING_URL}" ]]; then
  ENV_VARS+=("DISPUTE_FILING_URL=${DISPUTE_FILING_URL}")
fi

echo "Deploying Cloud Run service: ${SERVICE_NAME}"
ENV_FILE="$(mktemp)"
{
  for item in "${ENV_VARS[@]}"; do
    key="${item%%=*}"
    val="${item#*=}"
    printf "%s: \"%s\"\n" "${key}" "${val//\"/\\\"}"
  done
} > "${ENV_FILE}"
gcloud run deploy "${SERVICE_NAME}" \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --image "${IMAGE_NAME}" \
  --allow-unauthenticated \
  --env-vars-file "${ENV_FILE}" \
  --set-secrets "GOOGLE_API_KEY=GOOGLE_API_KEY:latest,AUDITOR_TOKEN_SECRET=AUDITOR_TOKEN_SECRET:latest,AP2_GATEWAY_TOKEN=AP2_GATEWAY_TOKEN:latest,PAYMENT_WEBHOOK_SECRET=PAYMENT_WEBHOOK_SECRET:latest,PAYMENT_OPS_API_KEY=PAYMENT_OPS_API_KEY:latest"
rm -f "${ENV_FILE}"

echo "Done."
echo "Next: assign subscription tiers to hiring agents through:"
echo "  POST https://${SERVICE_NAME}-${PROJECT_ID}.${REGION}.run.app/internal/payments/subscriptions/assign-tier"
