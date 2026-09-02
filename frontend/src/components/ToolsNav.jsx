import { Link, useLocation } from "react-router-dom";
import { NAV_ITEMS, TOP_NAV_KEYS } from "../nav-items.js";

const LINKS = TOP_NAV_KEYS.map((key) => NAV_ITEMS.find((item) => item.key === key));

// Desktop-only (hidden on mobile via CSS, see App.css — the bottom nav is primary there).
// Real <a href> links to every major page, present on every screen, so Google can reach any
// page through ordinary navigation rather than needing a sitemap, and so a desktop visitor has
// a normal top nav instead of a mobile-style bottom bar wasting vertical space.
export function ToolsNav() {
  const { pathname } = useLocation();
  return (
    <nav className="tools-nav">
      {LINKS.map((l) => (
        <Link key={l.key} to={l.path} className={pathname === l.path ? "active" : ""}>
          {l.label}
        </Link>
      ))}
    </nav>
  );
}
