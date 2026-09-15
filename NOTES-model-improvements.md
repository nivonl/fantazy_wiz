# Model improvement notes (from the blog's Gameweek 1, 2 & 3 "surprise" posts)

**Status: implemented and backtested.** See `fantasy_app/services/fpl_service.py` —
`_fit_price_rate_priors` / `_player_rates` (price prior + minutes-weighted shrinkage, replacing
the old starts-only rate) and `_squad_depth_price_threshold` / `_is_priced_like_backup`
(price-implied rotation risk). Tests in `tests/test_fpl_service.py`. Documented for users on
`/methodology`. Internal only below — not linked from the site.

**Momentum was removed** after a full-season backtest (see "Backtest results" below) showed it
net-hurt accuracy for established players badly enough to erase most of the price prior's own
gain — a public, honest writeup of the whole backtest (including this) is the
`testing-the-price-and-squad-depth-update` Deep Research post. `_momentum_factor` no longer
exists in the codebase; don't reintroduce a `form`-vs-`points_per_game` multiplier without
re-testing it properly first.

## Backtest results (2025-26 season, full walk-forward + player-holdout cross-section)

Script: one-off, not committed (was in a scratchpad) — reran the real production functions
(`_fit_price_rate_priors`, `_player_rates`, the start-prob caps, `player_xp`) against every
gameweek of the completed 2025-26 season, predicting each from only the data available before it.

- **Overall**: ~3% lower mean absolute error than the old (starts-only, no price prior, no
  squad-depth) model, across all 37 testable gameweeks (~8,600 player-gameweek predictions,
  players with 30+ minutes).
- **By how much current-season history a player had**: monotonic and exactly where it should
  be — brand new (0 matches): ~15% error reduction. 1-2 matches: ~9%. 3-5 matches: ~4%. 6+
  matches (established): ~0.6%. The fade to near-zero for established players is the price
  prior correctly getting out of the way once real form exists, not a weakness.
- **Momentum ablation, established players only (6+ matches)**: price prior alone: ~2.1% error
  reduction. Price prior + momentum: **-2.7%** (error got *worse*). Momentum only barely
  mattered for cold-start players (not enough recent history for "recent vs. average" to mean
  anything yet) but was net-harmful for the ~90% of a season where most players are established
  — enough to flip the shipped model's established-player number from a gain to a loss before
  it was removed.
- **Player-holdout cross-section** (5-fold, players entirely excluded from fitting the price
  prior, scored only on the excluded fold, across 7 representative gameweeks): held-out-player
  MAE (2.329) was statistically indistinguishable from in-sample MAE (2.330) — the price prior
  generalizes to players it's never seen, not just the ones that happened to train it.

If this needs rerunning (a second season becomes available, or squad-depth/price-prior get
retuned), rebuild the same harness: walk-forward per gameweek using only prior-gameweek
cumulative stats, plus a k-fold player holdout on whichever population feeds a fitted prior.

Originally written while building the blog's gameweek-surprise posts (see
`frontend/data/blog/posts.json`), which required re-running the real prediction pipeline
(`fit_ratings` / `predict_fixture` / `player_xp`, timed to only see data available before each
gameweek) against real Gameweek 1 and 2 results. That backtest surfaced a specific, recurring
failure mode; the fix below also folds in the user's separate request to weight momentum,
current price, and squad depth into the core model, informed by the Deep Research team's
market-value study (`predicting-transfer-value` post) finding recent output is the stronger
fantasy-points signal whenever it actually exists — so price is used here as a cold-start
fallback prior, not a competitor to observed form.

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

## Gameweek 3 insights: a different failure mode — team-rating volatility, not player rates

**Status: implemented (early-season team L2 + committed harness).** Confirm live-season
fixture-λ MAE with `scripts/backtest_xp_walkforward.py` before retuning
`EARLY_SEASON_L2_BOOST`. Analysis below is kept as the motivating case study.

Re-ran the real production functions against GW3's five blog surprises (`_player_rates`,
`_is_unproven_this_season`, `_is_priced_like_backup`, `_is_backup_goalkeeper`, and — new this
time — `fit_pl_ratings`/`predict_fixture` for the fixture-level side) using each player's actual
cumulative stats through Gameweek 2 (FPL's `element-summary` per-gameweek history log, real
data, not simulated) and a team-ratings fit restricted to matches finished before each fixture's
own kickoff.

**Four of the five are ordinary variance, not a bug** (Tyrick Mitchell, Harvey Barnes, Luka
Vuškovic, Alexander Isak) — none of the start_prob caps fired for any of them, their own
goal/assist rates going into GW3 were unremarkable, and the predictions were all modest and
reasonable given 1-2 matches of evidence. They just had unusually good days (two defenders with
literal goal returns, in particular — a genuinely hard thing for any rate-based model to see
coming). The blog post's own player-level analysis already gets this right for all four.

**Jayden Bogle is a different, genuinely interesting case: -13.88, the single biggest miss of
the round, and it's NOT a player-level issue.** His own inputs were clean — 2 starts, 157
minutes, no goals/assists yet, no cap fired, an unremarkable ~0.02 goal rate. The miss traces
entirely to the FIXTURE-level prediction:

- Reconstructing `fit_pl_ratings` as of just before this kickoff (real historical-season blend
  included, via `_CutoffFPLClient`, a wrapper that filters `client.fixtures()` to matches
  finished before the target kickoff): Brighton's attack rating had already been pushed to
  **1.08** off just two matches (a heavy home win and a win at Manchester United) — enough that
  `predict_fixture` gave Brighton **3.59 expected goals** at home and Leeds (away) just a **2.8%
  clean-sheet probability**.
- The match actually finished 1-1. Leeds conceded 1, not ~3.6, and Bogle personally kept a clean
  sheet for the 60 minutes he played.
- For any Leeds defender, `player_xp`'s `conceded_xp = -(lam_opponent / 2)` term alone was
  roughly `-1.8` points off a fixture the model thought was a near-lock for Brighton — that's
  what crushed Bogle's predicted_xp toward zero, not anything about Bogle himself.

**Why this survives the existing historical-season blend**: `fit_pl_ratings` already blends in
the last 2 PL seasons when the current season has under `MIN_MATCHES_FOR_FIT` (50) matches — and
it did fire here (Leeds actually has one full prior PL season on record, so this isn't a
newly-promoted-club gap). But `fit_ratings`' recency decay (`decay_half_life_days=180`) means the
two freshest, most unusual results still dominate a team's CURRENT rating this early in a
season — there simply isn't enough same-season data yet to dilute a hot streak, decay-weighted
history or not. Checking the same fixture with today's fuller-season ratings: Brighton's attack
had already cooled from 1.08 to a calmer figure and Leeds' defense rating moved from an unstable
extreme toward a normal one as more matches came in — the rating genuinely was that volatile,
confirmed by watching it settle.

### Recommendation — implemented

Sample-size-aware **per-team L2** on attack/defense is in `models/strength.py`
(`early_season_l2_boost` / `team_current_season_matches`) and wired through `fit_pl_ratings`
(`EARLY_SEASON_L2_BOOST=3.0`, `EARLY_SEASON_FULL_STRENGTH_MATCHES=8`). Only *current-season*
FPL fixtures count toward sample size; historical football-data rows still inform the
likelihood. Unit test: `tests/test_strength.py::test_early_season_l2_shrinks_hot_streak_attack`.

Walk-forward fixture-λ MAE (boost vs 0): `scripts/backtest_xp_walkforward.py` +
`services/xp_backtest.py` (`CutoffFPLClient`, loud `FOOTBALL_DATA_TOKEN` requirement). Re-run
when a season completes or when retuning the boost; keep the default only while mean MAE does
not get worse.

Also shipped in the same pass (player-level LHF, separate from GW3):
- Fixture-scaled assists (`_fixture_assist_share`) — was raw per-90 as `assist_share`
- GK `save_rate` and `defensive_contribution` wired from bootstrap into `player_xp`

### Process note for next time

GW1/2 backtest lived in a scratchpad; reconstructing for GW3 nearly shipped a wrong answer when
`FOOTBALL_DATA_TOKEN` was missing. Use `services/xp_backtest.py` /
`scripts/backtest_xp_walkforward.py` instead of another one-off.

## Gameweek 4 insights: newly-promoted clubs, and a real name-matching bug

**Status: implemented.** Triggered by a live user report: Semi Ajayi (Hull City, a defender with
no reputation for attacking or defensive standout play) showing a predicted ~7.8-8.6 points on
`/fpl/player/ajayi/` for every gameweek regardless of opponent, including a strong away fixture.

**Two separate real bugs, found while investigating:**

1. **`normalize_team_name` (`services/team_matching.py`) silently dropped two clubs' entire
   historical-season match history from the ratings fit.** It stripped "AFC" only as a *suffix*
   ("X AFC"), never as football-data.org's *prefix* naming convention ("AFC Bournemouth"), and
   kept football-data.org's "Brighton & Hove Albion FC" ampersand while the FPL-side alias mapped
   to "brighton hove albion" (no ampersand) — two different normalized strings for the same club
   either way, so `fit_pl_ratings`'s historical blend never joined on them. Fixed with a `"afc "`
   prefix strip and a uniform `"&"` -> space normalization, both applied before suffix/alias
   handling. Confirmed via a full current-PL-teams-vs-3-seasons-of-history check that these two
   were the only real mismatches (Coventry and Hull City correctly have no match — genuinely no
   historical PL data, not a name-join failure). Regression tests:
   `tests/test_team_matching.py::test_normalize_handles_prefix_club_names` and
   `::test_normalize_handles_ampersand_variants`.

2. **A genuinely promoted club with zero historical rows gets under-regularized even with the
   GW3 early-season L2 boost already at max strength.** Hull City's fitted defense rating hit
   **+3.35** (vs. Arsenal's +0.57, the next-best established side) off 3 clean sheets in their
   first 3 top-flight games ever — `EARLY_SEASON_L2_BOOST` alone shrinks toward 0 based on
   *current-season sample size*, but says nothing about whether the *historical* side of the
   blend has anything real anchoring the team, so a promoted club's thin, lucky sample has nothing
   pulling against it except the same taper every mid-table team with 3-4 games also gets.

### Recommendation — implemented

`models/strength.py`'s `_per_team_l2` takes an optional `team_has_historical_anchor` +
`no_history_l2_boost`, applying an *additional* boost (same early-season taper) only to teams
with no rows in the historical blend at all; `fit_ratings` derives
`team_has_historical_anchor` itself by comparing each team's total match count in the fit against
`team_current_season_matches`, so callers don't have to keep a second flag in sync with the same
match list. Wired through `fit_pl_ratings` as `NO_HISTORY_L2_BOOST=40.0`.

That value is a compromise, not a clean backtest result — see the constant's comment in
`services/fpl_service.py`. A walk-forward MAE check against the only 3 finished Hull/Coventry
fixtures so far this season (GW2-3, `scripts/backtest_xp_walkforward.py`-style) minimized around
boost 8-12, but every one of those fixtures was against a mid/lower-table side — the sample has no
case of the actual failure mode (an inflated defense implying a promoted side nearly shuts out a
*strong* attack). Direct inspection filled that gap: at boost=10, Hull's fitted defense still gave
Chelsea only a ~15% chance of scoring at all away at Hull. 40.0 brings that to ~28% — still
generous, but no longer absurd — while stopping well short of the boost needed to fully match an
established side's rating (100+), which the thin backtest doesn't support either. Revisit once
promoted clubs have played more top-half fixtures.

Unit test: `tests/test_strength.py::test_no_history_l2_boost_shrinks_promoted_team_harder_than_anchored_team`.

### Follow-up — implemented: shrink toward a promoted-team prior, not toward 0

The 40.0 compromise above was fighting the wrong target. Shrinking a promoted club toward 0
treats it as a league-average team, but promoted clubs are *systematically* below average — they
were in the Championship for a reason — so 0 was never a good prior, just a convenient one. The
same fix idea as the historical blend itself: use real data instead of a placeholder.

`scripts/compute_promoted_team_prior.py` finds every club promoted into a PL season that
football-data.org's free tier still exposes (2023-24 is the oldest season available; 2018-2022
return 403), fits a full, evenly-weighted rating for that whole season, and averages the promoted
clubs' attack/defense across all of them: **6 examples** (Ipswich, Leicester, Southampton from
2024-25; Burnley, Leeds, Sunderland from 2025-26) give `PROMOTED_TEAM_ATTACK_PRIOR = -0.229`,
`PROMOTED_TEAM_DEFENSE_PRIOR = -0.375` — every one of the 6 was below-average on both axes, no
exceptions, which is itself a useful sanity check on the idea.

`models/strength.py`'s `fit_ratings` gained `no_history_prior: tuple[float, float] = (0.0, 0.0)`:
a no-historical-anchor team's *entire* L2 penalty (early-season + no-history boost combined, one
scalar weight) now centers on this point instead of 0. Wired through `fit_pl_ratings` using the
constants above. With a real prior doing more of the work, `NO_HISTORY_L2_BOOST` dropped from
40.0 to **20.0** — roughly half the old brute-force shrinkage reaches a comparable real-world
plausibility check (Chelsea's expected goals away at a promoted side no longer implausibly close
to 0). Re-running that plausibility check across this session's investigation showed the fitted
values drifting by roughly ±0.5 on Hull's defense rating between otherwise-identical calls minutes
apart — almost certainly the live bootstrap/fixture data itself updating, not optimizer
instability — so treat 20.0 as good to within a few units, not a precise optimum.

Unit test: `tests/test_strength.py::test_no_history_prior_pulls_toward_the_prior_not_zero`.

Re-run `scripts/compute_promoted_team_prior.py` once another season completes (more examples,
and football-data.org's 403 cutoff will have moved) and update the two constants by hand.

### Known residual: player-level goal-rate shrinkage may also be too weak for hot small samples

Even with both fixes above, Ajayi's predicted points only dropped to ~6.5-8.3 (from ~7.8-8.6) —
still high for a low-reputation defender. Breaking down `player_xp`'s components for the Chelsea
fixture (boost=40): `clean_sheet` ~2.65-3.49 (the team-rating fix's target, now improved but still
elevated), but `goals` alone contributes ~0.9 xp/game — implausibly high for a budget defender,
traced to `_player_rates`'s price-prior blend: Ajayi's 1 goal in ~3.7 effective matches (a 0.27
per-90 raw rate) only gets diluted to ~0.157 per-90 after blending with `PRICE_PRIOR_WEIGHT_MATCHES
= 4.0` worth of price-informed prior — still a lot for a defender extrapolated over a season.

**Not implemented.** Unlike the team-rating fix, `PRICE_PRIOR_WEIGHT_MATCHES` (or the shrinkage
weighting generally) is a single sitewide constant that touches every player's predicted points,
not just newly-promoted clubs' defenders — raising it needs the same full backtest discipline as
the price-prior work already has, across many players' actual outcomes, not just one player's
one fixture. Flagging here rather than retuning blind.

## Deferred: actual transfer fee paid

The user's original ask also included the real transfer fee a club paid (not just FPL price) as
a signal — deliberately scoped out for now. FPL price is a strong, already-integrated proxy for
the same underlying "reputation/quality" signal a transfer fee would carry, without needing new
infrastructure. A real fee would need a new provider (Transfermarkt or similar), matched to FPL
players by name — comparable scope to `providers/fpl_history.py`, plus the same name-matching
work `services/team_matching.py` already does for football-data.org, and ongoing upkeep since
it's a source not otherwise integrated anywhere in this app. Revisit if the price-prior above
turns out not to be informative enough on its own.
