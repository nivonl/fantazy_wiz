// Tier 1 (easiest) -> 5 (hardest), derived server-side from the team's own predicted win
// probability in that fixture (models/predict.py), not a separate invented metric.
const TIER_CLASS = { 1: "tier-1", 2: "tier-2", 3: "tier-3", 4: "tier-4", 5: "tier-5" };

export function FixtureDifficultyTicker({ team, fixtures }) {
  if (!fixtures || fixtures.length === 0) {
    return <p className="empty">No upcoming fixtures found{team ? ` for ${team}` : ""}.</p>;
  }
  return (
    <div>
      {team && <p className="summary-line" style={{ marginBottom: 8 }}>Fixture run — {team}</p>}
      <div className="fixture-ticker">
        {fixtures.map((f) => (
          <div className={`fixture-chip ${TIER_CLASS[f.tier] || "tier-3"}`} key={f.event} title={`${(f.win_prob * 100).toFixed(0)}% win probability`}>
            <span className="fixture-opponent">{f.opponent}</span>
            <span className="fixture-venue">{f.is_home ? "H" : "A"}</span>
          </div>
        ))}
      </div>
      <div className="fixture-legend">
        <span>Easy</span>
        <span className="fixture-legend-bar" />
        <span>Hard</span>
      </div>
    </div>
  );
}
