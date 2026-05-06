/**
 * Site configuration (public only). See docs/CUSTOM_DOMAIN_EMAIL.md for domain + email setup.
 */
window.TRUST_AUDITOR_SITE = {
  githubUrl: "https://github.com/mauriciohollando/identityAgent",
  /** After recording: Loom/YouTube embed URL (see docs/DEMO_VIDEO_SCRIPT.md) */
  demoVideoEmbedUrl: "",
  /** Use hello@yourdomain.com once DNS + mailbox or forwarding are ready */
  contactEmail: "hollandomauricio@gmail.com",
  /** Optional: https://www.yourdomain.com — for your reference / future canonical use */
  publicSiteUrl: "",
  /**
   * Stripe Payment Links (test mode — recreate in live Dashboard for production revenue).
   */
  stripePaymentLinks: {
    starter: "https://buy.stripe.com/test_00w7sKfxB5P08Lkdemcs800",
    growth: "https://buy.stripe.com/test_bJe9ASdpt6T4f9I1vEcs801",
    scale: "https://buy.stripe.com/test_28EcN4gBFgtE1iS1vEcs802",
  },
};
