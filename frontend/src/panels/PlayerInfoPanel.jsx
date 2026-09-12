import { useEffect, useState } from "react";
import { api } from "../api.js";
import { Button, Card, ErrorBanner, Field, Reveal, Spinner, Tag, useAsyncAction } from "../components/ui.jsx";

const HORIZON_OPTIONS = [5, 10, 15];

// Resolves a free-typed name against the player list already fetched for the datalist -- exact
// match first, then substring, same fallback order as the backend's own match_player_names
// (services/fpl_service.py) uses for manual-squad entry, just done client-side here since this
// endpoint takes a numeric element id in the path, not a name.
function resolvePlayerId(query, players) {
  const q = query.trim().toLowerCase();
  if (!q) return null;
  const exact = players.find((p) => p.name.toLowerCase() === q);
  if (exact) return exact.id;
  const partial = players.find((p) => p.name.toLowerCase().includes(q));
  return partial ? partial.id : null;
}

export function PlayerInfoPanel() {
  const [players, setPlayers] = useState([]);
  const [query, setQuery] = useState("");
  const [horizon, setHorizon] = useState(5);
  const [state, run] = useAsyncAction();

  useEffect(() => {
    api.get("/fpl/players").then(setPlayers).catch(() => {});
  }, []);

  const search = (nextHorizon) => {
    const useHorizon = nextHorizon || horizon;
    const id = resolvePlayerId(query, players);
    if (id == null) {
      run(async () => {
        throw new Error(`No player matches "${query}".`);
      });
      return;
    }
    run(async () => api.get(`/fpl/player/${id}/card?num_gameweeks=${useHorizon}`));
  };

  const changeHorizon = (h) => {
    setHorizon(h);
    if (state.data) search(h);
  };

  const card = state.data;

  return (
    <Card
      title="Player Info"
      hint="Search any player for their card and predicted points gameweek-by-gameweek, out to however far ahead you want to look."
    >
      <datalist id="player-info-list">
        {players.map((p) => (
          <option value={p.name} key={p.id}>
            {p.name} — {p.team} ({p.pos})
          </option>
        ))}
      </datalist>
      <div className="controls">
        <Field label="Player">
          <input
            list="player-info-list"
            placeholder="e.g. Haaland"
            style={{ width: 260 }}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && search()}
          />
        </Field>
        <Button onClick={() => search()} disabled={state.loading || !query.trim()}>
          {state.loading ? "Searching…" : "Search"}
        </Button>
      </div>

      <div className="output">
        {state.loading && <Spinner label="Fitting ratings, projecting fixtures…" />}
        <ErrorBanner error={state.error} />
        {!state.loading && !state.error && !card && <p className="empty">Search a player to see their card.</p>}
        {card && (
          <Reveal revealKey={card.player.id + horizon}>
            <div className="hero-card">
              <p className="summary-line" style={{ marginTop: 0 }}>
                <b>{card.player.name}</b> · {card.player.team} · {card.player.pos} · {card.player.price.toFixed(1)}m
                {card.status && card.status !== "a" && <Tag variant="hit">{card.status}</Tag>}
              </p>
              {card.news && (
                <p className="hint" style={{ marginTop: -6 }}>
                  {card.news}
                </p>
              )}
              <div className="stat-grid" style={{ marginTop: 10 }}>
                <div className="stat-tile">
                  <div className="stat-label">Season points</div>
                  <div className="stat-value">{card.total_points ?? "—"}</div>
                </div>
                <div className="stat-tile">
                  <div className="stat-label">Ownership</div>
                  <div className="stat-value">{card.ownership_percent != null ? `${card.ownership_percent}%` : "—"}</div>
                </div>
                <div className="stat-tile">
                  <div className="stat-label">Next fixture xP</div>
                  <div className="stat-value">{card.projections[0] ? card.projections[0].xp.toFixed(2) : "—"}</div>
                </div>
              </div>
            </div>

            <p className="section-heading">Predicted points by gameweek</p>
            <div className="controls" style={{ marginBottom: 8 }}>
              {HORIZON_OPTIONS.map((h) => (
                <Button key={h} variant={h === horizon ? "primary" : "ghost"} onClick={() => changeHorizon(h)}>
                  Next {h}
                </Button>
              ))}
            </div>
            {card.projections.length === 0 ? (
              <p className="empty">No fixtures found in this window.</p>
            ) : (
              <ul className="flags">
                {card.projections.map((p) => (
                  <li key={p.event}>
                    GW{p.event} vs {p.opponent} — {p.xp.toFixed(2)} xP
                  </li>
                ))}
              </ul>
            )}
          </Reveal>
        )}
      </div>
    </Card>
  );
}
