# Model improvement notes (from the blog's Gameweek 1 & 2 "surprise" posts)

Internal only — not linked from the site, not published. Written while building the blog's
gameweek-surprise posts (see `frontend/data/blog/posts.json`), which required re-running the
real prediction pipeline (`fit_ratings` / `predict_fixture` / `player_xp`, timed to only see
data available before each gameweek) against real Gameweek 1 and 2 results. That backtest
surfaced a specific, recurring failure mode worth fixing. Captured here for when we pick this up.

## The core problem: player-level rates have no memory across seasons, and no shrinkage

`fpl_service._player_rates()` computes a player's goal/assist rate for the model purely from
`goals_scored / starts` and `assists_scored / starts` **this season, this club**. Two consequences,
both visible in the actual GW1/GW2 data:

1. **No prior-season carryover.** A player with zero starts this season gets a hard `0.0` rate —
   deliberately, per the existing code comment ("someone with zero starts this season gets 0.0 for
   a rate rather than a rate inflated by leftover stats from before a reset"). That's correct for
   avoiding *stale* stats, but it means a five-season veteran and a completely unproven rookie are
   statistically identical the moment either one has a quiet game. Concretely: **Bruno Fernandes**
   played all 90 minutes of Gameweek 1, didn't score or assist, and Gameweek 2's prediction for him
   was 2.14 points — barely above a squad player's floor, despite being a 12.0m-priced player and
   one of the league's most productive playmakers for years. The team-rating side of the model
   already blends in previous seasons' results early in a season (`fit_pl_ratings`'s football-data
   fallback); the player-rate side has no equivalent at all.

2. **No shrinkage on small samples.** The flip side of the same gap: **Maxim De Cuyper** scored his
   only shot of Gameweek 1 (1 goal from 1 start — a literal 100% share of Brighton's expected goals
   under `goal_share`'s cap). Gameweek 2's prediction for him wasn't a moderate bump — it was 16.66
   predicted points, higher than anyone's actual Gameweek 2 total in either week's top 5. He
   returned a blank. A rate estimated from one match got zero regularization pulling it back toward
   a sane baseline.

3. **Worse than "no data": *discarded* data.** `_player_rates()` returns `(0.0, 0.0, start_prob)`
   whenever `starts == 0`, full stop — even if the player has real, current-season minutes and
   product from substitute appearances. **Rayan Cherki** came on as a substitute in Gameweek 1 (27
   minutes) and recorded 2 assists — genuinely useful signal that he could contribute directly to
   goals. Because those 27 minutes were as a sub, not a start, the model treated him going into
   Gameweek 2 exactly like an untested academy player it had literally never seen (predicted 0.74
   points, the lowest of either week's top 5). This is the sharpest case of the three: it's not a
   data-availability problem, it's a rule actively throwing away data the pipeline already fetched.

## Recommendation

Apply the same empirical-Bayes shrinkage the model already uses one layer up — `services/
opponent_history.py`'s `shrinkage_factor()` blends a player's record against a specific opponent
with their overall average, weighted by how many head-to-head games exist (`PRIOR_WEIGHT = 3.0`
"games" of evidence for the prior). The same technique belongs on the base `goal_share`/
`assist_share` calculation itself, roughly:

- Prior: last season's per-90 goal/assist rate (or a multi-season career rate, or a position-
  average for a player new to the league entirely, e.g. Cherki/De Cuyper — both had zero PL
  history for a different reason than Bruno's blank GW1: they simply hadn't played in this league
  before).
- Evidence: this season's rate, weighted by minutes played (not gated to `starts == 0` — a
  substitute's minutes and output should count for *something*, just less than a starter's).
  `PRIOR_WEIGHT`-style blending naturally handles both the "zero minutes yet" case (prior dominates)
  and the "one huge start" case (prior still pulls it back) without needing De Cuyper's current hard
  cap at `goal_share <= 1.0` to do all the work by itself.
- The existing `UNPROVEN_PLAYER_START_PROB_CAP` / `_is_backup_goalkeeper` machinery already does
  something similar for *playing time* uncertainty; this would be the same idea applied to
  *scoring-rate* uncertainty.

Net effect: Gameweek 1 predictions stop being a near-flat floor for the whole league (established
players keep some of their known quality; genuine unknowns stay near the floor), and no single
match — start or substitute appearance — should ever be able to swing a prediction as far as
De Cuyper's 16.66 or Cherki's 0.74 did.
