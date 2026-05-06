# Trust Auditor — public marketing site

Static HTML/CSS/JS (no build step). Use for **Stripe business verification**, **YC**, and **prospects**.

## Related docs (in repo)

- [docs/DEMO_VIDEO_SCRIPT.md](../docs/DEMO_VIDEO_SCRIPT.md) — record the embed you put in `demoVideoEmbedUrl`
- [docs/CUSTOM_DOMAIN_EMAIL.md](../docs/CUSTOM_DOMAIN_EMAIL.md) — domain, Pages/Netlify, `hello@` email
- [docs/STRIPE_PAYMENT_LINKS.md](../docs/STRIPE_PAYMENT_LINKS.md) — test vs live Payment Links

## Edit before launch

1. **`config.js`**
   - `githubUrl` — default `https://github.com/mauriciohollando/identityAgent` (change if you fork).
   - `stripePaymentLinks` — paste **Stripe Payment Link** URLs (live mode for revenue) for `starter`, `growth`, `scale`.
   - `demoVideoEmbedUrl` — Loom or YouTube **embed** URL for the demo section on the home page.
   - `contactEmail` — prefer a **domain** address when you have one.

2. **Deploy** — Netlify, Cloudflare Pages, GitHub Pages, or GCS bucket + HTTPS. Ensure `config.js` and `site.js` load (same directory).

3. **Legal** — `terms.html` and `privacy.html` are templates; have counsel review before high-volume signup.

## Local preview

```bash
cd reputation-auditor-site && python3 -m http.server 8765
# open http://127.0.0.1:8765/
```
