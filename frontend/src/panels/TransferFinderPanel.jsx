import { useState } from "react";
import { api } from "../api.js";
import {
  Button,
  Card,
  ErrorBanner,
  Field,
  PlayerTip,
  Reveal,
  SnapshotHint,
  Spinner,
  useCachedAsyncAction,
} from "../components/ui.jsx";

const POSITION_ORDER = ["GK", "DEF", "MID", "FWD"];

function safeCacheKey(squad) {
  try {
    return squad.toParams().toString();
  } catch {
    return "unconfigured";
  }
}

// Standalone version of the per-position budget target finder that used to live only inside
// the Team Analyzer flow. Works with no squad configured at all (the backend tolerates an
// empty squad and just returns the best player at that price, market-wide) — if a squad IS
// configured on the Team Analyzer tab, results here automatically exclude players you own,
// since both tools read the same shared squad identity.
export function TransferFinderPanel({ squad }) {
  const [budget, setBudget] = useState(8.0);
  const cacheKey = `${safeCacheKey(squad)}|budget=${budget}`;
  const [state, run] = useCachedAsyncAction("transfer-finder", cacheKey);

  const findTargets = () => {
    run(async () => {
      let params;
      try {
        params = squad.toParams();
      } catch {
        params = new URLSearchParams(); // no squad configured — a plain market-wide lookup
      }
      params.set("budget", budget);
      return api.get(`/recommend/fpl/targets?${params.toString()}`);
    });
  };

  const targets = state.data;

  return (
    <Card
      title="FPL Transfer Finder"
      hint="For a given spend on a single incoming player, the best player at each position ranked by predicted points summed over the next few gameweeks. Enter your squad on the Team Analyzer tab first if you want players you already own excluded — otherwise this is a plain market-wide lookup."
    >
      <div className="controls">
        <Field label="Budget for the incoming player (£m)">
          <input type="number" step="0.1" min="0" value={budget} onChange={(e) => setBudget(e.target.value)} />
        </Field>
        <Button onClick={findTargets} disabled={state.loading}>
          {state.loading ? "Searching…" : "Find targets"}
        </Button>
        <SnapshotHint savedAt={state.savedAt} />
      </div>

      {state.loading && <Spinner label="Scoring the market…" />}
      <ErrorBanner error={state.error} />
      {!state.loading && !state.error && !targets && <p className="empty">Nothing loaded yet.</p>}

      {targets && (
        <Reveal revealKey={JSON.stringify(targets.targets)}>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Pos</th>
                  <th>Best target</th>
                  <th>Team</th>
                  <th>Price</th>
                  <th>Predicted pts ({targets.horizon_gameweeks} GWs)</th>
                </tr>
              </thead>
              <tbody>
                {POSITION_ORDER.map((pos) => {
                  const p = targets.targets[pos];
                  return (
                    <tr key={pos}>
                      <td>{pos}</td>
                      {p ? (
                        <>
                          <td><PlayerTip player={p} /></td>
                          <td>{p.team}</td>
                          <td>{p.price.toFixed(1)}m</td>
                          <td>{p.xp.toFixed(2)}</td>
                        </>
                      ) : (
                        <td colSpan={4} className="empty">
                          Nothing affordable at £{Number(budget).toFixed(1)}m
                        </td>
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Reveal>
      )}
    </Card>
  );
}
