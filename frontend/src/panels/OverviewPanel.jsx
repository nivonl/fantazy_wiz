import { useEffect } from "react";
import { api } from "../api.js";
import { Button, Card, ErrorBanner, PlayerTip, Reveal, SignedValue, Spinner, useAsyncAction } from "../components/ui.jsx";
import { Sparkline } from "../components/Sparkline.jsx";
import { FixtureDifficultyTicker } from "../components/FixtureDifficultyTicker.jsx";

// `squad` is the shared identity from useMySquadIdentity() (App.jsx) — entered once on the
// Squad tab, reused here so Overview reflects the same team without asking again.
export function OverviewPanel({ squad, onGoToSquad }) {
  const [state, run] = useAsyncAction();

  const load = () => {
    run(async () => {
      const params = squad.isConfigured ? squad.toParams() : new URLSearchParams();
      return api.get(`/fpl/overview?${params.toString()}`);
    });
  };

  // Load once on mount, and again whenever the squad identity actually changes (e.g. you just
  // set your entry ID on the Squad tab and come back here).
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [squad.mode, squad.entryId, squad.players]);

  const data = state.data;

  return (
    <>
      <Card title="Weekly Insights" hint="A quick glance — deeper multi-gameweek analysis and chip lifts live in Insights.">
        {!squad.isConfigured && (
          <p className="hint" style={{ marginTop: -6 }}>
            Showing general top-candidate insights. <a href="#" onClick={(e) => { e.preventDefault(); onGoToSquad(); }}>Set up your squad</a> in
            the Squad tab for personalized recommendations and season totals.
          </p>
        )}
        <div className="controls">
          <Button onClick={load} disabled={state.loading} variant="ghost">
            {state.loading ? "Refreshing…" : "Refresh"}
          </Button>
        </div>

        {state.loading && <Spinner label="Fitting ratings, scoring candidates…" />}
        <ErrorBanner error={state.error} />

        {data && (
          <Reveal revealKey={JSON.stringify(data.team_totals) + data.top_players.length}>
            {data.unmatched_names?.length > 0 && (
              <p className="error-banner" style={{ marginBottom: 14 }}>
                Couldn't match: {data.unmatched_names.join(", ")}.
              </p>
            )}

            {data.team_totals && (
              <div className="stat-grid" style={{ marginBottom: 18 }}>
                <div className="stat-tile">
                  <div className="stat-label">Total points</div>
                  <div className="stat-value">{data.team_totals.total_points}</div>
                </div>
                <div className="stat-tile">
                  <div className="stat-label">Overall rank</div>
                  <div className="stat-value">{data.team_totals.overall_rank.toLocaleString()}</div>
                </div>
                <div className="stat-tile">
                  <div className="stat-label">This gameweek</div>
                  <div className="stat-value">{data.team_totals.event_points}</div>
                </div>
                <div className="stat-tile">
                  <div className="stat-label">Squad value</div>
                  <div className="stat-value">{data.team_totals.squad_value}m</div>
                </div>
              </div>
            )}

            {data.recommended_move && (
              <div className="hero-card">
                <span className="hero-badge">Recommended move</span>
                <div className="hero-move">
                  <PlayerTip player={data.recommended_move.out} />
                  <span className="hero-arrow">&rarr;</span>
                  <PlayerTip player={data.recommended_move.in} />
                </div>
                <div className="hero-gain">
                  <SignedValue value={data.recommended_move.xp_gain} suffix=" projected xP" /> this gameweek
                  {data.recommended_move.is_hit && " (costs a -4 hit)"}
                </div>
              </div>
            )}

            <p className="section-heading">Top players this week</p>
            <div className="top-players-list">
              {data.top_players.map((tp, i) => (
                <div className="top-player-row" key={tp.player.id}>
                  <span className="top-player-rank">{i + 1}</span>
                  <div className="top-player-info">
                    <div className="top-player-name">
                      <PlayerTip player={tp.player} />
                    </div>
                    <div className="top-player-meta">
                      {tp.player.team} · {tp.player.pos} · {tp.player.price.toFixed(1)}m
                    </div>
                  </div>
                  <Sparkline values={tp.recent_points} />
                  <span className="top-player-xp">{tp.player.xp.toFixed(1)}</span>
                </div>
              ))}
            </div>

            <p className="section-heading">Fixture difficulty</p>
            <FixtureDifficultyTicker team={data.fixture_run_team} fixtures={data.fixture_run} />
          </Reveal>
        )}
      </Card>
    </>
  );
}
