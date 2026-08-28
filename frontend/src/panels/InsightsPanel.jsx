import { TeamBuilderPanel } from "./TeamBuilderPanel.jsx";
import { BuildSquadPanel } from "./BuildSquadPanel.jsx";
import { PredictionsPanel } from "./PredictionsPanel.jsx";

// Deeper, slower analysis than Overview's quick glance: build-from-scratch optimizers and
// score predictions, each a full request of its own rather than a dashboard summary.
export function InsightsPanel() {
  return (
    <>
      <TeamBuilderPanel />
      <BuildSquadPanel />
      <PredictionsPanel />
    </>
  );
}
