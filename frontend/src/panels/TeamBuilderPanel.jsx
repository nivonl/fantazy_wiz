import { useEffect, useState } from "react";
import { api } from "../api.js";
import { Button, Card, ErrorBanner, Field, Reveal, Spinner, useAsyncAction } from "../components/ui.jsx";
import { SquadTable } from "../components/SquadTable.jsx";

export function TeamBuilderPanel() {
  const [teams, setTeams] = useState([]);
  const [players, setPlayers] = useState([]);
  const [favoriteTeam, setFavoriteTeam] = useState("");
  const [minCount, setMinCount] = useState(3);
  const [favoritePlayers, setFavoritePlayers] = useState("");
  const [event, setEvent] = useState("");
  const [state, run] = useAsyncAction();

  useEffect(() => {
    api.get("/fpl/teams").then(setTeams).catch(() => {});
    api.get("/fpl/players").then(setPlayers).catch(() => {});
  }, []);

  const submit = () => {
    run(async () => {
      const params = new URLSearchParams();
      if (event) params.set("event", event);
      if (favoriteTeam) params.set("favorite_team", favoriteTeam);
      if (favoritePlayers.trim()) params.set("favorite_players", favoritePlayers.trim());
      if (minCount) params.set("min_favorite_team_count", minCount);
      return api.get(`/recommend/fpl/team-builder?${params.toString()}`);
    });
  };

  const result = state.data;

  return (
    <Card
      title="Team builder"
      hint="Builds around a shortlist of the best candidates (base model, already adjusted for opponent history). Pick a favorite club to require players from it, and/or name 1-2 players to lock into the squad."
    >
      <datalist id="team-list">
        {teams.map((t) => (
          <option value={t.name} key={t.id} />
        ))}
      </datalist>
      <datalist id="player-list">
        {players.map((p) => (
          <option value={p.name} key={p.id}>
            {p.name} — {p.team} ({p.pos})
          </option>
        ))}
      </datalist>

      <div className="controls">
        <Field label="Favorite club (optional)">
          <input list="team-list" placeholder="e.g. Arsenal" value={favoriteTeam} onChange={(e) => setFavoriteTeam(e.target.value)} />
        </Field>
        <Field label="Min. from that club">
          <input type="number" min="1" max="3" value={minCount} onChange={(e) => setMinCount(e.target.value)} />
        </Field>
        <Field label="Gameweek (optional)">
          <input type="number" min="1" placeholder="current" value={event} onChange={(e) => setEvent(e.target.value)} />
        </Field>
      </div>
      <div className="controls">
        <Field label="Favorite player(s), comma-separated">
          <input
            list="player-list"
            placeholder="e.g. Saka, Haaland"
            style={{ width: 320 }}
            value={favoritePlayers}
            onChange={(e) => setFavoritePlayers(e.target.value)}
          />
        </Field>
        <Button onClick={submit} disabled={state.loading}>
          {state.loading ? "Building…" : "Build my team"}
        </Button>
      </div>

      <div className="output">
        {state.loading && <Spinner label="Shortlisting candidates, optimizing squad…" />}
        <ErrorBanner error={state.error} />
        {!state.loading && !state.error && !result && <p className="empty">Nothing loaded yet.</p>}
        {result && (
          <Reveal revealKey={result.total_price}>
            <p className="summary-line">
              {result.favorite_team && (
                <>
                  At least {minCount} from <b>{result.favorite_team}</b>.{" "}
                </>
              )}
              {result.favorite_players_matched.length > 0 && (
                <>
                  Locked in: <b>{result.favorite_players_matched.join(", ")}</b>.{" "}
                </>
              )}
              {result.favorite_players_unmatched.length > 0 && (
                <span className="value-negative">Couldn't match: {result.favorite_players_unmatched.join(", ")}. </span>
              )}
              Considered {result.shortlisted_count} shortlisted candidates.
            </p>
            <p className="summary-line">
              Squad total <b>{result.total_price}m</b> · Starting XI xP <b>{result.starting_xp}</b>
            </p>
            <SquadTable
              title="Starting XI"
              players={[...result.starters].sort((a, b) => b.xp - a.xp)}
              captainId={result.captain.id}
              viceId={result.vice_captain.id}
              injuryNotes={result.injury_notes}
            />
            <SquadTable title="Bench" players={result.bench} injuryNotes={result.injury_notes} />
          </Reveal>
        )}
      </div>
    </Card>
  );
}
