# Deploy Guide (Per-Call Billing)

This is the **fastest path** to launch revenue:

- `AP2_MODE=live`
- `AP2_BILLING_MODE=per_call`
- payment gateway handles authorization + settlement
- this service handles idempotency, webhook updates, reconciliation endpoints

## 1) Choose required values

- `PROJECT_ID` (GCP project with billing enabled)
- `REGION` (example: `us-central1`)
- `SERVICE_NAME` (example: `trust-auditor`)
- `AP2_GATEWAY_URL` (your treasury/payment API base URL)

Optional:

- `MCP_SERVER_BASE_URL`
- `IDENTITY_REGISTRY_URL`
- `DISPUTE_FILING_URL`

If you do not have a gateway yet, deploy the included Stripe adapter first:
`docs/STRIPE_ADAPTER_SETUP.md` and `scripts/cloudrun_deploy_stripe_adapter.sh`.

## 2) Set gcloud context

```bash
gcloud auth login
gcloud config set project "$PROJECT_ID"
```

## 3) Create/update secrets

```bash
PROJECT_ID="$PROJECT_ID" ./scripts/cloudrun_set_secrets.sh
```

Creates/updates:
- `GOOGLE_API_KEY`
- `AUDITOR_TOKEN_SECRET`
- `AP2_GATEWAY_TOKEN`
- `PAYMENT_WEBHOOK_SECRET`
- `PAYMENT_OPS_API_KEY`

## 4) Deploy Cloud Run

```bash
PROJECT_ID="$PROJECT_ID" \
REGION="$REGION" \
SERVICE_NAME="$SERVICE_NAME" \
AP2_GATEWAY_URL="https://your-gateway.example.com" \
MCP_SERVER_BASE_URL="https://your-log-service.example.com" \
IDENTITY_REGISTRY_URL="https://your-registry.example.com" \
./scripts/cloudrun_deploy_per_call.sh
```

## 5) Configure gateway webhook

Set payment gateway webhook URL to:

`https://<service-url>/internal/webhooks/payment`

Where `<service-url>` is your Cloud Run URL.

Use HMAC SHA-256 signature header:
- Header: `X-Payment-Signature`
- Value: `hex(hmac_sha256(PAYMENT_WEBHOOK_SECRET, raw_body))`

## 6) Quick smoke checks

```bash
curl -fsSL "https://<service-url>/healthz"
curl -fsSL "https://<service-url>/.well-known/agent-card.json"
curl -fsSL "https://<service-url>/metrics"
```

## 7) Ops checks

```bash
curl -s "https://<service-url>/internal/payments/summary?from_unix=0" \
  -H "Authorization: Bearer <PAYMENT_OPS_API_KEY>"
```

## 8) Known production caveats

- SQLite ledgers are fine for single-instance or low scale; for scale-out use shared DB (Cloud SQL, etc.).
- Tax/VAT/chargeback/legal compliance is still owned by your PSP + legal/accounting workflows.
