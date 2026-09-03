// Must match src/hooks/useDocumentHead.js's SITE_URL -- duplicated rather than imported since
// this is a plain Node build script, not part of the client bundle.
export const SITE_URL = "https://pitchmetricai.com";

const NAV_LINKS = [
  { href: "/fpl-team-analyzer", label: "Team Analyzer" },
  { href: "/fpl-transfer-finder", label: "Transfer Finder" },
  { href: "/fpl-squad-builder", label: "Squad Builder" },
  { href: "/fpl-predictions", label: "Predictions" },
  { href: "/blog", label: "Blog" },
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
    <meta name="theme-color" content="#24002F" />
    <title>${escapeHtml(fullTitle)}</title>
    <meta name="description" content="${escapeHtml(description)}" />
    <link rel="canonical" href="${canonical}" />
    <meta property="og:title" content="${escapeHtml(fullTitle)}" />
    <meta property="og:description" content="${escapeHtml(description)}" />
    <meta property="og:url" content="${canonical}" />
    <meta property="og:type" content="${ogType}" />
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
                <circle cx="10" cy="10" r="6.5" stroke="#04F5FF" stroke-width="2" />
                <line x1="14.8" y1="14.8" x2="20" y2="20" stroke="#963CFF" stroke-width="2.2" stroke-linecap="round" />
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
  </body>
</html>
`;
}
