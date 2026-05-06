# Getting started

Run the **Trust Auditor** (**agent handoff gate**) locally: log one transaction outcome, then call an audit the way you would before a handoff or payout.

## Prerequisites

- Python **3.12+**
- Optional: `GOOGLE_API_KEY` for the full A2A + Gemini path (core flows work without it for smoke tests)

## 1. Clone and install

```bash
git clone https://github.com/mauriciohollando/identityAgent.git
cd identityAgent
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
export PYTHONPATH=src
```

## 2. Transaction log (real success-rate data)

Terminal 1:

```bash
export PYTHONPATH=src
export TRANSACTION_LOG_DB_PATH=./data/transaction_log.db
uvicorn transaction_log.app:app --host 127.0.0.1 --port 8090
```

Seed or POST events (example):

```bash
curl -s -X POST http://127.0.0.1:8090/v1/agents/demo-agent/transactions \
  -H 'content-type: application/json' \
  -d '{"outcome":"success","context":"payments","latency_ms":95}'
```

See [TRANSACTION_MODEL.md](TRANSACTION_MODEL.md) for outcome semantics.

## 3. Auditor (A2A)

Terminal 2:

```bash
export PYTHONPATH=src
export MCP_SERVER_BASE_URL=http://127.0.0.1:8090
# optional: export GOOGLE_API_KEY=...
uvicorn auditor:a2a_app --host 127.0.0.1 --port 8080
```

- Agent card: `http://127.0.0.1:8080/.well-known/agent-card.json`

## 4. REST shim (quick JSON audit)

Terminal 3 (optional):

```bash
export PYTHONPATH=src
export MCP_SERVER_BASE_URL=http://127.0.0.1:8090
uvicorn dev_api:app --host 127.0.0.1 --port 8081
```

```bash
curl -s http://127.0.0.1:8081/v1/audit-reputation \
  -H 'content-type: application/json' \
  -d '{"target_agent_id":"demo-agent","context":"payments"}'
```

You should see `trust_score`, `status`, `performance`, and `evidence`.

## 5. Without MCP (stub vs production)

If `MCP_SERVER_BASE_URL` / `MCP_SERVER_URLS` are unset:

- **`AP2_MODE=stub`** (default in `.env.example`): a **synthetic** success rate is generated for local dev. Audits include **`STUB_PERFORMANCE_DATA`** and **`REVIEW_REQUIRED`** so you do not auto-approve on fake numbers.
- **`AP2_MODE=live`**: **no** synthetic data—performance is **`unavailable`** (`success_rate` 0, `sample_size` 0) with **`NO_PERFORMANCE_DATA`** and **`REVIEW_REQUIRED`**. Production must set **`MCP_SERVER_*`** to a real transaction log (or compatible aggregate HTTP API).

Override (emergency demo only): `TRUST_AUDITOR_ALLOW_PERFORMANCE_STUB=true` with `AP2_MODE=live`—avoid in customer-facing production.

## 6. Payments & Stripe adapter

For billing integration, see [PAYMENTS_INTEGRATION.md](PAYMENTS_INTEGRATION.md) and [STRIPE_ADAPTER_SETUP.md](STRIPE_ADAPTER_SETUP.md).

## 7. Docker Compose

```bash
docker compose up transaction-log
# then run auditor with MCP_SERVER_BASE_URL=http://localhost:8090
```

Full stack (with registry + stripe adapter): see root [README.md](../README.md).
