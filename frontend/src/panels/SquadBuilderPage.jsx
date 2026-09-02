import { TeamBuilderPanel } from "./TeamBuilderPanel.jsx";
import { BuildSquadPanel } from "./BuildSquadPanel.jsx";

// Two build-from-scratch squad optimizers: one shortlist-and-favorites-aware, one a plain
// optimal-15-under-budget solve. Split out from the old combined "Insights" tab into its own
// page/URL — was previously bundled with score predictions, now those live at /fpl-predictions.
export function SquadBuilderPage() {
  return (
    <>
      <TeamBuilderPanel />
      <BuildSquadPanel />
    </>
  );
}
