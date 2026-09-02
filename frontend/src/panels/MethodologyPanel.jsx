import { Card } from "../components/ui.jsx";

export function MethodologyPanel() {
  return (
    <>
      <Card title="How PitchMetric's predictions work">
        <p className="hint" style={{ marginTop: 0 }}>
          A plain description of the actual model behind every predicted-points number on this
          site — no black box, and no claim of more sophistication than what's really running.
        </p>

        <p className="section-heading">Team strength ratings</p>
        <p className="summary-line">
          Each team gets an attack and defense rating, fit directly from real match results —
          not derived from bookmaker odds. For a fixture between a home team and an away team,
          expected goals for each side come from a Poisson model: the home side's expected goals
          are a function of their attack rating, the away side's defense rating, and a home-
          advantage term; the away side's expected goals mirror that without the home term.
          Ratings are fit by maximizing the (recency-weighted) likelihood of the season's actual
          results so far — recent matches count for more than early-season ones.
        </p>

        <p className="section-heading">Early season: blending in previous seasons</p>
        <p className="summary-line">
          A handful of gameweeks isn't enough match data to fit reliable team ratings. Until the
          current season has enough finished matches, the model blends in the previous two
          seasons' results as well, shifting weight toward the current season as more of it is
          actually played. This is also the biggest source of noisy predictions early in a
          season — small samples produce more volatile ratings, and predicted-points numbers can
          swing more than they will once a fuller season's data is in.
        </p>

        <p className="section-heading">From team goals to player points</p>
        <p className="summary-line">
          Given a fixture's expected goals for a player's team, and their real share of that
          team's goals and assists this season (from actual per-match history, not a guess),
          the official FPL classic scoring table converts that into expected points: goals,
          assists, clean sheets, appearance points, and the rest, weighted by an estimated
          probability of actually playing meaningful minutes. A player's own observed output
          always overrides an assumed rate — someone with zero starts this season gets 0.0 for a
          rate rather than a rate inflated by leftover stats from before a reset.
        </p>

        <p className="section-heading">Opponent-specific history</p>
        <p className="summary-line">
          Each predicted-points number is nudged by how that specific player has actually
          performed against their upcoming opponent over the last 5 Premier League seasons, both
          overall and specifically since joining their current club. That adjustment is shrunk
          toward the player's real overall average the fewer head-to-head matches exist — a
          player with one game against an opponent doesn't get judged purely on that one game,
          it's blended with their broader level of form.
        </p>

        <p className="section-heading">Known limitations</p>
        <ul className="flags">
          <li>Predictions are a statistical model — Poisson-distributed expected goals and a
            points formula — not a machine-learning or AI system.</li>
          <li>Early-season predictions carry more uncertainty than mid-to-late-season ones, for
            the reasons above.</li>
          <li>Squad-optimizer tools (Wildcard/Free Hit lifts, Squad Builder) show the true
            mathematical optimum under the model's own numbers — when those numbers are still
            volatile early in a season, the "optimal" squad it finds can look extreme. Treat it
            as a upper-bound estimate on that day's model, not investment advice.</li>
          <li>Player availability (rotation risk, late fitness calls) is estimated from FPL's own
            published status, not insider information — always check the live status flags
            before a deadline.</li>
        </ul>
      </Card>
    </>
  );
}
