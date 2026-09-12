import { useEffect, useState } from "react";
import { api } from "../api.js";
import { Button, Card, ErrorBanner, fetchSlugManifest, Field } from "../components/ui.jsx";

// Resolves a free-typed name against the full player list -- exact match first, then substring,
// same fallback order as the backend's own match_player_names (services/fpl_service.py) uses for
// manual-squad entry.
function resolvePlayer(query, players) {
  const q = query.trim().toLowerCase();
  if (!q) return null;
  const exact = players.find((p) => p.name.toLowerCase() === q);
  if (exact) return exact;
  const partial = players.find((p) => p.name.toLowerCase().includes(q));
  return partial ?? null;
}

// This tab is deliberately just a search box, not its own player-card UI: the real player
// page (/fpl/player/<slug>/ -- price, latest stats, stat radar, forward predictions) already
// exists as a real static page (scripts/build-static-pages.mjs), the same one every PlayerTip
// popup links out to elsewhere in the app. Rendering a second, thinner card here would mean two
// designs to keep in sync for the same player -- a real navigation to that same page keeps it
// unified across the whole site instead.
export function PlayerInfoPanel() {
  const [players, setPlayers] = useState([]);
  const [query, setQuery] = useState("");
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.get("/fpl/players").then(setPlayers).catch(() => {});
  }, []);

  const goToPlayer = async () => {
    setError(null);
    const player = resolvePlayer(query, players);
    if (!player) {
      setError(`No player matches "${query}".`);
      return;
    }
    setLoading(true);
    const manifest = await fetchSlugManifest();
    setLoading(false);
    const slug = manifest[player.id];
    if (!slug) {
      setError(`${player.name}'s page isn't available yet -- static player pages are only built at deploy time.`);
      return;
    }
    window.location.href = `/fpl/player/${slug}/`;
  };

  return (
    <Card
      title="Player Info"
      hint="Search any player to open their full page — price, latest stats, stat radar, and predicted points gameweek-by-gameweek."
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
            onKeyDown={(e) => e.key === "Enter" && goToPlayer()}
          />
        </Field>
        <Button onClick={goToPlayer} disabled={loading || !query.trim()}>
          {loading ? "Finding…" : "Go to player page"}
        </Button>
      </div>
      <ErrorBanner error={error} />
    </Card>
  );
}
