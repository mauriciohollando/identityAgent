# Payments & treasury integration (AP2-shaped)

This service never holds bank money in-process. It **orchestrates** mandates, records a **ledger**, supports **prepaid credits** (bundles), and talks to **your** gateway (Stripe Billing, Adyen, internal ERP, or a future AP2 hub).

## Pricing models (pick one or combine)

| Mode | Env | Behavior |
|------|-----|----------|
| **Per call** | `AP2_BILLING_MODE=per_call` | Each verification hits `AP2_MODE=stub` or live gateway. |
| **Prepaid credits** | `AP2_BILLING_MODE=credits` | Debits `credit_balances` by `VERIFICATION_FEE_USD`; no gateway call. |
| **Credits then card** | `AP2_BILLING_MODE=credits_or_gateway` | Use balance first; if short, call live gateway. |
| **Subscription tiers** | `AP2_BILLING_MODE=subscription` | Consumes monthly included calls from `subscription_entitlements`; denies when exhausted/expired. |
| **Subscription then card** | `AP2_BILLING_MODE=subscription_or_gateway` | Uses included calls first; falls back to live gateway. |

Grant bundles via **`POST /internal/payments/credits`** (Bearer `PAYMENT_OPS_API_KEY`):

```json
{ "hiring_agent_id": "buyer-1", "amount_cents": 10000, "note": "starter pack" }
```

## Subscription tier operations

Configure default tiers using:

- `AP2_SUBSCRIPTION_TIERS_JSON` (example):

```json
{
  "starter": {"included_calls": 500, "period_days": 30},
  "growth": {"included_calls": 5000, "period_days": 30},
  "scale": {"included_calls": 30000, "period_days": 30}
}
```

Internal ops routes (Bearer `PAYMENT_OPS_API_KEY`):

- `GET /internal/payments/subscriptions/tiers` — view tier config.
- `POST /internal/payments/subscriptions/assign-tier` — assign by `tier_id`:

```json
{ "hiring_agent_id": "buyer-1", "tier_id": "growth" }
```

- `POST /internal/payments/subscriptions/grant` — explicit entitlement write (custom included calls / period).
- `GET /internal/payments/subscriptions/{hiring_agent_id}` — current entitlement and remaining calls.

## Live gateway contract (default)

- **URL:** `{AP2_GATEWAY_URL}{AP2_GATEWAY_MANDATES_PATH}` (default path `/v1/mandates`).
- **Headers:** `Authorization: Bearer …` if `AP2_GATEWAY_TOKEN`; idempotency header `Idempotency-Key` (override with `AP2_IDEMPOTENCY_HEADER`).
- **JSON body (default):**

```json
{
  "amount_usd": 0.1,
  "amount_cents": 10,
  "currency": "USD",
  "reason": "Agent Verification Fee",
  "payer_agent_id": "hiring-agent-id",
  "idempotency_key": "<stable-per-logical-call>"
}
```

- **Response:** `authorized` (bool) and `mandate_id` (string) — field names overridable via `AP2_RESPONSE_AUTHORIZED_FIELD` / `AP2_RESPONSE_MANDATE_ID_FIELD`.

**Custom body:** set `AP2_GATEWAY_JSON_BODY` to a JSON **template** string with placeholders:
`{amount_cents}`, `{currency}`, `{payer_agent_id}`, `{reason}`, `{idempotency_key}`, `{amount_usd}`.
(Use `json.dumps` for `reason` in templates if it contains quotes.)

## Idempotency & A2A

The A2A interceptor derives a stable key from `task_id`, `context_id`, `message_id`, and `hiring_agent_id`, so **retries** of the same user message do not double-charge when the ledger already shows `authorized` for that key.

## Retries

`AP2_HTTP_MAX_RETRIES` (default 3), `AP2_HTTP_RETRY_BACKOFF_SEC` (default 0.5) with exponential backoff on transport errors and **429 / 5xx**.

## Webhooks (settlement / failures)

Expose **`POST /internal/webhooks/payment`** (same path on `auditor` and `dev_api` apps).

If `PAYMENT_WEBHOOK_SECRET` is set, require header **`X-Payment-Signature`** equal to **hex HMAC-SHA256(secret, raw_body)**.

Body example:

```json
{
  "gateway_mandate_id": "mandate_from_psp",
  "status": "settled"
}
```

Statuses update the mandate row matched by `gateway_mandate_id` (e.g. `settled`, `failed`, `refunded`).

### Subscription sync (Stripe adapter → auditor)

When you run the **Stripe adapter**, it can forward subscription lifecycle events to the auditor so `subscription_entitlements` stay aligned with Stripe without manual ops.

- **Auditor path:** `POST /internal/webhooks/subscription-sync` (same **`X-Payment-Signature`** HMAC as payment webhooks when `PAYMENT_WEBHOOK_SECRET` is set).
- **Adapter:** configure Stripe webhooks for `invoice.paid`, `customer.subscription.updated`, and `customer.subscription.deleted` on the adapter’s `/v1/stripe/webhook`. Map Stripe Price IDs to tier ids via **`STRIPE_PRICE_TO_TIER_JSON`**, or set **`metadata[tier_id]`** on the Subscription in Stripe. See [STRIPE_ADAPTER_SETUP.md](STRIPE_ADAPTER_SETUP.md).

## Refunds

`payments.request_refund(gateway_mandate_id)` **POST**s to `{AP2_GATEWAY_URL}{AP2_GATEWAY_REFUND_PATH}` with `{mandate_id}` in the default path template. Adjust in code for your PSP.

## Operations & reporting

- **`GET /internal/payments/summary?from_unix=&to_unix=`** — counts and amounts by mandate status (Bearer `PAYMENT_OPS_API_KEY`).
- Ledger events table **`ledger_events`** — audit trail for credits, mandates, webhooks.

## Persistence paths

- **`PAYMENT_LEDGER_DB_PATH`** — SQLite file (default `./data/payment_ledger.db`). Use a mounted volume or Cloud SQL proxy in production.

## Compliance & tax

Sales tax, VAT, MTL, and PCI scope live **outside** this repo—your gateway and accountants own them. This stack records **commercial intent** (mandate rows + events) for reconciliation.

## Stub persistence

Set **`PAYMENTS_PERSIST_STUB=true`** to write **authorized** mandate rows even in stub mode (useful for end-to-end tests and demos).
