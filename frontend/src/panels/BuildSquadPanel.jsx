import { api } from "../api.js";
import { Button, Card, ErrorBanner, Reveal, Spinner, useAsyncAction } from "../components/ui.jsx";
import { SquadTable } from "../components/SquadTable.jsx";

export function BuildSquadPanel() {
  const [state, run] = useAsyncAction();
  const result = state.data;

  return (
    <Card title="Build a squad from scratch" hint="Optimal 15 under the 100m budget, valid formation, max 3 per club — no favorites applied.">
      <div className="controls">
        <Button onClick={() => run(() => api.get("/recommend/fpl/build"))} disabled={state.loading}>
          {state.loading ? "Building…" : "Build squad"}
        </Button>
      </div>
      <div className="output">
        {state.loading && <Spinner label="Optimizing 587 players against budget/formation…" />}
        <ErrorBanner error={state.error} />
        {!state.loading && !state.error && !result && <p className="empty">Nothing loaded yet.</p>}
        {result && (
          <Reveal revealKey={result.total_price}>
            <p className="summary-line">
              Squad total <b>{result.total_price}m</b> · Starting XI xP <b>{result.starting_xp}</b>
            </p>
            <SquadTable
              title="Starting XI"
              players={[...result.starters].sort((a, b) => b.xp - a.xp)}
              captainId={result.captain.id}
              viceId={result.vice_captain.id}
            />
            <SquadTable title="Bench" players={result.bench} />
          </Reveal>
        )}
      </div>
    </Card>
  );
}
