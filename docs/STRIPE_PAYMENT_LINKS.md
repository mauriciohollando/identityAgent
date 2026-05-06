# Stripe Payment Links (marketing site)

The public site (`reputation-auditor-site/pricing.html`) reads **Payment Link** URLs from `config.js` → `stripePaymentLinks`. No secret keys in the browser.

## Test vs live

- **Test** links (`buy.stripe.com/test_...`) use your **test** API key. Good for demos and Stripe verification.
- **Live** links use **live** products/prices and **live** mode. Create these when you are ready to charge real cards, then replace URLs in `config.js` and redeploy the static site.

## Create links with Stripe CLI

Set your secret key (test or live):

```bash
export STRIPE_API_KEY=sk_test_...   # or sk_live_...
```

One link per tier (use your **Price** ids from the Dashboard or from `scripts/stripe_ensure_subscription_prices.py`):

```bash
# Starter
stripe payment_links create \
  -d "line_items[0][price]=price_XXXXX" \
  -d "line_items[0][quantity]=1" \
  -d "metadata[tier]=starter"

# Growth
stripe payment_links create \
  -d "line_items[0][price]=price_YYYYY" \
  -d "line_items[0][quantity]=1" \
  -d "metadata[tier]=growth"

# Scale
stripe payment_links create \
  -d "line_items[0][price]=price_ZZZZZ" \
  -d "line_items[0][quantity]=1" \
  -d "metadata[tier]=scale"
```

Copy the `url` from each JSON response into `reputation-auditor-site/config.js`.

### Optional: success redirect

Send buyers back to your site after payment:

```bash
stripe payment_links create \
  -d "line_items[0][price]=price_XXXXX" \
  -d "line_items[0][quantity]=1" \
  -d "after_completion[type]=redirect" \
  -d "after_completion[redirect][url]=https://YOUR_DOMAIN/thanks.html"
```

## Dashboard path

**Stripe Dashboard → Product catalog → [Price] → Create payment link** — then paste URLs into `config.js`.

## After checkout (entitlements)

Payment Links create **Stripe Customers** and **Subscriptions**. Your **payment adapter** still needs a **payer mapping** (`payer_agent_id` ↔ `stripe_customer_id`) for mandates and webhook sync. See [STRIPE_ADAPTER_SETUP.md](STRIPE_ADAPTER_SETUP.md) and onboarding email or a small backend to complete mapping.
