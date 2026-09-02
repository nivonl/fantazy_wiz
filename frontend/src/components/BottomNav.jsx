import { Link, useLocation } from "react-router-dom";

const ICONS = {
  overview: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="7" height="9" rx="1.5" />
      <rect x="14" y="3" width="7" height="5" rx="1.5" />
      <rect x="14" y="12" width="7" height="9" rx="1.5" />
      <rect x="3" y="16" width="7" height="5" rx="1.5" />
    </svg>
  ),
  squad: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="9" cy="8" r="3.2" />
      <path d="M3.5 20c0-3.3 2.5-5.5 5.5-5.5s5.5 2.2 5.5 5.5" />
      <circle cx="17" cy="8" r="2.4" opacity="0.7" />
      <path d="M15.5 14.6c2.7 0.3 4.5 2.2 4.9 5.4" opacity="0.7" />
    </svg>
  ),
  insights: (
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
};

const TABS = [
  { key: "overview", label: "Overview", path: "/" },
  { key: "squad", label: "Squad", path: "/fpl-team-analyzer" },
  { key: "insights", label: "Insights", path: "/fpl-squad-builder" },
  { key: "more", label: "More", path: "/more" },
];

// Real <a href> navigation (via react-router's Link), not click handlers over local state — the
// active tab is derived from the URL itself, driven by useLocation, so it stays in sync
// regardless of how a page was reached (a Link click, browser back/forward, or a bookmark).
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
    </nav>
  );
}
