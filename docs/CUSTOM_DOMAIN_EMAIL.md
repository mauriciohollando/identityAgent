# Custom domain + professional email

Use this checklist to move off a personal Gmail on the marketing site and look **B2B-credible** to Stripe, YC, and customers.

**Context:** **Trust Auditor** is positioned as an **agent handoff gate** (allow / deny / review before delegation or payout). A custom domain and team inbox match that story better than a consumer Gmail on the contact and legal pages.

## 1. Pick and register a domain

Examples of patterns (availability varies): `trustauditor.com`, `trytrustauditor.com`, `trustlayer.dev`, `agenttrust.io`.

Registrars: **Cloudflare Registrar**, **Namecheap**, **Google Domains → Squarespace**, **Porkbun**. Enable **WHOIS privacy** if offered.

## 2. Host the static marketing site on that domain

Your files live in `reputation-auditor-site/`.

| Host | Steps (high level) |
|------|---------------------|
| **Cloudflare Pages** | Connect GitHub repo `mauriciohollando/identityAgent`, set build output to `reputation-auditor-site` (or no build, root that folder), add custom domain, enable SSL. |
| **Netlify** | New site from Git → pick repo → publish directory `reputation-auditor-site` → Domain settings → add apex + `www`. |
| **GitHub Pages** | Repo Settings → Pages → deploy from branch `main` and folder `/reputation-auditor-site` (or use an Action); add CNAME for `www`. |

**DNS:** Point `A` / `CNAME` as your host instructs (often **proxied** through Cloudflare).

**Verify:** `https://YOUR_DOMAIN/` loads `index.html`; `pricing.html` and `config.js` load (check browser devtools Network tab).

## 3. Professional email (pick one)

### Option A — **Google Workspace** (best for serious B2B)

- Sign up at [workspace.google.com](https://workspace.google.com) with **YOUR_DOMAIN**.
- Create **`hello@`** or **`team@`**.
- **MX records** in DNS per Google’s wizard (~$6–7/user/mo).

**Pros:** Gmail UI, calendar, easy **Send mail as** for founders.  
**Cons:** Cost.

### Option B — **Cloudflare Email Routing** (free forwarding)

- In Cloudflare → **Email** → **Email Routing**: create address `hello@YOUR_DOMAIN` → **forward to** your current Gmail.
- You **receive** at Gmail; **sending** as `hello@` from Gmail requires Gmail **Send mail as** (SMTP) or Workspace later.

**Pros:** Free, fast.  
**Cons:** Outbound “from” domain needs extra setup for SPF/DKIM if you mass-mail.

### Option C — **Proton / Fastmail** for `hello@`

- Similar to Workspace: paid mailbox on your domain.

## 4. Update the marketing site

1. Edit **`reputation-auditor-site/config.js`**:
   - `contactEmail`: **`hello@YOUR_DOMAIN`** (or your Workspace address).
   - Optionally set `publicSiteUrl`: **`https://YOUR_DOMAIN`** (reference only for you today; can power future canonical tags).
2. Commit and push; redeploy static hosting.
3. **Terms** / **Privacy** contact lines use `data-role="contact-email"` — `site.js` updates **mailto** and visible address where applicable (see `data-show-address` on nav “Contact” links).

## 5. Stripe + GitHub

- **Stripe Dashboard** → Business settings → **public website** / support URL → `https://YOUR_DOMAIN`.
- **GitHub** repo **About** → Website → same URL.

## 6. Optional: apex redirect

Redirect `https://YOUR_DOMAIN` → `https://www.YOUR_DOMAIN` (or reverse) in your host’s redirect rules so links are consistent.

## 7. Legal

When you incorporate, update **Terms** / **Privacy** with **legal entity name** and address; have counsel review before high-volume signup.

---

**Minimal path this week:** register domain → **Cloudflare Pages** + **Email Routing** to Gmail → set `contactEmail` in `config.js` → redeploy.
