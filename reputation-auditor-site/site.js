(function () {
  var C = window.TRUST_AUDITOR_SITE || {};

  function setGithubLinks() {
    var gh = C.githubUrl;
    if (!gh || gh.indexOf("YOUR_ORG") !== -1) return;
    var base = gh.replace(/\/$/, "");
    document.querySelectorAll('a[data-role="github"]').forEach(function (el) {
      el.setAttribute("href", gh);
    });
    document.querySelectorAll('a[data-role="getting-started"]').forEach(function (el) {
      el.setAttribute("href", base + "/blob/main/docs/GETTING_STARTED.md");
    });
  }

  function setMailtos() {
    var em = C.contactEmail || "";
    if (!em) return;
    document.querySelectorAll('a[data-role="contact-email"]').forEach(function (el) {
      el.setAttribute("href", "mailto:" + em);
      if (el.getAttribute("data-show-address") !== "false") {
        el.textContent = em;
      }
    });
  }

  function wirePricingButtons() {
    var links = C.stripePaymentLinks || {};
    document.querySelectorAll("a[data-subscribe]").forEach(function (btn) {
      var tier = btn.getAttribute("data-subscribe");
      var url = links[tier];
      if (url) {
        btn.setAttribute("href", url);
        btn.setAttribute("target", "_blank");
        btn.setAttribute("rel", "noopener noreferrer");
        btn.textContent = "Subscribe with Stripe";
      } else {
        btn.setAttribute(
          "href",
          "mailto:" + (C.contactEmail || "") + "?subject=Trust%20Auditor%20—%20" + tier + "%20plan"
        );
        btn.textContent = "Contact to subscribe";
      }
    });
  }

  function demoVideo() {
    var holder = document.getElementById("demo-video-embed");
    if (!holder || !C.demoVideoEmbedUrl) return;
    var url = C.demoVideoEmbedUrl;
    if (url.indexOf("loom.com/share/") !== -1) {
      url = url.replace("share/", "embed/");
    }
    holder.innerHTML =
      '<div style="position:relative;padding-bottom:56.25%;height:0;border-radius:12px;overflow:hidden;border:1px solid #2d3a4d">' +
      '<iframe src="' +
      url.replace(/"/g, "&quot;") +
      '" style="position:absolute;top:0;left:0;width:100%;height:100%" allowfullscreen title="Demo video"></iframe></div>';
  }

  setGithubLinks();
  setMailtos();
  wirePricingButtons();
  demoVideo();
})();
