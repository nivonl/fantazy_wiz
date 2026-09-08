// Must match src/hooks/useDocumentHead.js's SITE_URL -- duplicated rather than imported since
// this is a plain Node build script, not part of the client bundle.
//
// www, not the bare apex -- GoDaddy (where this domain's DNS is managed) doesn't allow a CNAME
// record at the root, so the apex just 301-redirects to www via GoDaddy's domain forwarding
// rather than pointing at Railway directly. www is the actual serving domain and the one every
// canonical/OG/sitemap URL needs to agree on.
export const SITE_URL = "https://www.pitchmetricai.com";

const NAV_LINKS = [
  { href: "/fpl-team-analyzer", label: "Team Analyzer" },
  { href: "/fpl-transfer-finder", label: "Transfer Finder" },
  { href: "/fpl-squad-builder", label: "Squad Builder" },
  { href: "/fpl-predictions", label: "Predictions" },
  { href: "/blog/", label: "Blog" },
  { href: "/methodology", label: "Methodology" },
];

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function escapeJsonForScriptTag(json) {
  // Prevents a literal "</script" inside JSON-LD data from prematurely closing the tag.
  return json.replace(/</g, "\\u003c");
}

/**
 * Renders one static, self-contained HTML page: title/description/canonical/OG tags, basic
 * JSON-LD (WebSite/Organization/BreadcrumbList -- deliberately no FAQ schema, since Google
 * discontinued FAQ rich results), the same nav chrome as the SPA shell (real <a href> links,
 * not JS-only navigation), and whatever `bodyHtml` the caller built for the actual content.
 * No JS/hydration required to see any of it.
 */
export function renderPage({ title, description, path, bodyHtml, cssHref, breadcrumbs, cardStyle, ogType = "website", extraJsonLd = [] }) {
  const fullTitle = `${title} | PitchMetric`;
  const canonical = `${SITE_URL}${path}`;
  const jsonLd = [
    {
      "@context": "https://schema.org",
      "@type": "WebSite",
      name: "PitchMetric",
      url: SITE_URL,
    },
    {
      "@context": "https://schema.org",
      "@type": "Organization",
      name: "PitchMetric",
      url: SITE_URL,
    },
    ...extraJsonLd,
  ];
  if (breadcrumbs?.length) {
    jsonLd.push({
      "@context": "https://schema.org",
      "@type": "BreadcrumbList",
      itemListElement: breadcrumbs.map((b, i) => ({
        "@type": "ListItem",
        position: i + 1,
        name: b.name,
        item: `${SITE_URL}${b.path}`,
      })),
    });
  }

  return `<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <meta name="theme-color" content="#170021" />
    <title>${escapeHtml(fullTitle)}</title>
    <meta name="description" content="${escapeHtml(description)}" />
    <link rel="canonical" href="${canonical}" />
    <meta property="og:title" content="${escapeHtml(fullTitle)}" />
    <meta property="og:description" content="${escapeHtml(description)}" />
    <meta property="og:url" content="${canonical}" />
    <meta property="og:type" content="${ogType}" />
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link
      rel="stylesheet"
      href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;700;800&family=Work+Sans:wght@400;500;600&display=swap"
    />
    <link rel="stylesheet" crossorigin href="${cssHref}" />
    <script type="application/ld+json">${escapeJsonForScriptTag(JSON.stringify(jsonLd))}</script>
  </head>
  <body>
    <div class="app-shell">
      <header class="top">
        <div class="brand-bar">
          <div class="brand">
            <span class="brand-mark">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                <circle cx="10" cy="10" r="6.5" stroke="var(--text)" stroke-width="2" />
                <line x1="14.8" y1="14.8" x2="20" y2="20" stroke="var(--accent)" stroke-width="2.2" stroke-linecap="round" />
              </svg>
            </span>
            <h1><span class="brand-pitch">Pitch</span><span class="brand-metric">Metric</span></h1>
          </div>
          <a href="/" style="color:var(--text-dim); font-size:0.8rem;">Home</a>
        </div>
        <p>FPL &amp; La Liga analytics — score predictions and squad recommendations backed by real data.</p>
        <nav class="tools-nav">
          ${NAV_LINKS.map((l) => `<a href="${l.href}">${escapeHtml(l.label)}</a>`).join("\n          ")}
        </nav>
      </header>
      <main>
        <div class="panel-fade">
          <section class="card"${cardStyle ? ` style="${cardStyle}"` : ""}>
            ${bodyHtml}
          </section>
        </div>
      </main>
    </div>
    <script>${CHART_TOOLTIP_SCRIPT}${SHARE_SCRIPT}${FILTER_SCRIPT}</script>
  </body>
</html>
`;
}

// Delegated hover (and tap, for touch) tooltip for any [data-tooltip] element -- currently the
// radar and price-history charts' invisible hit-circles (see charts/radarChart.js and
// scripts/lib/chart.mjs). One shared listener per page rather than per-chart, since a static
// page can have several charts and this needs no per-chart wiring. Deliberately JS-driven
// rather than relying on SVG's native <title> tooltip, which those charts still carry as a
// fallback but which proved inconsistent to actually trigger on some real desktop browsers --
// same reasoning, and the same .chart-tooltip bubble styling, as components/ui.jsx's
// ChartTooltipHost (the equivalent for the SPA popup).
const CHART_TOOLTIP_SCRIPT = `
(function () {
  var bubble;
  function ensureBubble() {
    if (!bubble) {
      bubble = document.createElement("div");
      bubble.className = "hover-tooltip chart-tooltip";
      document.body.appendChild(bubble);
    }
    return bubble;
  }
  function show(el) {
    var text = el.getAttribute("data-tooltip");
    if (!text) return;
    var b = ensureBubble();
    b.textContent = text;
    b.style.display = "block";
    var rect = el.getBoundingClientRect();
    var margin = 8;
    var left = rect.left + rect.width / 2 - b.offsetWidth / 2;
    left = Math.max(margin, Math.min(left, window.innerWidth - b.offsetWidth - margin));
    var top = rect.top - b.offsetHeight - margin;
    if (top < margin) top = rect.bottom + margin;
    b.style.left = left + "px";
    b.style.top = top + "px";
  }
  function hide() {
    current = null;
    if (bubble) bubble.style.display = "none";
  }
  var current = null;
  document.addEventListener("mouseover", function (e) {
    var el = e.target.closest && e.target.closest("[data-tooltip]");
    if (el) {
      current = el;
      show(el);
    }
  });
  document.addEventListener("mouseout", function (e) {
    var el = e.target.closest && e.target.closest("[data-tooltip]");
    if (el) hide();
  });
  // mousemove as a second, more universally reliable path alongside mouseover/mouseout above --
  // some synthetic/automated input (and, per real reports, at least one real desktop setup)
  // never generates a mouseover event even though it does move the pointer, so relying on
  // mouseover alone left the tooltip genuinely unreachable there despite correct hit-testing.
  document.addEventListener("mousemove", function (e) {
    var el = e.target.closest && e.target.closest("[data-tooltip]");
    if (el && el !== current) {
      current = el;
      show(el);
    } else if (!el && current) {
      hide();
    }
  });
  document.addEventListener(
    "touchstart",
    function (e) {
      var el = e.target.closest && e.target.closest("[data-tooltip]");
      if (el) show(el);
    },
    { passive: true }
  );
})();
`;

// Delegated click handler for any [data-copy-url] button (currently the blog share bar's "Copy
// link" button -- see build-static-pages.mjs's renderShareBar). navigator.clipboard needs a
// secure context, which every real deployment of this site is (https); the try/catch falls back
// to a no-op rather than throwing on an old browser or a local non-https preview.
const SHARE_SCRIPT = `
(function () {
  document.addEventListener("click", function (e) {
    var el = e.target.closest && e.target.closest("[data-copy-url]");
    if (!el) return;
    var url = el.getAttribute("data-copy-url");
    var reset = function () {
      el.textContent = el.getAttribute("data-original-label") || "Copy link";
    };
    if (!el.getAttribute("data-original-label")) el.setAttribute("data-original-label", el.textContent);
    function done(ok) {
      el.textContent = ok ? "Copied!" : "Couldn't copy";
      setTimeout(reset, 1600);
    }
    try {
      navigator.clipboard.writeText(url).then(function () { done(true); }, function () { done(false); });
    } catch (err) {
      done(false);
    }
  });
})();
`;

// Delegated click handler for the blog index's filter bar (see build-static-pages.mjs's
// renderBlogIndexBody / FILTER_BUCKETS). Only present on /blog/, but registered globally like
// the two scripts above -- the closest() lookup is a no-op everywhere else. Toggling the .hidden
// property (not a class) matches this page skeleton's own [hidden]{display:none!important} reset.
const FILTER_SCRIPT = `
(function () {
  document.addEventListener("click", function (e) {
    var btn = e.target.closest && e.target.closest("[data-filter-btn]");
    if (!btn) return;
    var bar = btn.closest(".blog-filter-bar");
    var grid = document.querySelector(".blog-index-grid");
    if (!bar || !grid) return;
    var key = btn.getAttribute("data-filter-btn");
    Array.prototype.forEach.call(bar.querySelectorAll("[data-filter-btn]"), function (b) {
      b.classList.toggle("is-active", b === btn);
    });
    Array.prototype.forEach.call(grid.querySelectorAll(".blog-index-card"), function (card) {
      card.hidden = key !== "all" && card.getAttribute("data-filter-key") !== key;
    });
  });
})();
`;
