import { Link } from "react-router-dom";
import { Card, ThemeToggle, useTheme } from "../components/ui.jsx";
import { LaLigaPanel } from "./LaLigaPanel.jsx";

export function MorePanel() {
  const [theme] = useTheme();
  return (
    <>
      <Card title="Settings">
        <div className="settings-row">
          <span>Appearance</span>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span className="hint" style={{ margin: 0 }}>{theme === "light" ? "Light" : "Dark"} mode</span>
            <ThemeToggle />
          </div>
        </div>
      </Card>
      <Card title="More on PitchMetric">
        <p className="summary-line" style={{ display: "flex", gap: 18, flexWrap: "wrap" }}>
          <Link to="/fpl-predictions">Score predictions</Link>
          <a href="/blog">Blog</a>
          <Link to="/methodology">How the model works</Link>
        </p>
      </Card>
      <p className="section-heading" style={{ margin: "4px 0 -8px 4px" }}>
        La Liga — same engine, lighter feature set (via 9cat.co.il)
      </p>
      <LaLigaPanel />
    </>
  );
}
