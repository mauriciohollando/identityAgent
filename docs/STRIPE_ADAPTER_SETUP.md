# Stripe Adapter Setup (Real Payments)

This creates a real `AP2_GATEWAY_URL` using Stripe as the money rail.

The adapter exposes:

- `POST /v1/mandates`
- `POST /v1/mandates/{mandate_id}/refund`
- `POST /v1/stripe/webhook`
- admin mapping endpoints for `payer_agent_id` -> Stripe customer/payment method

## 1) Deploy adapter (Cloud Run)

Build/deploy `Dockerfile.stripeadapter` as a separate service (example name `reputation-auditor-payments`).

Set env vars on adapter:

- `STRIPE_SECRET_KEY` (secret)
- `STRIPE_WEBHOOK_SECRET` (secret)
- `STRIPE_ADAPTER_CLIENT_TOKEN` (secret; shared with auditor `AP2_GATEWAY_TOKEN`)
- `STRIPE_ADAPTER_OPS_TOKEN` (secret; for mapping/admin calls)
- `AUDITOR_WEBHOOK_URL` (public auditor URL + `/internal/webhooks/payment`)
- `PAYMENT_WEBHOOK_SECRET` (same value used by auditor)
- `PAYMENT_CURRENCY=USD` (optional)
- `STRIPE_ADAPTER_DB_PATH` (optional; default file path)
- `STRIPE_PRICE_TO_TIER_JSON` (optional; map Stripe Price IDs to auditor tier ids, e.g. `{"price_abc":"starter","price_def":"growth"}`). You can instead set `metadata[tier_id]` on the Subscription in Stripe. **Cloud Run:** JSON contains commas — prefer a Secret Manager secret named `STRIPE_PRICE_TO_TIER_JSON` and `--update-secrets STRIPE_PRICE_TO_TIER_JSON=STRIPE_PRICE_TO_TIER_JSON:latest` (plain `--update-env-vars` often fails to parse).
- **Create tier products/prices in Stripe (terminal):** `python scripts/stripe_ensure_subscription_prices.py` (uses `STRIPE_SECRET_KEY`; idempotent via product metadata `identity_agent_tier`).
- `AUDITOR_SUBSCRIPTION_SYNC_URL` (optional; defaults to sibling of payment webhook: `.../internal/webhooks/subscription-sync`)

Helper scripts:

- `scripts/cloudrun_set_stripe_adapter_secrets.sh`
- `scripts/cloudrun_deploy_stripe_adapter.sh`

**Cloud Run caution:** `gcloud run deploy` / `services update` with `--env-vars-file` **replaces** all plain (non-secret) environment variables with only the keys in that file. To change one variable, either use `--update-env-vars` for simple values or pass a **complete** env file (as in `scripts/cloudrun_deploy_subscription.sh`).

## 2) Configure Stripe webhook

Endpoint URL:

`https://<adapter-url>/v1/stripe/webhook`

### Option A — Stripe API (recommended)

With `STRIPE_SECRET_KEY` in the environment (test or live key for the mode you use):

```bash
export STRIPE_SECRET_KEY=$(gcloud secrets versions access latest --secret=STRIPE_SECRET_KEY --project=YOUR_GCP_PROJECT)
python scripts/stripe_register_adapter_webhook.py --url https://<adapter-url>
```

- If the script **creates** a new endpoint, it prints `whsec_…` — store that as `STRIPE_WEBHOOK_SECRET` for the adapter.
- If it **updates** an existing endpoint, the signing secret is unchanged.

List recurring prices to build `STRIPE_PRICE_TO_TIER_JSON`:

```bash
python scripts/stripe_register_adapter_webhook.py --list-prices
```

(Only `--list-prices` is needed; `--url` is optional for that mode.)

### Option B — Stripe Dashboard

Subscribe to these events on the URL above:

- `payment_intent.succeeded`
- `payment_intent.payment_failed`
- `payment_intent.canceled`
- `charge.refunded`
- `invoice.paid` (subscription renewals — syncs included calls / period to the auditor)
- `customer.subscription.updated`
- `customer.subscription.deleted`

Copy the endpoint signing secret into `STRIPE_WEBHOOK_SECRET`.

## 3) Create payer mappings

Before mandates can charge, map each `payer_agent_id`:

```bash
curl -s -X POST "https://<adapter-url>/v1/admin/mappings" \
  -H "Authorization: Bearer <STRIPE_ADAPTER_OPS_TOKEN>" \
  -H "content-type: application/json" \
  -d '{
    "payer_agent_id":"agent-buyer-1",
    "stripe_customer_id":"cus_123",
    "stripe_payment_method_id":"pm_123"
  }'
```

## 4) Point auditor at adapter

On auditor service:

- `AP2_MODE=live`
- `AP2_BILLING_MODE=per_call` **or** `subscription` / `subscription_or_gateway` if you sell subscription tiers
- `AP2_GATEWAY_URL=https://<adapter-url>`
- `AP2_GATEWAY_TOKEN=<STRIPE_ADAPTER_CLIENT_TOKEN>` (same secret value)
- (keep default paths unless customized)

## 5) Sell subscriptions (Checkout)

**Prerequisites:** `STRIPE_PRICE_TO_TIER_JSON` (or Secret Manager) populated; payer either has a **mapping** (`POST /v1/admin/mappings`) or you pass **`customer_email`** so the adapter can auto-create a Stripe Customer and mapping.

1. **Price catalog** (ops token):

```bash
curl -s "https://<adapter-url>/v1/subscription/prices" \
  -H "Authorization: Bearer <STRIPE_ADAPTER_OPS_TOKEN>"
```

2. **Checkout Session** (ops token). Use `tier_id` (`starter` \| `growth` \| `scale`) or a literal `price_id`. `success_url` may include `{CHECKOUT_SESSION_ID}`.

```bash
curl -s -X POST "https://<adapter-url>/v1/checkout/sessions" \
  -H "Authorization: Bearer <STRIPE_ADAPTER_OPS_TOKEN>" \
  -H "content-type: application/json" \
  -d '{
    "payer_agent_id": "your-hiring-agent-id",
    "tier_id": "growth",
    "customer_email": "buyer@company.com",
    "success_url": "https://your-app.example/billing/success?session_id={CHECKOUT_SESSION_ID}",
    "cancel_url": "https://your-app.example/billing/cancel"
  }'
```

Open `checkout_url` in the browser. After payment, **`invoice.paid`** / **`customer.subscription.updated`** webhooks sync entitlements to the auditor (same as before).

3. **Customer portal** (manage card, cancel, invoices):

```bash
curl -s -X POST "https://<adapter-url>/v1/billing/portal-sessions" \
  -H "Authorization: Bearer <STRIPE_ADAPTER_OPS_TOKEN>" \
  -H "content-type: application/json" \
  -d '{
    "payer_agent_id": "your-hiring-agent-id",
    "return_url": "https://your-app.example/account"
  }'
```

Open `portal_url`. Enable and configure the portal under **Stripe Dashboard → Settings → Billing → Customer portal** (products, cancellation, invoice history).

## 6) Stripe emails & receipts

In **Stripe Dashboard → Settings → Emails** (and **Branding**): turn on **successful payment** / **invoice** emails as needed. Customer portal links and receipts are controlled there; no code changes required.

## 7) End-to-end smoke (script)

```bash
export ADAPTER_URL="https://<adapter-url>"
export OPS_TOKEN="<STRIPE_ADAPTER_OPS_TOKEN>"
./scripts/e2e_subscription_smoke.sh
```

Optional: set `OPEN_CHECKOUT=1`, `SUCCESS_URL`, `CANCEL_URL`, and `PAYER_ID` to create a session from the shell. After paying in test mode, set `AUDITOR_URL` and `PAYMENT_OPS_API_KEY` and re-run to fetch **`GET /internal/payments/subscriptions/{payer_agent_id}`**.

## 8) Guardrails & operations

- **Logs:** The adapter logs **warnings** when forwarding to the auditor returns **HTTP ≥ 400** (`subscription_sync forward failed`, `payment webhook forward failed`). In **Google Cloud Logging**, create a **log-based metric** or alert on `textPayload=~"forward failed"` (or structured filter on `jsonPayload.message` if you add JSON logging later).
- **Dashboard:** Stripe **Developers → Webhooks** — monitor delivery failures and response latency.
- **SQLite on Cloud Run:** The adapter DB is local to each instance. For **multiple instances**, use a **single replica** count, or move mappings/mandates to **Cloud SQL** / a shared store so all replicas see the same payer mappings.

## 9) Smoke test mandate

```bash
curl -s -X POST "https://<adapter-url>/v1/mandates" \
  -H "Authorization: Bearer <STRIPE_ADAPTER_CLIENT_TOKEN>" \
  -H "content-type: application/json" \
  -d '{
    "amount_usd": 0.10,
    "currency": "USD",
    "reason": "Agent Verification Fee",
    "payer_agent_id": "agent-buyer-1",
    "idempotency_key": "demo-key-1"
  }'
```

Response:

```json
{
  "authorized": true,
  "mandate_id": "mandate_...",
  "status": "authorized",
  "stripe_payment_intent_id": "pi_..."
}
```

## Notes

- This is real charging if mapped Stripe customer/payment method can be charged off-session.
- For production scale, move adapter DB from local file to shared DB.
- Keep adapter and auditor tokens distinct from Stripe keys.
- Checkout and portal routes require **`STRIPE_ADAPTER_OPS_TOKEN`**; do not expose that token in a public browser — call these from your **backend** and redirect the user to `checkout_url` / `portal_url`.

