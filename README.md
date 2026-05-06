# Trust Auditor (A2A)

[![CI](https://github.com/mauriciohollando/identityAgent/actions/workflows/ci.yml/badge.svg)](https://github.com/mauriciohollando/identityAgent/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**One-liner:** Trust Auditor is an **A2A-native API** that scores **agent identity + behavioral history** so platforms can gate **money and risk** before delegating to another agent—with **evidence**, not a black box.

Serverless-friendly **Agent Identity & Reputation Auditor** using Google ADK with A2A, multi-source MCP-style history, registry-backed identity (optional), structured **evidence** payloads, **tier** rules, dispute intake, metrics, rate limits, and an AP2-style payment gate on A2A requests.

| Doc | Purpose |
|-----|---------|
| [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md) | Clone → log service → first audit |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System diagram & components |
| [docs/GITHUB_PUBLISH.md](docs/GITHUB_PUBLISH.md) | Push this repo to GitHub safely |
| [docs/ACCELERATOR_READINESS_CHECKLIST.md](docs/ACCELERATOR_READINESS_CHECKLIST.md) | YC / launch backlog |
| [SECURITY.md](SECURITY.md) | Vulnerability reporting |

**Public marketing site (static):** [reputation-auditor-site/](reputation-auditor-site/) — deploy to Netlify/GitHub Pages + edit `config.js` for GitHub URL, demo video, and Stripe Payment Links.

## Run locally

### Without a Gemini API key (dev)

Core logic works without `GOOGLE_API_KEY`:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
python scripts/smoke_audit.py my-agent-id --context payments
```

REST shim (health, metrics, verify, audit, disputes):

```bash
export PYTHONPATH=src
uvicorn dev_api:app --host 0.0.0.0 --port 8081
# curl -s localhost:8081/metrics
# curl -s localhost:8081/v1/audit-reputation -H 'content-type: application/json' \
#   -d '{"target_agent_id":"demo-agent","context":"test"}'
# curl -s localhost:8081/v1/disputes -H 'content-type: application/json' \
#   -d '{"target_agent_id":"demo-agent","reason":"Incorrect score"}'
```

Use header `X-Verification-Tier: enterprise` (or JSON `verification_tier`) for stricter rules (enterprise requires live MCP, not stub data).

### Full A2A server (needs Gemini)

```bash
export GOOGLE_API_KEY=...
export PYTHONPATH=src
uvicorn auditor:a2a_app --host 0.0.0.0 --port 8080
```

- Agent card: `http://127.0.0.1:8080/.well-known/agent-card.json` (legacy: `/.well-known/agent.json`).
- Ops: `GET /healthz`, `GET /metrics` (Prometheus text).

Set **`AGENT_PUBLIC_BASE_URL`** in production so the card’s `url` matches the Cloud Run endpoint.

## Transaction log (real MCP-shaped history)

The repo includes a small **HTTP log service** the auditor already knows how to call.

1. **Definitions** of outcomes and how `success_rate` is computed: [docs/TRANSACTION_MODEL.md](docs/TRANSACTION_MODEL.md).
2. **Run the service** (SQLite file on disk):

   ```bash
   export PYTHONPATH=src
   export TRANSACTION_LOG_DB_PATH=./data/transaction_log.db
   uvicorn transaction_log.app:app --host 0.0.0.0 --port 8090
   ```

3. **Point the auditor** at it: `export MCP_SERVER_BASE_URL=http://127.0.0.1:8090`

4. **Ingest** events from your platform (worker, webhook, agent runtime):

   ```bash
   curl -s -X POST http://127.0.0.1:8090/v1/agents/my-agent/transactions \
     -H 'content-type: application/json' \
     -d '{"outcome":"success","context":"payments","latency_ms":95}'
   ```

   Outcomes: `success`, `failure`, `disputed`, `refunded`, `cancelled` (see doc).

5. **Seed demo data**: `python scripts/seed_transaction_log.py my-agent --context demo`

6. **Docker Compose** (log + auditor): `docker compose up transaction-log` then run the auditor with `MCP_SERVER_BASE_URL=http://localhost:8090`, or use the full `docker-compose.yml` stack.

Optional: set `LOG_SERVICE_API_KEY` on the log service and the **same** value as `MCP_SERVER_BEARER_TOKEN` on the auditor so GET aggregates are authenticated.

## Identity registry (reference implementation)

**Go-to-market strategy (phased, differentiated):** [docs/GO_TO_MARKET_IDENTITY.md](docs/GO_TO_MARKET_IDENTITY.md)  
**API / schema:** [docs/IDENTITY_REGISTRY_MODEL.md](docs/IDENTITY_REGISTRY_MODEL.md).

**Run the registry** (SQLite):

```bash
export PYTHONPATH=src
export IDENTITY_REGISTRY_DB_PATH=./data/identity_registry.db
uvicorn identity_registry.app:app --host 0.0.0.0 --port 8091
```

**Point the auditor** at it: `export IDENTITY_REGISTRY_URL=http://127.0.0.1:8091`

**Onboard an agent** (operator accountability + optional signing key):

```bash
curl -s -X POST http://127.0.0.1:8091/v1/agents \
  -H 'content-type: application/json' \
  -d '{
    "agent_id":"acme-payments",
    "org_id":"acme",
    "operator_name":"ACME Ops",
    "operator_contact":"ops@acme.example",
    "kyc_verified": true,
    "public_key":"-----BEGIN PUBLIC KEY-----\n...\n-----END PUBLIC KEY-----",
    "algorithm":"RSA"
  }'
```

**Check status** (what the auditor calls): `GET http://127.0.0.1:8091/agents/acme-payments/status`

**Rotation / revocation**: `POST /v1/agents/{id}/keys`, `POST /v1/agents/{id}/keys/{key_id}/revoke`, `POST .../suspend`, `POST .../revoke`, `POST .../activate`.

**Trust ladder (unique signal)** — status includes `trust_tier`: `registered` → `operator_verified` (internal review) → `partner_attested` (B2B partner webhook):

- `POST /v1/admin/agents/{id}/attest/operator` — Bearer **`REGISTRY_ADMIN_API_KEY`**; body `{"attestor":"you@corp.com","notes":"optional"}`.
- `POST /v1/partner/v1/agents/{id}/attest` — header **`X-Partner-Attestation-Token`**: env **`PARTNER_ATTESTATION_TOKEN`**; body `partner_id`, `partner_ref`, optional `attestor`.

The auditor’s evidence includes **`trust_tier_max`** across registries.

**Seed**: `python scripts/seed_identity_registry.py my-agent --kyc`

Optional: `REGISTRY_SERVICE_API_KEY` on the registry and **`IDENTITY_REGISTRY_BEARER_TOKEN`** on the auditor. Stricter eligibility: `REGISTRY_REQUIRE_KYC=1`, `REGISTRY_REQUIRE_SIGNING_KEY=1`.

`docker compose` includes the registry on **8091** and sets `IDENTITY_REGISTRY_URL` for the auditor.

## Payments (AP2-shaped treasury)

Behavior, billing modes (per-call / prepaid credits / hybrid), gateway JSON mapping, idempotency, webhooks, and refunds: **[docs/PAYMENTS_INTEGRATION.md](docs/PAYMENTS_INTEGRATION.md)**.

On the **auditor** (`:8080`) and **dev_api** (`:8081`) apps:

- `POST /internal/webhooks/payment` — PSP settlement callbacks (optional HMAC `X-Payment-Signature`).
- `GET /internal/payments/summary` — reconciliation slice (Bearer `PAYMENT_OPS_API_KEY`).
- `POST /internal/payments/credits` — grant prepaid bundles to a `hiring_agent_id`.

Ledger file: `PAYMENT_LEDGER_DB_PATH` (default `./data/payment_ledger.db`; set in Docker to `/app/data/...`).

## Stripe adapter (real gateway URL quickly)

If you do not have a payment gateway yet, run the included Stripe adapter service and use its URL as `AP2_GATEWAY_URL`.

- Setup guide: `docs/STRIPE_ADAPTER_SETUP.md`
- Service entrypoint: `uvicorn stripe_adapter.app:app --host 0.0.0.0 --port 8092`
- Docker: `Dockerfile.stripeadapter`
- Cloud Run helper: `scripts/cloudrun_deploy_stripe_adapter.sh`

It provides:
- `POST /v1/mandates` (AP2-like authorize)
- `POST /v1/mandates/{mandate_id}/refund`
- `POST /v1/stripe/webhook`
- `POST /v1/admin/mappings` for `payer_agent_id` -> Stripe customer mapping
- `GET /v1/subscription/prices`, `POST /v1/checkout/sessions`, `POST /v1/billing/portal-sessions` (subscription selling; ops token — call from your backend)

## Configuration

See `.env.example` for the full list. Highlights:

| Variable | Purpose |
|----------|---------|
| `GOOGLE_API_KEY` | Gemini (A2A LLM path) |
| `AGENT_PUBLIC_BASE_URL` | Public URL for the agent card |
| `AUDITOR_TOKEN_SECRET` | HMAC secret for verification tokens |
| `MCP_SERVER_URLS` | Comma-separated MCP HTTP bases (or `MCP_SERVER_BASE_URL`) |
| `PERF_AGGREGATION` | `median` or `mean` across sources |
| `IDENTITY_REGISTRY_URLS` | Comma-separated registries (or `IDENTITY_REGISTRY_URL`) |
| `IDENTITY_REGISTRY_BEARER_TOKEN` | Bearer token for registry `GET /agents/.../status` |
| `IDENTITY_REGISTRY_QUORUM` | `all`, `any`, or `majority` |
| `VERIFICATION_TIER` | Default `standard` or `enterprise` |
| `AP2_MODE` | `stub` or `live` |
| `AP2_BILLING_MODE` | `per_call`, `credits`, or `credits_or_gateway` (bundles / hybrid) |
| `PAYMENT_LEDGER_DB_PATH` | SQLite ledger for mandates + credits |
| `PAYMENT_OPS_API_KEY` | Bearer for `/internal/payments/summary` and credit grants |
| `PAYMENT_WEBHOOK_SECRET` | HMAC secret for `/internal/webhooks/payment` |
| `AP2_GATEWAY_URL` | Treasury gateway for `live` (see [docs/PAYMENTS_INTEGRATION.md](docs/PAYMENTS_INTEGRATION.md)) |
| `RATE_LIMIT_PER_MINUTE` | Per-IP limit (0 to disable) |
| `DISPUTES_DB_PATH` | SQLite path for dispute tickets |
| `DISPUTE_FILING_URL` | Public URL shown in API responses |

**Live AP2** expects a JSON response like `{"authorized": true, "mandate_id": "..."}` from `POST {AP2_GATEWAY_URL}/v1/mandates` with body `amount_usd`, `reason`, `payer_agent_id`. Adjust the client in `src/payments.py` to match your real gateway.

## Legal / GTM

- Template only: `legal/TERMS_TEMPLATE.md` (not legal advice). Counsel must review.
- Distribution (marketplaces, orchestrators) and commercial packaging are outside this repo.

## Tests

```bash
pip install -r requirements.txt pytest pytest-asyncio
PYTHONPATH=src pytest
```

## Docker / Cloud Run

```bash
gcloud builds submit --tag gcr.io/your-project/auditor-agent
gcloud run deploy auditor-agent --image gcr.io/your-project/auditor-agent --allow-unauthenticated
```

Use Secret Manager for `GOOGLE_API_KEY`, `AUDITOR_TOKEN_SECRET`, and `AP2_GATEWAY_TOKEN`. For multi-instance Cloud Run, replace SQLite disputes with Cloud SQL or another shared store.

For production launch paths, use:

- `docs/DEPLOY_CLOUD_RUN_PER_CALL.md`
- `scripts/cloudrun_set_secrets.sh`
- `scripts/cloudrun_deploy_per_call.sh`
- `scripts/cloudrun_deploy_subscription.sh` (subscription tiers)
