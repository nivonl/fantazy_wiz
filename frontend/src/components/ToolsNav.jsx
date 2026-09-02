import { Link } from "react-router-dom";

const LINKS = [
  { to: "/fpl-team-analyzer", label: "Team Analyzer" },
  { to: "/fpl-transfer-finder", label: "Transfer Finder" },
  { to: "/fpl-squad-builder", label: "Squad Builder" },
  { to: "/fpl-predictions", label: "Predictions" },
  { to: "/methodology", label: "Methodology" },
];

// Real <a href> links to every major page, present on every screen — Google should be able to
// reach any page through ordinary navigation, not just a sitemap, and this is the one place
// that guarantees every SPA tool route is reachable from every other one.
export function ToolsNav() {
  return (
    <nav className="tools-nav">
      {LINKS.map((l) => (
        <Link key={l.to} to={l.to}>
          {l.label}
        </Link>
      ))}
    </nav>
  );
}
