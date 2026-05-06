# Accelerator readiness — execution checklist

Single place for **YC / accelerator prep** and **customer-facing** polish. Product wedge: **Trust Auditor = agent handoff gate** (allow / deny / review before delegation or payout) — see [GO_TO_MARKET_IDENTITY.md](GO_TO_MARKET_IDENTITY.md).

**Legend:** 🔧 code/repo · ☁️ infra / DNS · 📣 copy / legal · 🎬 demo · 🔐 secrets

---

## Done in this repository (baseline)

Use this as the “already shipped” list; don’t duplicate work below.

- [x] **Positioning** — README, site, `pyproject.toml`, GTM doc, root agent instructions, agent card copy: handoff gate + structured evidence (not a global reputation network).
- [x] **MIT `LICENSE`**, **`SECURITY.md`**, **`CONTRIBUTING.md`**
- [x] **GitHub Actions CI** — `.github/workflows/ci.yml` (Python 3.12, `pytest`)
- [x] **`requirements-dev.txt`**, **`.gitignore`** (`.env`, `data/`, `*.db`, credentials patterns)
- [x] **README** — doc table, CI badge, marketing site pointer
- [x] **Developer docs** — `docs/GETTING_STARTED.md`, `docs/ARCHITECTURE.md`, `docs/GITHUB_PUBLISH.md`, transaction model, demo script, Stripe + domain guides
- [x] **Agent card** — `.well-known/agent-card.json` valid (see `tests/test_agent_card.py`); `url` / extension URI must stay in sync with **deployed** A2A host after each deploy
- [x] **Marketing site** — `reputation-auditor-site/`: hero, ICP, how-it-works, pricing (`config.js` → Payment Links), terms/privacy stubs, shared assets
- [x] **Contact wiring** — legal pages and footer read `contactEmail` from `config.js`

---

## Your next actions (outside the repo or one-time setup)

Check these off as **you** complete them; they are not automatable here.

- [ ] 🎬 **Demo** — Record 90–120s per [DEMO_VIDEO_SCRIPT.md](DEMO_VIDEO_SCRIPT.md); set `reputation-auditor-site/config.js` → `demoVideoEmbedUrl`.
- [ ] ☁️ **Custom domain + HTTPS** — Host `reputation-auditor-site/`; then set `publicSiteUrl` in `config.js` if you use it. Steps: [CUSTOM_DOMAIN_EMAIL.md](CUSTOM_DOMAIN_EMAIL.md).
- [ ] 📣 **Professional email** — e.g. `hello@yourdomain.com` in `config.js` (replace personal Gmail for B2B).
- [ ] ☁️ **Live Stripe** — Create **live** Payment Links; paste into `config.js` → `stripePaymentLinks`. Plan **post-checkout** mapping (`payer_agent_id` ↔ Stripe customer): see [STRIPE_PAYMENT_LINKS.md](STRIPE_PAYMENT_LINKS.md) and checklist below.
- [ ] 🔐 **Secrets hygiene** — Confirm no `sk_live_`, `whsec_`, or GCP keys in git history; enable GitHub secret scanning; rotate anything ever exposed.
- [ ] ☁️ **GitHub** — Branch protection on `main` (require CI if you want); repo description, website URL, topics (`agents`, `a2a`, `trust`, `api`).
- [ ] 📣 **Legal** — Counsel review of [terms.html](../reputation-auditor-site/terms.html) and [privacy.html](../reputation-auditor-site/privacy.html) before scaling sign-up / paid marketing.
- [ ] 📣 **Fundraising assets** — Deck (problem, handoff-gate solution, why now, screenshot, traction, team, ask); traction slide even if early.

---

## Production & operations (ongoing)

- [ ] 🔧 After each **Cloud Run** (or other) deploy: **`AGENT_PUBLIC_BASE_URL`**, serve **`/.well-known/agent-card.json`** from the same host, and update the on-disk card if the public base URL changed.
- [ ] ☁️ **Scale** — SQLite is fine for early adapter/ledger; for horizontal scale, move to a shared DB or single-instance adapter (see [ARCHITECTURE.md](ARCHITECTURE.md)).
- [ ] ☁️ **Monitoring** — Log alerts for payment/adapter failures; Stripe webhook health checks.
- [ ] 🔐 **Secrets in prod** — Secret Manager / platform secrets only; never in repo or static HTML.

---

## Subscription MVP (live revenue)

1. Stripe Dashboard (**live**): products/prices + **Payment Links** per tier.  
2. Site: pricing buttons → those links (update `config.js`).  
3. Post-purchase: email or flow to map **`payer_agent_id`** ↔ customer until you add server-side Checkout.  
4. Optional later: `POST /v1/checkout/sessions` + small backend for smoother onboarding.

---

## Accelerator application (Phase 7 style)

- [ ] 🎬 **~2 min demo** — Transaction POST → audit JSON → call out **handoff / payout gate** and evidence fields.
- [ ] 📣 **Moat (2 bullets)** — Behavioral history from **your** log + identity ladder + optional AP2-style billing; point to [GO_TO_MARKET_IDENTITY.md](GO_TO_MARKET_IDENTITY.md).

---

## Reference — optional hardening (nice-to-have)

- [ ] 🔧 CI: `ruff` or other linters if you adopt them.
- [ ] 🎬 Static **sample audit JSON** on the site (anonymized) with copy button.
- [ ] 🔧 **GitHub org** move (e.g. `your-org/trust-auditor`) if branding needs it; update all links.

Track larger work as GitHub Issues if you prefer.
