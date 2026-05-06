/**
 * Site configuration (public only — no secret keys).
 *
 * Remaining setup you own: demo embed URL, custom domain + HTTPS, professional contact email,
 * live Stripe Payment Links, counsel review of terms/privacy. See:
 *   docs/ACCELERATOR_READINESS_CHECKLIST.md
 *   docs/CUSTOM_DOMAIN_EMAIL.md
 *   docs/STRIPE_PAYMENT_LINKS.md
 *   docs/DEMO_VIDEO_SCRIPT.md
 */
window.TRUST_AUDITOR_SITE = {
  githubUrl: "https://github.com/mauriciohollando/identityAgent",
  /** After recording: Loom/YouTube embed URL (see docs/DEMO_VIDEO_SCRIPT.md) */
  demoVideoEmbedUrl: "",
  /** Prefer hello@yourdomain.com for B2B; see docs/CUSTOM_DOMAIN_EMAIL.md */
  contactEmail: "hollandomauricio@gmail.com",
  /** Set when the marketing site has a canonical URL (https://…) */
  publicSiteUrl: "",
  /**
   * Stripe Payment Links — test URLs below; create live links in Dashboard for production.
   */
  stripePaymentLinks: {
    starter: "https://buy.stripe.com/test_00w7sKfxB5P08Lkdemcs800",
    growth: "https://buy.stripe.com/test_bJe9ASdpt6T4f9I1vEcs801",
    scale: "https://buy.stripe.com/test_28EcN4gBFgtE1iS1vEcs802",
  },
};
