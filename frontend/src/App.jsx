import { useState } from "react";
import "./App.css";
import { CurrentTeamPanel } from "./panels/CurrentTeamPanel.jsx";
import { TeamBuilderPanel } from "./panels/TeamBuilderPanel.jsx";
import { BuildSquadPanel } from "./panels/BuildSquadPanel.jsx";
import { PredictionsPanel } from "./panels/PredictionsPanel.jsx";
import { LaLigaPanel } from "./panels/LaLigaPanel.jsx";

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
  const [tab, setTab] = useState("fpl");

  return (
    <div className="app-shell">
      <header className="top">
        <div className="brand">
          <BrandMark />
          <h1>
            <span className="brand-pitch">Pitch</span>
            <span className="brand-metric">Metric</span>
          </h1>
        </div>
        <p>FPL &amp; La Liga analytics — score predictions and squad recommendations backed by real data.</p>
        <nav className="tabs">
          <button className={tab === "fpl" ? "active" : ""} onClick={() => setTab("fpl")}>
            Premier League (FPL)
          </button>
          <button className={tab === "laliga" ? "active" : ""} onClick={() => setTab("laliga")}>
            La Liga
          </button>
        </nav>
      </header>

      <main>
        {tab === "fpl" && (
          <div className="panel-fade" key="fpl">
            <CurrentTeamPanel />
            <TeamBuilderPanel />
            <BuildSquadPanel />
            <PredictionsPanel />
          </div>
        )}
        {tab === "laliga" && (
          <div className="panel-fade" key="laliga">
            <LaLigaPanel />
          </div>
        )}
      </main>
    </div>
  );
}
