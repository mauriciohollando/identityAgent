# Accelerator readiness — execution checklist

Use this as the single source of truth for YC / accelerator prep and **customer-facing** polish. Check items off as you complete them.

## Already landed in this repository (baseline)

- [x] **MIT `LICENSE`**, **`SECURITY.md`**, **`CONTRIBUTING.md`**
- [x] **GitHub Actions CI** — `.github/workflows/ci.yml` (Python 3.12, `pytest`)
- [x] **`requirements-dev.txt`** for pytest / asyncio
- [x] **`.gitignore`** hardened for `.env`, `data/`, `*.db`, common credential filenames
- [x] **README** — one-liner, doc table, CI badge (`mauriciohollando/identityAgent`), marketing site pointer
- [x] **`docs/GETTING_STARTED.md`**, **`docs/ARCHITECTURE.md`**, **`docs/GITHUB_PUBLISH.md`**
- [x] **Agent card** — production-style `url`, `documentationUrl` placeholder, extension URI on same host (replace when you change domains)
- [x] **Marketing site** — `reputation-auditor-site/`: home (ICP, how-it-works, demo block, product-truth), **pricing** with Stripe Payment Link wiring via `config.js`, updated terms/privacy stubs, shared `styles.css` + `site.js`
- [x] **Docs** — [STRIPE_PAYMENT_LINKS.md](STRIPE_PAYMENT_LINKS.md), [DEMO_VIDEO_SCRIPT.md](DEMO_VIDEO_SCRIPT.md), [CUSTOM_DOMAIN_EMAIL.md](CUSTOM_DOMAIN_EMAIL.md); site **contact** pulls from `config.js` (visible address on legal pages)
- [ ] **You still must:** record **demo** → set `demoVideoEmbedUrl`; **custom domain** + **professional email** per [CUSTOM_DOMAIN_EMAIL.md](CUSTOM_DOMAIN_EMAIL.md); **live** Stripe links; counsel review; **deck**; **traction**

**Legend:** 🔧 code/repo · ☁️ infra / DNS · 📣 copy / legal · 🎬 demo · 🔐 secrets

---

## Phase 0 — Repository & GitHub

- [ ] 🔐 **Scrub secrets** — Confirm no API keys, `sk_live_`, `whsec_`, or GCP keys are committed (search: `git log -p`, GitHub secret scanning). Rotate anything that ever leaked in chat/logs.
- [ ] Create **GitHub org or user repo** (e.g. `your-org/trust-auditor` or `reputation-auditor`).
- [ ] **Initialize / push** — `git remote add origin …`, push `main`, add **README** visible on landing.
- [ ] Add **`.gitignore`** coverage for `.env`, `*.db`, `.venv`, service account JSON (verify nothing sensitive tracked).
- [ ] **Branch protection** on `main` (require PR, optional required checks for CI).
- [ ] **Repo metadata** — Description, website URL (public site), topics (`agents`, `a2a`, `trust`, `api`).
- [ ] Optional: **GitHub CLI** — `gh repo create`, `gh secret set` for CI (if using Actions with deploy later).

---

## Phase 1 — Engineering hygiene (what reviewers open first)

- [ ] 🔧 Add **root `LICENSE`** (MIT, Apache-2.0, or proprietary “All rights reserved” — pick with counsel).
- [ ] 🔧 Add **`SECURITY.md`** — How to report vulnerabilities (email or GitHub Security Advisories).
- [ ] 🔧 Add **CI** — `.github/workflows/ci.yml`: checkout, Python 3.12, `pip install -r requirements.txt`, `pytest tests/`.
- [ ] 🔧 Optional CI: `ruff check` / format if you adopt Ruff; fail on warnings if desired.
- [ ] 🔧 **`requirements-dev.txt`** or `[dev]` extras (pytest only is fine to start).
- [ ] 🔧 Confirm **`python -m pytest tests/`** passes cleanly on a fresh clone (document Python version in README).

---

## Phase 2 — Brand, narrative, and product truth

- [ ] 📣 **Pick one public name** — e.g. *Trust Auditor* **or** *ReputationAuditor* everywhere (site, README H1, agent card `name`, emails).
- [ ] 📣 **One-liner** — Problem + who + outcome (one sentence) at top of README + site hero.
- [ ] 📣 **ICP paragraph** — Who buys first (marketplace, agent platform, fintech, internal tools).
- [ ] 📣 **Pricing truth** — Align: per-call **and/or** subscription tiers; link to Stripe products or “Contact for enterprise.”
- [ ] 📣 **Stub honesty** — State clearly: without **transaction log / MCP**, performance scores use **stub data**; production path = ingest events (link to `docs/TRANSACTION_MODEL.md`).

---

## Phase 3 — Agent card & API discoverability

- [ ] 🔧 **`.well-known/agent-card.json`** — Set `url` to **production A2A base** (real `https://…run.app` or custom domain), not `https://run.app/` or placeholders.
- [ ] 🔧 **Extensions URI** — Replace `trust-auditor.local` with a **real https** doc URL or remove until stable; avoid broken links in discovery.
- [ ] 🔧 **`version` / `protocolVersion`** — Keep in sync with what you actually run; re-run `tests/test_agent_card.py` after edits.
- [ ] 🔧 Ensure **deployed** service serves the same card at `/.well-known/agent-card.json` (or path your A2A stack uses).

---

## Phase 4 — Public site (`reputation-auditor-site/`)

### Core polish

- [ ] 📣 **Hero** — Name, one-liner, primary CTA (e.g. “View demo” / “Get API access” / “Pricing”).
- [ ] 📣 **How it works** — 3 steps: ingest outcomes → audit → decision / evidence (plain English).
- [ ] 📣 **Trust & scope** — Decision-support, not a guarantee; link to Terms.
- [ ] 📣 **Footer** — Terms, Privacy, optional Security, GitHub/docs link.
- [ ] ☁️ **Hosting** — Netlify / Cloud Storage + Cloud CDN / GitHub Pages; **custom domain** + HTTPS.
- [ ] 📣 **Contact** — Prefer **`hello@yourdomain.com`** over personal Gmail for B2B (DNS + Google Workspace / forwarder).

### Demo section (on site)

- [ ] 🎬 **Embedded or linked demo** — Short **Loom / YouTube** (90–120s): transaction POST → audit result → trust score + evidence.
- [ ] 🎬 **Static “live example”** — Optional: anonymized JSON **sample response** (no real customer data) with copy button.
- [ ] 🔧 **Link to repo** “Try locally” — `docker compose` or `scripts/smoke_audit.py` one-liner from README.

### Subscription / “easy subscribe” (important: no secret keys in the browser)

**Do not** embed `STRIPE_ADAPTER_OPS_TOKEN` in static HTML. Use one of:

- [ ] ☁️ **Stripe Payment Links** or **Pricing Table** (Dashboard) — Embed **publishable** snippet on site; products = your **live** prices; success/cancel URLs → site pages.  
  - [ ] Create **live** products/prices (mirror test tiers if needed).
  - [ ] After payment, **webhook** still updates entitlements if customer is mapped — you need a **post-checkout** path to map `payer_agent_id` ↔ Stripe Customer (email capture, magic link, or serverless function).
- [ ] 🔧 **Minimal backend** (optional) — Small Cloud Run **public** endpoint: collects email + `payer_agent_id`, server-side calls `POST /v1/checkout/sessions` with ops token, returns redirect URL (best UX, more code).
- [ ] 📣 **“Subscribe” page** — Table of tiers (starter/growth/scale), bullets (included verifications), **Buy** buttons → Payment Links or backend.

### Legal pages

- [ ] 📣 **Terms** — Align with **subscription + refunds + Stripe**; decision-support disclaimer (keep); governing law / entity name if you have one.
- [ ] 📣 **Privacy** — Subprocessors (Stripe, GCP, Google AI if applicable), retention, contact, GDPR-style rights if EU customers.
- [ ] 📣 Counsel **review** before “sign up” marketing at scale.

---

## Phase 5 — README & developer docs

- [ ] 📣 **README above the fold** — One-liner, link to **public site**, **docs**, **CI badge** (after CI exists).
- [ ] 🔧 **`docs/GETTING_STARTED.md`** — Clone, `.env.example`, run auditor + transaction log, one `curl` audit, one `curl` transaction POST.
- [ ] 🔧 Link **GO_LIVE_STRIPE** or fold **live vs test** Stripe steps into `docs/STRIPE_ADAPTER_SETUP.md` (live keys, live webhook, live price map).
- [ ] 📣 **Architecture** — One diagram (Mermaid or PNG): client → auditor → registry / log / Stripe.

---

## Phase 6 — Production & operations

- [ ] ☁️ **Cloud Run** — Document **min instances** / **single region**; adapter DB **single instance** or migrate to shared DB for scale-out.
- [ ] ☁️ **Monitoring** — Log-based alerts for adapter “forward failed”; Stripe webhook dashboard checks.
- [ ] 🔐 **Secrets** — All in Secret Manager / GitHub Actions secrets; never in repo.

---

## Phase 7 — Accelerator application assets (non-code)

- [ ] 🎬 **2-min demo** — Record after Phase 4 demo script is stable.
- [ ] 📣 **Deck** (10–12 slides) — Problem, solution, why now, market, product screenshot, traction, team, ask.
- [ ] 📣 **Traction slide** — Even if early: pilots, waitlist N, LOIs, MRR, or “technical milestones shipped.”
- [ ] 📣 **Moat** — 2 bullets: behavioral reputation + identity ladder + payments (point to `docs/GO_TO_MARKET_IDENTITY.md`).

---

## Suggested order (fastest path)

1. Phase 0 + 1 (GitHub + CI + LICENSE + SECURITY)  
2. Phase 2 + 3 (story + agent card URLs)  
3. Phase 4 (site + subscribe via **Payment Links** first — fastest)  
4. Phase 5 (README + getting started)  
5. Phase 6–7 (ops hardening + deck + video)

---

## Subscription page — recommended MVP

1. In **Stripe Dashboard (live)**: create **Payment Links** for each tier (monthly).  
2. On site: **Pricing** page with three cards → each button opens Payment Link.  
3. Post-purchase: email buyers with **“complete onboarding”** link to map `payer_agent_id` (form or support) until you build serverless checkout.  
4. Later: replace with **checkout sessions API** + automatic mapping when you add the small backend.

This checklist is the **backlog**; work can be tracked as GitHub Issues per checkbox group if you prefer.
