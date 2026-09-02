import { PredictionsPanel } from "./PredictionsPanel.jsx";

// Split out from the old combined "Insights" tab into its own page/URL. The generated,
// gameweek-by-gameweek prediction pages (scripts/build-static-pages.mjs, one per gameweek,
// past ones kept forever) link back here as their canonical "current predictions" home.
export function PredictionsPage() {
  return <PredictionsPanel />;
}
