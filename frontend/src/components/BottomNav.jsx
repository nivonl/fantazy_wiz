import { Link, useLocation } from "react-router-dom";
import { NAV_ITEMS, BOTTOM_NAV_KEYS } from "../nav-items.js";

const ICONS = {
  overview: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="7" height="9" rx="1.5" />
      <rect x="14" y="3" width="7" height="5" rx="1.5" />
      <rect x="14" y="12" width="7" height="9" rx="1.5" />
      <rect x="3" y="16" width="7" height="5" rx="1.5" />
    </svg>
  ),
  analyzer: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="9" cy="8" r="3.2" />
      <path d="M3.5 20c0-3.3 2.5-5.5 5.5-5.5s5.5 2.2 5.5 5.5" />
      <circle cx="17" cy="8" r="2.4" opacity="0.7" />
      <path d="M15.5 14.6c2.7 0.3 4.5 2.2 4.9 5.4" opacity="0.7" />
    </svg>
  ),
  transfer: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M17 3l4 4-4 4" />
      <path d="M21 7H9" />
      <path d="M7 21l-4-4 4-4" />
      <path d="M3 17h12" />
    </svg>
  ),
  builder: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 3a6.5 6.5 0 0 0-3.6 11.9c.4.3.6.8.6 1.3V17h6v-.8c0-.5.2-1 .6-1.3A6.5 6.5 0 0 0 12 3Z" />
      <path d="M9.5 21h5" />
    </svg>
  ),
  more: (
    <svg viewBox="0 0 24 24" fill="currentColor">
      <circle cx="5" cy="12" r="1.8" />
      <circle cx="12" cy="12" r="1.8" />
      <circle cx="19" cy="12" r="1.8" />
    </svg>
  ),
  blog: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="4" y="4" width="16" height="16" rx="2" />
      <line x1="8" y1="9" x2="16" y2="9" />
      <line x1="8" y1="13" x2="16" y2="13" />
      <line x1="8" y1="17" x2="12" y2="17" />
    </svg>
  ),
};

const TABS = BOTTOM_NAV_KEYS.map((key) => NAV_ITEMS.find((item) => item.key === key));

// Mobile-only (hidden on desktop via CSS, see App.css) — a curated subset of NAV_ITEMS, real
// <a href> navigation via react-router's Link, active state derived from the URL itself.
export function BottomNav() {
  const { pathname } = useLocation();
  return (
    <nav className="bottom-nav">
      {TABS.map((t) => (
        <Link key={t.key} to={t.path} className={`bottom-nav-item ${pathname === t.path ? "active" : ""}`}>
          {ICONS[t.key]}
          <span>{t.label}</span>
        </Link>
      ))}
      {/* Plain <a>, not <Link>: /blog is a real static page (scripts/build-static-pages.mjs),
          not one of App.jsx's always-mounted SPA panels -- same reasoning as the Blog link in
          ToolsNav.jsx. */}
      <a href="/blog" className={`bottom-nav-item ${pathname.startsWith("/blog") ? "active" : ""}`}>
        {ICONS.blog}
        <span>Blog</span>
      </a>
    </nav>
  );
}
