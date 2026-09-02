// One canonical list of every real page, shared by the desktop top nav and the mobile bottom
// nav so labels/destinations never drift apart between the two (they used to: "Squad" vs
// "Team Analyzer" pointed to the same page under two different names).
export const NAV_ITEMS = [
  { key: "overview", path: "/", label: "Overview" },
  { key: "analyzer", path: "/fpl-team-analyzer", label: "Team Analyzer" },
  { key: "transfer", path: "/fpl-transfer-finder", label: "Transfer Finder" },
  { key: "builder", path: "/fpl-squad-builder", label: "Squad Builder" },
  { key: "predictions", path: "/fpl-predictions", label: "Predictions" },
  { key: "methodology", path: "/methodology", label: "Methodology" },
  { key: "more", path: "/more", label: "More" },
];

// The bottom nav (mobile, thumb-reach) only has room for a handful of icons -- these are the
// highest-frequency destinations; Predictions/Methodology stay reachable via the desktop top
// nav, via content cross-links (every player/gameweek page links to both), and via quick links
// on the More page.
export const BOTTOM_NAV_KEYS = ["overview", "analyzer", "transfer", "builder", "more"];

// Everything except Overview shows in the desktop top nav -- Overview is already one click away
// via the brand logo, which links home.
export const TOP_NAV_KEYS = ["analyzer", "transfer", "builder", "predictions", "methodology", "more"];
