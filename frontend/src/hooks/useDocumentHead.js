import { useEffect } from "react";

const SITE_URL = "https://pitchmetricai.com";

function upsertMeta(attr, value, content) {
  let el = document.querySelector(`meta[${attr}="${value}"]`);
  if (!el) {
    el = document.createElement("meta");
    el.setAttribute(attr, value);
    document.head.appendChild(el);
  }
  el.setAttribute("content", content);
}

function upsertLink(rel, href) {
  let el = document.querySelector(`link[rel="${rel}"]`);
  if (!el) {
    el = document.createElement("link");
    el.setAttribute("rel", rel);
    document.head.appendChild(el);
  }
  el.setAttribute("href", href);
}

// Sets document.title + meta description + canonical + Open Graph tags on route change. No
// react-helmet-async dependency — this is a small, one-shot DOM write per navigation, not a
// component tree to reconcile. Google explicitly treats JS-set <head> content as fine for
// client-rendered routes (crawled/indexed on a slightly slower second pass), which is an
// acceptable tradeoff for these interactive tool pages — the actual SEO-volume pages (player
// and gameweek pages) are genuine static HTML instead, built by scripts/build-static-pages.mjs.
export function useDocumentHead({ title, description, path }) {
  useEffect(() => {
    const fullTitle = title ? `${title} | PitchMetric` : "PitchMetric";
    document.title = fullTitle;
    if (description) upsertMeta("name", "description", description);
    const canonical = `${SITE_URL}${path || ""}`;
    upsertLink("canonical", canonical);
    upsertMeta("property", "og:title", fullTitle);
    if (description) upsertMeta("property", "og:description", description);
    upsertMeta("property", "og:url", canonical);
    upsertMeta("property", "og:type", "website");
  }, [title, description, path]);
}

export { SITE_URL };
