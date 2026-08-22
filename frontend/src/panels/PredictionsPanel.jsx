import { useState } from "react";
import { api } from "../api.js";
import { Button, Card, ErrorBanner, Field, Reveal, Spinner, useAsyncAction } from "../components/ui.jsx";
import { PredictionsTable } from "../components/PredictionsTable.jsx";

export function PredictionsPanel() {
  const [event, setEvent] = useState("");
  const [state, run] = useAsyncAction();

  const submit = () => {
    run(() => {
      const qs = event ? `?event=${encodeURIComponent(event)}` : "";
      return api.get(`/predict/fpl${qs}`);
    });
  };

  return (
    <Card
      title="Score predictions"
      hint="Fitted from real results this season (blends in the last 2 seasons via football-data.org until there's enough current-season data)."
    >
      <div className="controls">
        <Field label="Gameweek (optional)">
          <input type="number" min="1" placeholder="current" value={event} onChange={(e) => setEvent(e.target.value)} />
        </Field>
        <Button onClick={submit} disabled={state.loading}>
          {state.loading ? "Predicting…" : "Predict"}
        </Button>
      </div>
      <div className="output">
        {state.loading && <Spinner label="Fitting team ratings…" />}
        <ErrorBanner error={state.error} />
        {!state.loading && !state.error && !state.data && <p className="empty">Nothing loaded yet.</p>}
        {state.data && (
          <Reveal revealKey={state.data.length}>
            <PredictionsTable predictions={state.data} />
          </Reveal>
        )}
      </div>
    </Card>
  );
}
