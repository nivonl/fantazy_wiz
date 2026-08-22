import { useState } from "react";
import { api } from "../api.js";
import { Button, Card, ErrorBanner, Field, Reveal, SignedValue, Spinner, useAsyncAction } from "../components/ui.jsx";
import { PredictionsTable } from "../components/PredictionsTable.jsx";

const SAMPLE_SQUAD = `{
  "bank": 0.5,
  "free_transfers": 1,
  "players": [
    {"name": "Example GK", "position": "GK", "team": "Real Madrid", "price": 5.0, "is_starter": true},
    {"name": "Example DEF", "position": "DEF", "team": "Barcelona", "price": 6.5, "is_starter": true},
    {"name": "Example MID", "position": "MID", "team": "Atletico Madrid", "price": 7.0, "is_starter": true,
     "goal_share": 0.1, "assist_share": 0.2, "start_prob": 0.9}
  ],
  "watchlist": [
    {"name": "Candidate MID", "position": "MID", "team": "Sevilla", "price": 7.5}
  ]
}`;

export function LaLigaPanel() {
  const [matchday, setMatchday] = useState("");
  const [predState, runPred] = useAsyncAction();

  const [squadJson, setSquadJson] = useState(SAMPLE_SQUAD);
  const [recState, runRec] = useAsyncAction();

  const submitPredict = () => {
    runPred(() => {
      const qs = matchday ? `?matchday=${encodeURIComponent(matchday)}` : "";
      return api.get(`/predict/laliga${qs}`);
    });
  };

  const submitRec = () => {
    runRec(() => {
      let squad;
      try {
        squad = JSON.parse(squadJson);
      } catch {
        throw new Error("Squad JSON doesn't parse — check for a stray comma or quote.");
      }
      return api.post("/recommend/laliga", squad);
    });
  };

  return (
    <>
      <Card
        title="Score predictions"
        hint="Fitted from football-data.org results (blends in last season early on). Needs FOOTBALL_DATA_TOKEN configured on the backend."
      >
        <div className="controls">
          <Field label="Matchday (optional)">
            <input type="number" min="1" placeholder="next" value={matchday} onChange={(e) => setMatchday(e.target.value)} />
          </Field>
          <Button onClick={submitPredict} disabled={predState.loading}>
            {predState.loading ? "Predicting…" : "Predict"}
          </Button>
        </div>
        <div className="output">
          {predState.loading && <Spinner label="Fitting team ratings…" />}
          <ErrorBanner error={predState.error} />
          {!predState.loading && !predState.error && !predState.data && <p className="empty">Nothing loaded yet.</p>}
          {predState.data && (
            <Reveal revealKey={predState.data.length}>
              <PredictionsTable predictions={predState.data} />
            </Reveal>
          )}
        </div>
      </Card>

      <Card
        title="Squad recommendation"
        hint={
          <>
            No live squad source yet for 9cat.co.il — paste your current squad below. <code>goal_share</code>/
            <code>assist_share</code>/<code>start_prob</code> are optional per player; leave them out unless you've actually
            researched that player this week. <code>watchlist</code> players are the only pool transfers can be suggested
            from.
          </>
        }
      >
        <Field label="Squad JSON">
          <textarea rows={12} value={squadJson} onChange={(e) => setSquadJson(e.target.value)} style={{ fontFamily: "var(--mono)" }} />
        </Field>
        <div className="controls">
          <Button onClick={submitRec} disabled={recState.loading}>
            {recState.loading ? "Working…" : "Get recommendation"}
          </Button>
        </div>
        <div className="output">
          {recState.loading && <Spinner label="Fitting ratings, scoring squad…" />}
          <ErrorBanner error={recState.error} />
          {!recState.loading && !recState.error && !recState.data && <p className="empty">Nothing loaded yet.</p>}
          {recState.data && (
            <Reveal revealKey={recState.data.captain?.name}>
              <p className="summary-line">
                Captain <b>{recState.data.captain.name}</b> (xP {recState.data.captain.xp.toFixed(2)})
              </p>
              {recState.data.transfer_flags.length === 0 ? (
                <p className="empty">No transfer flagged.</p>
              ) : (
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Consider out</th>
                        <th>Consider in</th>
                        <th>xP gain</th>
                        <th>Price delta</th>
                      </tr>
                    </thead>
                    <tbody>
                      {recState.data.transfer_flags.map((f, i) => (
                        <tr key={i}>
                          <td>
                            {f.out.name} ({f.out.pos})
                          </td>
                          <td>
                            {f.in.name} ({f.in.pos})
                          </td>
                          <td>
                            <SignedValue value={f.xp_gain} />
                          </td>
                          <td>
                            {f.price_delta >= 0 ? "+" : ""}
                            {f.price_delta}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Reveal>
          )}
        </div>
      </Card>
    </>
  );
}
