import { useLocation, useNavigate } from "react-router-dom";
import "./App.css";
import { ThemeToggle, useMySquadIdentity, useTheme } from "./components/ui.jsx";
import { BottomNav } from "./components/BottomNav.jsx";
import { ToolsNav } from "./components/ToolsNav.jsx";
import { useDocumentHead } from "./hooks/useDocumentHead.js";
import { OverviewPanel } from "./panels/OverviewPanel.jsx";
import { CurrentTeamPanel } from "./panels/CurrentTeamPanel.jsx";
import { TransferFinderPanel } from "./panels/TransferFinderPanel.jsx";
import { SquadBuilderPage } from "./panels/SquadBuilderPage.jsx";
import { PredictionsPage } from "./panels/PredictionsPage.jsx";
import { MethodologyPanel } from "./panels/MethodologyPanel.jsx";
import { MorePanel } from "./panels/MorePanel.jsx";

// One <title>/description per real route — read by useDocumentHead below. Kept centralized
// here (rather than each panel calling useDocumentHead itself) because every panel stays
// mounted all the time (see the comment on <main> below): if each panel set its own head tags
// unconditionally, whichever rendered last would win, not necessarily the visible one.
const ROUTE_META = {
  "/": {
    title: "FPL & La Liga Fantasy Football Analytics",
    description:
      "Free FPL squad recommendations, transfer suggestions, and match score predictions backed by real statistical models — no login required.",
  },
  "/fpl-team-analyzer": {
    title: "FPL Team Analyzer & Transfer Recommendations",
    description:
      "Enter your FPL team and get your captain pick, best transfer, chip advice, and live risk flags — all backed by real predicted points.",
  },
  "/fpl-transfer-finder": {
    title: "FPL Transfer Finder",
    description:
      "Find the best affordable FPL player at each position for any budget, ranked by predicted points over the next few gameweeks.",
  },
  "/fpl-squad-builder": {
    title: "FPL Squad Builder",
    description:
      "Build the optimal 15-player FPL squad from scratch under the 100m budget, with favorite-team and favorite-player constraints.",
  },
  "/fpl-predictions": {
    title: "FPL & Premier League Score Predictions",
    description:
      "Match score predictions for the latest Premier League gameweek, from a Poisson attack/defense model fit on real results.",
  },
  "/methodology": {
    title: "Methodology",
    description: "How PitchMetric's team ratings and player expected-points predictions actually work.",
  },
  "/more": {
    title: "Settings",
    description: "Theme settings and La Liga fantasy recommendations.",
  },
};

function BrandMark() {
  return (
    <span className="brand-mark">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
        <circle cx="10" cy="10" r="6.5" stroke="#04F5FF" strokeWidth="2" />
        <line x1="14.8" y1="14.8" x2="20" y2="20" stroke="#963CFF" strokeWidth="2.2" strokeLinecap="round" />
      </svg>
    </span>
  );
}

function panelClass(active) {
  return `panel-fade${active ? "" : " panel-hidden"}`;
}

export default function App() {
  const location = useLocation();
  const navigate = useNavigate();
  const path = location.pathname;
  const squad = useMySquadIdentity();
  useTheme(); // applies the persisted data-theme attribute on mount and whenever it changes

  const meta = ROUTE_META[path] || ROUTE_META["/"];
  useDocumentHead({ title: meta.title, description: meta.description, path });

  return (
    <div className="app-shell">
      <header className="top">
        <div className="brand-bar">
          <div className="brand">
            <BrandMark />
            <h1>
              <span className="brand-pitch">Pitch</span>
              <span className="brand-metric">Metric</span>
            </h1>
          </div>
          <ThemeToggle />
        </div>
        <p>FPL &amp; La Liga analytics — score predictions and squad recommendations backed by real data.</p>
      </header>

      <ToolsNav />

      {/*
        Every panel stays mounted all the time (visibility is toggled with a CSS class, not
        conditional rendering) so navigating between pages never unmounts a panel's React state
        — without this, coming back to a page replayed its whole fetch (rating fit + ILP solve)
        from scratch every time, even though nothing about your squad or the gameweek had
        changed. Real URLs are layered on top via react-router (useLocation/useNavigate/Link)
        purely for addressability and SEO — <Routes>/<Route> are deliberately NOT used here,
        since those unmount whatever doesn't match.
      */}
      <main>
        <div className={panelClass(path === "/")}>
          <OverviewPanel squad={squad} onGoToSquad={() => navigate("/fpl-team-analyzer")} />
        </div>
        <div className={panelClass(path === "/fpl-team-analyzer")}>
          <CurrentTeamPanel squad={squad} />
        </div>
        <div className={panelClass(path === "/fpl-transfer-finder")}>
          <TransferFinderPanel squad={squad} />
        </div>
        <div className={panelClass(path === "/fpl-squad-builder")}>
          <SquadBuilderPage />
        </div>
        <div className={panelClass(path === "/fpl-predictions")}>
          <PredictionsPage />
        </div>
        <div className={panelClass(path === "/methodology")}>
          <MethodologyPanel />
        </div>
        <div className={panelClass(path === "/more")}>
          <MorePanel />
        </div>
      </main>

      <BottomNav />
    </div>
  );
}
