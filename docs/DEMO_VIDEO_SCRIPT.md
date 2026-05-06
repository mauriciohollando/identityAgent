# Demo video script (~90–120 seconds)

Use this for a **Loom**, **QuickTime screen + mic**, or **YouTube**. Target audience: technical buyer (platform / marketplace engineer).

## Before you record

1. Terminal **font size 14–16**, dark theme, full-screen or large window.
2. Two terminal tabs **or** split: **transaction log** (8090) and **dev_api** (8081) — see [GETTING_STARTED.md](GETTING_STARTED.md).
3. Optional: hide unrelated desktop notifications.

## Suggested structure

### [0:00–0:15] Hook

**Say:**  
“Agents call other agents and move money. Before the **next handoff** or **payout**, you need **identity plus behavioral history** from **your** log — not a vanity ID or a global reputation network. **Trust Auditor** is a **handoff gate**: **allow, flag, or require review**, with **structured evidence** in one API call.”

**Show:**  
GitHub repo `mauriciohollando/identityAgent` README (one scroll past the one-liner) **or** your public marketing site hero.

---

### [0:15–0:45] Ingest + audit

**Say:**  
“We record **outcomes** — success, failure, refund — into a transaction log. The auditor aggregates **success rate** over a window, combines optional **registry** identity, and returns a **trust score** and status your router can treat as a **gate** before delegation or funds.”

**Do:**

```bash
# Tab 1 — log service already running; then:
curl -s -X POST http://127.0.0.1:8090/v1/agents/demo-agent/transactions \
  -H 'content-type: application/json' \
  -d '{"outcome":"success","context":"payments","latency_ms":120}'

curl -s -X POST http://127.0.0.1:8090/v1/agents/demo-agent/transactions \
  -H 'content-type: application/json' \
  -d '{"outcome":"success","context":"payments","latency_ms":95}'
```

**Then (dev_api on 8081):**

```bash
curl -s http://127.0.0.1:8081/v1/audit-reputation \
  -H 'content-type: application/json' \
  -d '{"target_agent_id":"demo-agent","context":"payments"}' | python3 -m json.tool
```

**Say:**  
“Here’s **trust_score**, **status**, **performance.sample_size**, and **evidence** — ready for your policy engine, router, or AP2-style payment gate.”

---

### [0:45–1:15] Product truth + CTA

**Say:**  
“If you **don’t** wire a log service, the stack can run in **stub mode** for dev — **not** for production buyers. In production you connect your **MCP-shaped history** or this log service.”

**Show (optional):**  
`docs/ARCHITECTURE.md` diagram in the repo **or** pricing page with tiers.

**Say:**  
“Docs and **Getting started** are on GitHub; subscription checkout is on the marketing site via **Stripe Payment Links**. I’m [name] — [contact].”

---

## Loom tips

- **720p or 1080p**, **show cursor**, record **system audio** off unless you add music later.
- After upload: copy the **embed** URL into `reputation-auditor-site/config.js` → `demoVideoEmbedUrl` (use the `embed` URL Loom gives you, or a `share` URL — `site.js` rewrites Loom share → embed).

## Short vertical cut (30s) for social

Hook (5s) → one `curl` audit result showing `trust_score` + `APPROVED` (15s) → CTA + GitHub URL (10s).
