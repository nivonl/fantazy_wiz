import { useState } from "react";
import "./App.css";
import { ThemeToggle, useMySquadIdentity, useTheme } from "./components/ui.jsx";
import { BottomNav } from "./components/BottomNav.jsx";
import { OverviewPanel } from "./panels/OverviewPanel.jsx";
import { CurrentTeamPanel } from "./panels/CurrentTeamPanel.jsx";
import { InsightsPanel } from "./panels/InsightsPanel.jsx";
import { MorePanel } from "./panels/MorePanel.jsx";

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

export default function App() {
  const [tab, setTab] = useState("overview");
  const squad = useMySquadIdentity();
  useTheme(); // applies the persisted data-theme attribute on mount and whenever it changes

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

      {/*
        Every panel stays mounted all the time (visibility is toggled with a CSS class, not
        conditional rendering) so switching tabs never unmounts a panel's React state — without
        this, coming back to a tab replayed its whole fetch (rating fit + ILP solve) from
        scratch every time, even though nothing about your squad or the gameweek had changed.
      */}
      <main>
        <div className={`panel-fade${tab === "overview" ? "" : " panel-hidden"}`}>
          <OverviewPanel squad={squad} onGoToSquad={() => setTab("squad")} />
        </div>
        <div className={`panel-fade${tab === "squad" ? "" : " panel-hidden"}`}>
          <CurrentTeamPanel squad={squad} />
        </div>
        <div className={`panel-fade${tab === "insights" ? "" : " panel-hidden"}`}>
          <InsightsPanel />
        </div>
        <div className={`panel-fade${tab === "more" ? "" : " panel-hidden"}`}>
          <MorePanel />
        </div>
      </main>

      <BottomNav active={tab} onChange={setTab} />
    </div>
  );
}
