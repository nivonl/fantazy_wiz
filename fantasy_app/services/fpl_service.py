"""
Wires the FPL provider into the prediction/recommendation engine: fit ratings from real
results (falling back to football-data.org's last-2-seasons history when the current season
is too young), predict a gameweek's fixtures, and build the base xP candidate pool — enriched
per-player with real opponent-specific history from the last 5 PL seasons (providers/
fpl_history.py + services/opponent_history.py). `full_recommendation()` is the main entry
point: it turns a current squad into five kinds of actionable advice, each computed over the
time horizon that actually applies to it (this gameweek only, vs. multi-gameweek for anything
that sticks around) — see its docstring.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
import numpy as np

from fantasy_app.models.player_points import player_xp
from fantasy_app.models.predict import FixturePrediction, predict_fixture
from fantasy_app.models.strength import MatchResult, Ratings, fit_ratings, team_goal_averages
from fantasy_app.providers import fpl_history
from fantasy_app.providers.football_data import FootballDataClient
from fantasy_app.providers.fpl import POSITION_BY_ELEMENT_TYPE, FPLClient
from fantasy_app.recommend.fpl import (
    CandidatePlayer,
    SquadResult,
    TradeCombo,
    TransferSuggestion,
    best_transfer_targets_by_position,
    find_trade_combos_for_target,
    optimize_squad,
    pick_starting_xi,
    suggest_transfers,
)
from fantasy_app.services.common import current_season_start_year
from fantasy_app.services.opponent_history import compute_opponent_stats, shrinkage_factor
from fantasy_app.services.team_matching import normalize_team_name

MIN_MATCHES_FOR_FIT = 50
HISTORICAL_SEASONS_BACK = 2  # "previous 2 seasons" fallback when the current one is too thin

SHORTLIST_PER_POSITION = {"GK": 8, "DEF": 20, "MID": 20, "FWD": 15}

DEFAULT_TRANSFER_HORIZON = 3  # gameweeks a transfer's benefit is evaluated over — it sticks around
DEFAULT_WILDCARD_HORIZON = 5  # wildcard is permanent, so its lift is judged over a longer run
DEFAULT_TARGET_HORIZON = 5  # per-position "best affordable target" horizon
DEFAULT_TRADE_HORIZON = 5  # "trade for this player" combo horizon


@dataclass(frozen=True)
class NamedFixturePrediction:
    home_team: str
    away_team: str
    prediction: FixturePrediction


@dataclass
class TeamBuilderResult:
    squad: SquadResult
    injury_notes: dict[str, dict]  # player id -> {"status": "i"/"d"/"s"/..., "news": "..."}
    shortlisted_count: int
    favorite_team: str | None
    favorite_players_matched: list[str]
    favorite_players_unmatched: list[str]


@dataclass(frozen=True)
class RiskFlag:
    """A squad member whose live FPL status/news right now isn't a clean "available" — the
    thing to check in the window before deadline, since this can change hour to hour."""

    player: CandidatePlayer
    status: str
    news: str
    suggested_replacement: CandidatePlayer | None


@dataclass(frozen=True)
class ChipLift:
    chip: str  # "bench_boost" | "triple_captain" | "free_hit" | "wildcard"
    horizon_gameweeks: int
    lift: float
    note: str


@dataclass
class FullRecommendation:
    risk_flags: list[RiskFlag]
    captain: CandidatePlayer
    vice_captain: CandidatePlayer
    starters: list[CandidatePlayer]
    bench: list[CandidatePlayer]
    lineup_changes: list[str]  # only populated when the caller knows the ACTUAL current XI
    best_transfer: TransferSuggestion | None
    transfer_horizon_gameweeks: int
    chip_lifts: list[ChipLift]
    # The actual squads a "lift" number implies — not just the point differential, since
    # "how much better" is only useful alongside "better how, and does it fit the budget."
    free_hit_squad: SquadResult
    wildcard_squad: SquadResult


def _parse_kickoff(iso: str | None) -> datetime:
    if not iso:
        return datetime.now(timezone.utc)
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


def _try_football_data_client() -> FootballDataClient | None:
    try:
        return FootballDataClient()
    except RuntimeError:
        return None  # no token configured — historical blending is an optional enrichment


def _fd_matches_to_results_by_name(matches: list[dict]) -> list[MatchResult]:
    out = []
    for m in matches:
        score = m.get("score", {}).get("fullTime", {})
        if score.get("home") is None or score.get("away") is None:
            continue
        out.append(
            MatchResult(
                home_team_id=normalize_team_name(m["homeTeam"]["name"]),
                away_team_id=normalize_team_name(m["awayTeam"]["name"]),
                home_goals=score["home"],
                away_goals=score["away"],
                played_at=_parse_kickoff(m.get("utcDate")),
            )
        )
    return out


def fit_pl_ratings(
    client: FPLClient, bootstrap: dict, fd_client: FootballDataClient | None = None
) -> tuple[Ratings, dict[str, float], dict[int, str]]:
    """
    Returns (ratings, goal_averages, normalized_team_name_by_fpl_team_id) — everything keyed
    by *normalized team name* rather than FPL's team ID, because the historical fallback data
    comes from football-data.org, which uses a different ID namespace; name is the only join
    key the two sources share.
    """
    norm_name_by_fpl_id = {t["id"]: normalize_team_name(t["name"]) for t in bootstrap["teams"]}

    all_fixtures = client.fixtures()
    matches = [
        MatchResult(
            home_team_id=norm_name_by_fpl_id[f["team_h"]],
            away_team_id=norm_name_by_fpl_id[f["team_a"]],
            home_goals=f["team_h_score"],
            away_goals=f["team_a_score"],
            played_at=_parse_kickoff(f.get("kickoff_time")),
        )
        for f in all_fixtures
        if f.get("finished") and f.get("team_h_score") is not None and f.get("team_a_score") is not None
    ]

    if len(matches) < MIN_MATCHES_FOR_FIT:
        fd_client = fd_client if fd_client is not None else _try_football_data_client()
        if fd_client is not None:
            start_year = current_season_start_year()
            for seasons_back in range(1, HISTORICAL_SEASONS_BACK + 1):
                try:
                    fd_matches = fd_client.matches("PL", season=start_year - seasons_back, status="FINISHED")
                except Exception:
                    continue
                matches += _fd_matches_to_results_by_name(fd_matches)

    if not matches:
        raise RuntimeError(
            "No Premier League results available — the season hasn't started and no "
            "FOOTBALL_DATA_TOKEN is configured to fall back to the last two seasons' results. "
            "Add FOOTBALL_DATA_TOKEN to .env, or try again once gameweek 1 has kicked off."
        )

    ratings = fit_ratings(matches)
    goal_avgs = team_goal_averages(matches)
    return ratings, goal_avgs, norm_name_by_fpl_id


def predict_gameweek(client: FPLClient, event: int | None = None) -> list[NamedFixturePrediction]:
    bootstrap = client.bootstrap()
    ratings, _, norm_name_by_id = fit_pl_ratings(client, bootstrap)
    event = event or client.current_event(bootstrap)
    fixtures = client.fixtures(event=event)
    team_name_by_id = {t["id"]: t["name"] for t in bootstrap["teams"]}
    return [
        NamedFixturePrediction(
            home_team=team_name_by_id[f["team_h"]],
            away_team=team_name_by_id[f["team_a"]],
            prediction=predict_fixture(ratings, norm_name_by_id[f["team_h"]], norm_name_by_id[f["team_a"]]),
        )
        for f in fixtures
    ]


BACKUP_GK_MINUTES_RATIO = 0.2  # below this fraction of their club's top GK's minutes = clear backup
BACKUP_GK_START_PROB_CAP = 0.1

# A player with 0 minutes despite their OWN TEAM having already played is real evidence of
# something (rotation, a tactical call, an off-pitch issue never flagged as an injury — see
# Watkins/Gyökeres, confirmed live: both starts=0, minutes=0, chance_of_playing=None, i.e.
# indistinguishable from a fit, undisputed starter by FPL's own fields). It's weaker evidence
# than the goalkeeper case (we don't know WHO the alternative is, just that this player didn't
# feature), so the cap is more conservative than the backup-GK one.
UNPROVEN_PLAYER_START_PROB_CAP = 0.3


# --- Price-informed prior for goal/assist rate --------------------------------------------
#
# The observed rate below (goals/assists per 90) is real evidence, but for a player with little
# or no current-season minutes there isn't enough of it to trust on its own — the old version of
# this function simply returned 0.0 in that case, which treats a completely unknown academy
# player and a proven, expensively-priced veteran identically the moment either one has a quiet
# game. See NOTES-model-improvements.md for the two live cases (a 12m-priced international
# predicted near a squad player's floor; a single lucky goal blown up into a 16-point-a-week
# forecast) that motivated this.
#
# FPL's price already bakes in exactly the signal that's missing: reputation, output at a
# previous club or league, the transfer fee a manager was willing to pay — none of which show up
# in "goals this season" for someone who just arrived, but all of which the market (and FPL's
# own pricing team) already priced in. Rather than sourcing that externally (a real transfer-fee
# feed is a much bigger integration — see NOTES-model-improvements.md), this fits a simple
# price -> expected-rate curve straight from this gameweek's own bootstrap data: established
# players (real minutes on the board) are the training set, everyone else borrows their line.

MIN_MINUTES_FOR_PRICE_PRIOR_FIT = 270  # ~3 full matches — enough for a per-90 rate to mean something
MIN_PLAYERS_FOR_PRICE_PRIOR_FIT = 8  # below this many established players at a position, don't trust a position-specific line yet
PRICE_PRIOR_WEIGHT_MATCHES = 4.0  # the price prior counts as this many "matches" of evidence when blended with what's actually been observed — enough to anchor 0-2 starts, small enough that half a season of real form dominates it


@dataclass(frozen=True)
class PriceRatePrior:
    """A straight line from FPL price (£m) to expected goals/assists per 90 minutes, fit fresh
    from this gameweek's own bootstrap — see _fit_price_rate_priors for why and how."""

    goal_slope: float
    goal_intercept: float
    assist_slope: float
    assist_intercept: float

    def predict(self, price: float) -> tuple[float, float]:
        # A price/rate line fit on established players can dip slightly negative at the very
        # bottom of the price range (a cheap bench player's true rate is close to 0, not below
        # it) — clip rather than let that become a negative expected rate downstream.
        return (
            max(0.0, self.goal_slope * price + self.goal_intercept),
            max(0.0, self.assist_slope * price + self.assist_intercept),
        )


_FLAT_PRIOR = PriceRatePrior(0.0, 0.0, 0.0, 0.0)


def _fit_price_rate_priors(bootstrap: dict) -> dict[str, PriceRatePrior]:
    """
    One price -> rate line per position, fit each time this is called (prices and season-to-date
    rates both drift across a season, and refitting ~600 players with numpy is cheap). Positions
    without enough established players yet (plausible very early in a season) fall back to a
    single line fit across every position pooled together, or to a flat zero-rate prior if even
    that pool is too thin — never a crash, just a less informed prior.
    """
    rows_by_pos: dict[str, list[tuple[float, float, float]]] = {}
    for e in bootstrap["elements"]:
        minutes = e.get("minutes", 0) or 0
        if minutes < MIN_MINUTES_FOR_PRICE_PRIOR_FIT:
            continue
        pos = POSITION_BY_ELEMENT_TYPE[e["element_type"]]
        price = e["now_cost"] / 10.0
        goal_rate = (e.get("goals_scored", 0) or 0) * 90.0 / minutes
        assist_rate = (e.get("assists", 0) or 0) * 90.0 / minutes
        rows_by_pos.setdefault(pos, []).append((price, goal_rate, assist_rate))

    def fit_one(rows: list[tuple[float, float, float]]) -> PriceRatePrior:
        prices = np.array([r[0] for r in rows])
        goal_slope, goal_intercept = np.polyfit(prices, [r[1] for r in rows], 1)
        assist_slope, assist_intercept = np.polyfit(prices, [r[2] for r in rows], 1)
        return PriceRatePrior(
            float(goal_slope), float(goal_intercept), float(assist_slope), float(assist_intercept)
        )

    all_established = [row for rows in rows_by_pos.values() for row in rows]
    fallback = fit_one(all_established) if len(all_established) >= MIN_PLAYERS_FOR_PRICE_PRIOR_FIT else _FLAT_PRIOR

    return {
        pos: fit_one(rows_by_pos[pos]) if len(rows_by_pos.get(pos, [])) >= MIN_PLAYERS_FOR_PRICE_PRIOR_FIT else fallback
        for pos in POSITION_BY_ELEMENT_TYPE.values()
    }


def _player_rates(element: dict, price_priors: dict[str, PriceRatePrior]) -> tuple[float, float, float]:
    """
    (goals per 90, assists per 90, start_prob), blending this season's observed rate with the
    price-informed prior above via the same empirical-Bayes shrinkage the model already applies
    to opponent-specific history (services/opponent_history.py's shrinkage_factor) — just one
    layer earlier, on the base rate itself, weighted by minutes rather than starts so a
    productive substitute appearance counts for something instead of being discarded outright
    (the old starts-only version couldn't see a substitute's output at all).

    Per-90 rather than per-start: dimensionally consistent with team_avg_goals below (a
    per-match figure), and doesn't understate a player who's regularly subbed at 60' relative to
    one who plays every minute.

    As real minutes accumulate the observed rate quickly dominates the blend — this is a
    fallback for the genuinely unknown, not a competitor to actual current-season form (see the
    Deep Research post on market value: recent output is the stronger fantasy-points signal
    whenever it actually exists).
    """
    minutes = element.get("minutes", 0) or 0
    chance = element.get("chance_of_playing_next_round")
    start_prob = 0.9 if chance is None else max(chance, 0) / 100.0

    pos = POSITION_BY_ELEMENT_TYPE[element["element_type"]]
    price = element["now_cost"] / 10.0
    prior_goal_rate, prior_assist_rate = price_priors[pos].predict(price)

    goals = element.get("goals_scored", 0) or 0
    assists = element.get("assists", 0) or 0
    observed_goal_rate = goals * 90.0 / minutes if minutes else 0.0
    observed_assist_rate = assists * 90.0 / minutes if minutes else 0.0
    effective_matches = minutes / 90.0

    goal_rate = (observed_goal_rate * effective_matches + prior_goal_rate * PRICE_PRIOR_WEIGHT_MATCHES) / (
        effective_matches + PRICE_PRIOR_WEIGHT_MATCHES
    )
    assist_rate = (observed_assist_rate * effective_matches + prior_assist_rate * PRICE_PRIOR_WEIGHT_MATCHES) / (
        effective_matches + PRICE_PRIOR_WEIGHT_MATCHES
    )
    return goal_rate, assist_rate, start_prob


# --- Squad depth (price-implied rotation risk) -------------------------------------------------

# A rough "how many starters at this position" shape, used only to pick which price rank counts
# as "probably not first-choice" — not meant to model any one team's actual formation, just a
# sane default across the division's mix of back-3/back-4/etc systems.
TYPICAL_STARTERS_BY_POSITION = {"GK": 1, "DEF": 4, "MID": 4, "FWD": 2}
SQUAD_DEPTH_PRICE_RATIO = 0.75  # meaningfully cheaper than the Nth-most-expensive teammate at the position
SQUAD_DEPTH_START_PROB_CAP = 0.55  # softer than the evidence-based caps below — this is a price *hint*, not proof
SQUAD_DEPTH_PROVEN_START_RATIO = 0.5  # started at least half the team's games so far -> real evidence wins, ignore the price hint


def _squad_depth_price_threshold(bootstrap: dict) -> dict[tuple[int, str], float]:
    """
    Per (team id, position), the price of the Nth-most-expensive player in that position group
    at that club — N being the typical number of starters there. A club's own pricing already
    encodes who they rate as starters vs. squad depth (that's what price reflects); this turns
    it into a threshold so a much cheaper teammate in the same slot reads as real rotation risk
    even before any minutes evidence exists either way — the gap _is_unproven_this_season and
    _is_backup_goalkeeper can't cover, since both need the team to have played at least once.
    """
    prices_by_team_pos: dict[tuple[int, str], list[float]] = {}
    for e in bootstrap["elements"]:
        pos = POSITION_BY_ELEMENT_TYPE[e["element_type"]]
        prices_by_team_pos.setdefault((e["team"], pos), []).append(e["now_cost"] / 10.0)

    thresholds: dict[tuple[int, str], float] = {}
    for (team_id, pos), prices in prices_by_team_pos.items():
        prices.sort(reverse=True)
        n_starters = TYPICAL_STARTERS_BY_POSITION.get(pos, 1)
        thresholds[(team_id, pos)] = prices[min(n_starters, len(prices)) - 1]
    return thresholds


def _is_priced_like_backup(
    element: dict, price_thresholds: dict[tuple[int, str], float], team_games_played: dict[int, int]
) -> bool:
    """True only when the price hint AND the lack of real evidence against it both hold — a
    player who's actually started most of their team's games so far is a starter regardless of
    how their price stacks up against a teammate's; real minutes always outrank a price guess."""
    pos = POSITION_BY_ELEMENT_TYPE[element["element_type"]]
    threshold = price_thresholds.get((element["team"], pos))
    if threshold is None:
        return False
    if element["now_cost"] / 10.0 >= threshold * SQUAD_DEPTH_PRICE_RATIO:
        return False
    games_played = team_games_played.get(element["team"], 0)
    starts = element.get("starts", 0) or 0
    if games_played > 0 and starts / games_played >= SQUAD_DEPTH_PROVEN_START_RATIO:
        return False
    return True


def _max_gk_minutes_by_team(bootstrap: dict) -> dict[int, int]:
    max_minutes: dict[int, int] = {}
    for e in bootstrap["elements"]:
        if POSITION_BY_ELEMENT_TYPE[e["element_type"]] != "GK":
            continue
        team_id = e["team"]
        minutes = e.get("minutes", 0) or 0
        max_minutes[team_id] = max(max_minutes.get(team_id, 0), minutes)
    return max_minutes


def _is_backup_goalkeeper(element: dict, max_gk_minutes: dict[int, int]) -> bool:
    """
    Real signal, not a guess: exactly one goalkeeper starts per match, so if another keeper
    at the same club has clearly played most of the minutes this season, this one isn't
    first-choice — regardless of what `chance_of_playing_next_round` says (which only flags
    injury doubt, not squad status). Confirmed live: an Ipswich keeper with 0 starts/0
    minutes got the same 90% default start_prob as their actual starter (90 minutes played),
    solely because neither had an injury flag.
    """
    if POSITION_BY_ELEMENT_TYPE[element["element_type"]] != "GK":
        return False
    top_minutes = max_gk_minutes.get(element["team"], 0)
    if top_minutes == 0:
        return False  # nobody at this club has played yet — no relative signal either way
    return (element.get("minutes", 0) or 0) < BACKUP_GK_MINUTES_RATIO * top_minutes


def _team_games_played(client: FPLClient) -> dict[int, int]:
    """How many fixtures each team has actually finished this season — the signal that
    separates true preseason (nobody's played, 0 minutes means nothing) from a specific
    player having 0 minutes despite their own team already taking the pitch (real evidence,
    even with no injury flag to explain it)."""
    games: dict[int, int] = {}
    for f in client.fixtures():
        if not f.get("finished"):
            continue
        games[f["team_h"]] = games.get(f["team_h"], 0) + 1
        games[f["team_a"]] = games.get(f["team_a"], 0) + 1
    return games


def _is_unproven_this_season(element: dict, team_games_played: dict[int, int]) -> bool:
    """Zero starts AND their team has already played at least once — any position, not just
    goalkeepers. Weaker evidence than _is_backup_goalkeeper (no comparison to who else might
    start instead, just that this player hasn't featured at all), so it gets a softer cap."""
    if (element.get("starts", 0) or 0) > 0:
        return False
    return team_games_played.get(element["team"], 0) > 0


def _gameweek_fixture_by_team(client: FPLClient, event: int) -> dict[int, dict]:
    gw_fixtures = client.fixtures(event=event)
    fixture_by_team: dict[int, dict] = {}
    for f in gw_fixtures:
        fixture_by_team.setdefault(f["team_h"], f)
        fixture_by_team.setdefault(f["team_a"], f)
    return fixture_by_team


def _candidates_for_gameweek(
    client: FPLClient,
    bootstrap: dict,
    ratings: Ratings,
    goal_avgs: dict[str, float],
    norm_name_by_id: dict[int, str],
    history_index: dict[str, list],
    event: int,
    team_games_played: dict[int, int],
    price_priors: dict[str, PriceRatePrior],
    price_thresholds: dict[tuple[int, str], float],
) -> dict[str, CandidatePlayer]:
    """The single-gameweek xP model for every player with a fixture that week, keyed by
    element id. Factored out of build_candidate_pool so build_candidate_pool_multi_gw can
    call it once per gameweek in a window and sum, without duplicating the model.

    `team_games_played`, `price_priors` and `price_thresholds` are all computed once by the
    caller from data that doesn't vary across which gameweek we're predicting (only whether a
    match has already been played, and this gameweek's bootstrap snapshot) and passed in rather
    than recomputed here, since build_candidate_pool_multi_gw calls this once per gameweek in
    its window."""
    team_name_by_id = {t["id"]: t["name"] for t in bootstrap["teams"]}
    fixture_by_team = _gameweek_fixture_by_team(client, event)
    max_gk_minutes = _max_gk_minutes_by_team(bootstrap)

    candidates: dict[str, CandidatePlayer] = {}
    for element in bootstrap["elements"]:
        team_id = element["team"]
        fixture = fixture_by_team.get(team_id)
        if fixture is None:
            continue  # blank gameweek for this team — no fixture to predict against

        is_home = fixture["team_h"] == team_id
        home_name, away_name = norm_name_by_id[fixture["team_h"]], norm_name_by_id[fixture["team_a"]]
        pred = predict_fixture(ratings, home_name, away_name)
        lam_team = pred.lam_home if is_home else pred.lam_away
        lam_opponent = pred.lam_away if is_home else pred.lam_home
        p_cs = pred.p_home_clean_sheet if is_home else pred.p_away_clean_sheet

        pos = POSITION_BY_ELEMENT_TYPE[element["element_type"]]
        goal_rate, assist_rate, start_prob = _player_rates(element, price_priors)
        if _is_unproven_this_season(element, team_games_played):
            start_prob = min(start_prob, UNPROVEN_PLAYER_START_PROB_CAP)
        if _is_backup_goalkeeper(element, max_gk_minutes):
            start_prob = min(start_prob, BACKUP_GK_START_PROB_CAP)
        if _is_priced_like_backup(element, price_thresholds, team_games_played):
            start_prob = min(start_prob, SQUAD_DEPTH_START_PROB_CAP)
        team_avg_goals = max(goal_avgs.get(norm_name_by_id[team_id], 1.0), 0.1)
        # A player can't be responsible for more than the whole team's average output — clamp
        # defensively in case a small-sample rate (even after price-prior blending) or a
        # rate/average mismatch from a future data source pushes the raw ratio past 100%.
        goal_share = min(goal_rate / team_avg_goals, 1.0)

        base_xp = player_xp(
            name=element["web_name"],
            pos=pos,
            price=element["now_cost"] / 10.0,
            lam_team=lam_team,
            lam_opponent=lam_opponent,
            p_cs=p_cs,
            goal_share=goal_share,
            assist_share=assist_rate,
            start_prob=start_prob,
        ).xp

        full_name = fpl_history.normalize_person_name(f"{element['first_name']} {element['second_name']}")
        history_rows = history_index.get(full_name, [])
        opponent_name = team_name_by_id[fixture["team_a"] if is_home else fixture["team_h"]]
        current_team_name = team_name_by_id[team_id]
        opponent_factor = shrinkage_factor(history_rows, opponent_name)
        stats = compute_opponent_stats(history_rows, opponent_name, current_team_name)

        candidates[str(element["id"])] = CandidatePlayer(
            id=str(element["id"]),
            name=element["web_name"],
            pos=pos,
            team=current_team_name,
            price=element["now_cost"] / 10.0,
            xp=round(base_xp * opponent_factor, 3),
            opponent_stats=stats,
        )
    return candidates


def build_candidate_pool(
    client: FPLClient, event: int | None = None, fd_client: FootballDataClient | None = None
) -> list[CandidatePlayer]:
    bootstrap = client.bootstrap()
    ratings, goal_avgs, norm_name_by_id = fit_pl_ratings(client, bootstrap, fd_client=fd_client)
    event = event or client.current_event(bootstrap)
    history_index = fpl_history.index_by_player()
    team_games_played = _team_games_played(client)
    price_priors = _fit_price_rate_priors(bootstrap)
    price_thresholds = _squad_depth_price_threshold(bootstrap)
    return list(
        _candidates_for_gameweek(
            client, bootstrap, ratings, goal_avgs, norm_name_by_id, history_index, event, team_games_played,
            price_priors, price_thresholds,
        ).values()
    )


def build_candidate_pool_multi_gw(
    client: FPLClient,
    fd_client: FootballDataClient | None = None,
    start_event: int | None = None,
    num_gameweeks: int = DEFAULT_TRANSFER_HORIZON,
) -> list[CandidatePlayer]:
    """
    Same per-player xP model as build_candidate_pool, but summed across `num_gameweeks`
    consecutive gameweeks starting at `start_event` — for horizon-aware decisions. A transfer
    or a wildcard sticks around for multiple weeks, so a single gameweek's xP understates its
    real value; this is what makes "best transfer" and "wildcard lift" horizon-appropriate
    instead of just reusing the single-gameweek pool. Blank gameweeks for a team simply
    contribute 0 that week. The tooltip's opponent_stats reflects only the FIRST gameweek in
    the window (the next match) even though `xp` is the full-horizon sum — a multi-opponent
    tooltip isn't a meaningful thing to show.
    """
    bootstrap = client.bootstrap()
    ratings, goal_avgs, norm_name_by_id = fit_pl_ratings(client, bootstrap, fd_client=fd_client)
    start_event = start_event or client.current_event(bootstrap)
    history_index = fpl_history.index_by_player()
    team_games_played = _team_games_played(client)
    price_priors = _fit_price_rate_priors(bootstrap)
    price_thresholds = _squad_depth_price_threshold(bootstrap)

    template_by_id: dict[str, CandidatePlayer] = {}
    total_xp: dict[str, float] = {}
    for offset in range(num_gameweeks):
        event = start_event + offset
        gw_candidates = _candidates_for_gameweek(
            client, bootstrap, ratings, goal_avgs, norm_name_by_id, history_index, event, team_games_played,
            price_priors, price_thresholds,
        )
        for pid, c in gw_candidates.items():
            total_xp[pid] = total_xp.get(pid, 0.0) + c.xp
            template_by_id.setdefault(pid, c)

    return [
        CandidatePlayer(
            id=pid, name=t.name, pos=t.pos, team=t.team, price=t.price,
            xp=round(total_xp[pid], 3), opponent_stats=t.opponent_stats,
        )
        for pid, t in template_by_id.items()
    ]


def build_transfer_targets(
    client: FPLClient,
    current_squad: list[CandidatePlayer],
    budget: float,
    event: int | None = None,
    fd_client: FootballDataClient | None = None,
    horizon: int = DEFAULT_TARGET_HORIZON,
) -> dict[str, CandidatePlayer | None]:
    """Per-position best affordable transfer target (not already owned), ranked by xp summed
    over `horizon` gameweeks (default 5) — see best_transfer_targets_by_position for the pure
    selection logic this just wires a real multi-gameweek pool into."""
    pool = build_candidate_pool_multi_gw(client, fd_client=fd_client, start_event=event, num_gameweeks=horizon)
    return best_transfer_targets_by_position(pool, current_squad, budget)


def build_trade_combos(
    client: FPLClient,
    current_squad: list[CandidatePlayer],
    target_name: str,
    bank: float,
    free_transfers: int,
    event: int | None = None,
    fd_client: FootballDataClient | None = None,
    horizon: int = DEFAULT_TRADE_HORIZON,
    top_k: int = 3,
) -> list[TradeCombo]:
    """Top-`top_k` ways to reshuffle `current_squad` (no chip) to end up owning the player
    named `target_name`, ranked by projected points over `horizon` gameweeks net of any
    transfer hits. See find_trade_combos_for_target for the actual optimization."""
    pool = build_candidate_pool_multi_gw(client, fd_client=fd_client, start_event=event, num_gameweeks=horizon)
    matched, unmatched = match_player_names([target_name], pool)
    if not matched:
        raise RuntimeError(f"Couldn't match '{target_name}' to a real FPL player.")
    return find_trade_combos_for_target(current_squad, matched[0], pool, bank, free_transfers, top_k=top_k)


def match_player_names(names: list[str], pool: list[CandidatePlayer]) -> tuple[list[CandidatePlayer], list[str]]:
    """
    Exact name match first, then substring (e.g. "Salah" -> FPL's "M.Salah") — the UI's
    datalist offers exact names, but free-typed input shouldn't have to match them exactly.
    Matching is accent-insensitive (fpl_history.normalize_person_name) so plain-ASCII input
    like "Odegaard" finds FPL's actual "Ødegaard" — a plain .lower() comparison would silently
    miss it, since 'o' != 'ø'.
    Returns (matched candidates, names that couldn't be matched to anyone in the pool).
    """
    matched: list[CandidatePlayer] = []
    unmatched: list[str] = []
    normalized_pool = [(fpl_history.normalize_person_name(p.name), p) for p in pool]
    for wanted in (n.strip() for n in names if n.strip()):
        wanted_norm = fpl_history.normalize_person_name(wanted)
        match = next((p for norm, p in normalized_pool if norm == wanted_norm), None)
        if match is None:
            match = next((p for norm, p in normalized_pool if wanted_norm in norm), None)
        if match is not None:
            matched.append(match)
        else:
            unmatched.append(wanted)
    return matched, unmatched


def entry_squad_and_starters(
    client: FPLClient, entry_id: int, pool: list[CandidatePlayer]
) -> tuple[list[CandidatePlayer], set[str]]:
    """Map an FPL entry's saved picks onto the xP-priced CandidatePlayer pool by element id.
    Returns (the 15, the ids of the 11 actually in the starting XI right now) — FPL's pick
    objects carry `position` 1-11 for the starting XI and 12-15 for the bench."""
    bootstrap = client.bootstrap()
    event = client.current_event(bootstrap)
    try:
        picks = client.entry_picks(entry_id, event)["picks"]
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise RuntimeError(
                f"FPL entry {entry_id} exists, but gameweek {event}'s picks aren't public yet — "
                "FPL only exposes an entry's picks for a gameweek once that gameweek's deadline "
                "has passed (so other managers can't copy picks before lock). Enter your squad "
                "manually instead, or try again after the deadline."
            ) from e
        raise
    by_id = {p.id: p for p in pool}
    squad: list[CandidatePlayer] = []
    starter_ids: set[str] = set()
    for pick in picks:
        player = by_id.get(str(pick["element"]))
        if player is not None:
            squad.append(player)
            if pick.get("position", 99) <= 11:
                starter_ids.add(player.id)
    return squad, starter_ids


def _risk_flags(current_squad: list[CandidatePlayer], pool: list[CandidatePlayer], element_by_id: dict) -> list[RiskFlag]:
    squad_ids = {p.id for p in current_squad}
    flags: list[RiskFlag] = []
    for p in current_squad:
        element = element_by_id.get(p.id)
        if element is None or element.get("status") == "a":
            continue
        replacement = max(
            (c for c in pool if c.pos == p.pos and c.id not in squad_ids), key=lambda c: c.xp, default=None
        )
        flags.append(
            RiskFlag(player=p, status=element.get("status", "?"), news=element.get("news") or "", suggested_replacement=replacement)
        )
    return flags


def full_recommendation(
    client: FPLClient,
    current_squad: list[CandidatePlayer],
    pool_1gw: list[CandidatePlayer],
    bank: float,
    free_transfers: int = 1,
    event: int | None = None,
    fd_client: FootballDataClient | None = None,
    transfer_horizon: int = DEFAULT_TRANSFER_HORIZON,
    wildcard_horizon: int = DEFAULT_WILDCARD_HORIZON,
    actual_starter_ids: set[str] | None = None,
) -> FullRecommendation:
    """
    Turns a current 15 into five kinds of advice, each over the horizon that actually matches
    what it commits you to:
      - risk flags: live news/status right now (the "check before deadline" pass) — no horizon,
        it's a snapshot.
      - captain/vice + starting XI vs bench: this gameweek only.
      - one best transfer: summed over `transfer_horizon` gameweeks, since a transfer sticks
        around — a swap that's a wash this week but clearly better over the next few is worth
        making now, and this-week-only scoring would miss that entirely.
      - free_hit lift: this gameweek only (the chip is temporary, reverts next week).
      - wildcard lift: summed over `wildcard_horizon` gameweeks (the chip is permanent).
      - bench_boost / triple_captain lift: this gameweek only (both are single-gameweek chips).

    `pool_1gw` is the caller's already-built single-gameweek candidate pool (from
    build_candidate_pool) — accepted rather than rebuilt here, since the caller typically
    needs it anyway to resolve `current_squad` (from an entry's picks or matched player names)
    before calling this, and re-fitting ratings twice per request would be wasteful.
    """
    bootstrap = client.bootstrap()
    event = event or client.current_event(bootstrap)
    element_by_id = {str(e["id"]): e for e in bootstrap["elements"]}

    risk_flags = _risk_flags(current_squad, pool_1gw, element_by_id)

    starters, bench = pick_starting_xi(current_squad)
    ranked_starters = sorted(starters, key=lambda p: p.xp, reverse=True)
    captain, vice = ranked_starters[0], ranked_starters[1]

    lineup_changes: list[str] = []
    if actual_starter_ids is not None:
        recommended_ids = {p.id for p in starters}
        for p in current_squad:
            was_starting = p.id in actual_starter_ids
            should_start = p.id in recommended_ids
            if was_starting and not should_start:
                lineup_changes.append(f"Bench {p.name} — not in the optimal XI this gameweek")
            elif should_start and not was_starting:
                lineup_changes.append(f"Start {p.name} — currently on your bench but should start")

    # Best single transfer, over the transfer horizon (not just this gameweek).
    pool_transfer_horizon = build_candidate_pool_multi_gw(
        client, fd_client=fd_client, start_event=event, num_gameweeks=transfer_horizon
    )
    multi_by_id = {p.id: p for p in pool_transfer_horizon}
    current_squad_multi = [multi_by_id[p.id] for p in current_squad if p.id in multi_by_id]
    transfers = suggest_transfers(current_squad_multi, pool_transfer_horizon, bank=bank, free_transfers=1)
    best_transfer = transfers[0] if transfers else None

    # Chip lifts.
    bench_xp = round(sum(p.xp for p in bench), 2)
    triple_lift = round(captain.xp, 2)  # xP already reflects a normal (unmultiplied) captain

    optimal_1gw = optimize_squad(pool_1gw)
    current_1gw_xi_xp = sum(p.xp for p in starters)
    free_hit_lift = round(optimal_1gw.starting_xp - current_1gw_xi_xp, 2)

    pool_wildcard_horizon = (
        pool_transfer_horizon
        if wildcard_horizon == transfer_horizon
        else build_candidate_pool_multi_gw(client, fd_client=fd_client, start_event=event, num_gameweeks=wildcard_horizon)
    )
    optimal_wildcard = optimize_squad(pool_wildcard_horizon)
    wc_by_id = {p.id: p for p in pool_wildcard_horizon}
    current_squad_wc = [wc_by_id[p.id] for p in current_squad if p.id in wc_by_id]
    current_wc_starters, _ = pick_starting_xi(current_squad_wc)
    current_wc_xi_xp = sum(p.xp for p in current_wc_starters)
    wildcard_lift = round(optimal_wildcard.starting_xp - current_wc_xi_xp, 2)

    chip_lifts = [
        ChipLift(chip="bench_boost", horizon_gameweeks=1, lift=bench_xp, note=f"Bench's predicted xP this gameweek: {bench_xp}"),
        ChipLift(
            chip="triple_captain", horizon_gameweeks=1, lift=triple_lift,
            note=f"Extra xP over a normal (double) captain: {triple_lift} ({captain.name})",
        ),
        ChipLift(
            chip="free_hit", horizon_gameweeks=1, lift=free_hit_lift,
            note=(
                f"One-week-only optimal XI vs your current XI: {free_hit_lift:+} xP, reverts next "
                f"gameweek. Squad costs {optimal_1gw.total_price}m (100m budget, doesn't have to "
                f"match what you actually paid for your real squad since it's rebuilt from scratch)."
            ),
        ),
        ChipLift(
            chip="wildcard", horizon_gameweeks=wildcard_horizon, lift=wildcard_lift,
            note=(
                f"Optimal XI over the next {wildcard_horizon} gameweeks vs your current XI, permanent "
                f"change: {wildcard_lift:+} cumulative xP. Squad costs {optimal_wildcard.total_price}m "
                f"(100m budget)."
            ),
        ),
    ]

    return FullRecommendation(
        risk_flags=risk_flags,
        captain=captain,
        vice_captain=vice,
        starters=starters,
        bench=bench,
        lineup_changes=lineup_changes,
        best_transfer=best_transfer,
        transfer_horizon_gameweeks=transfer_horizon,
        chip_lifts=chip_lifts,
        free_hit_squad=optimal_1gw,
        wildcard_squad=optimal_wildcard,
    )


def build_team_builder(
    client: FPLClient,
    fd_client: FootballDataClient | None = None,
    event: int | None = None,
    favorite_team: str | None = None,
    favorite_player_names: list[str] | None = None,
    min_favorite_team_count: int = 3,
) -> TeamBuilderResult:
    """
    Team Builder: base xP pool (already opponent-history-adjusted — see build_candidate_pool)
    -> shortlist (top-N per position, plus any favorite-team/favorite-player picks so they're
    always in play even if the base model doesn't love them) -> optimize under the
    favorite-team/player constraints.
    """
    favorite_player_names = favorite_player_names or []
    bootstrap = client.bootstrap()
    event = event or client.current_event(bootstrap)
    base_pool = build_candidate_pool(client, event=event, fd_client=fd_client)
    element_by_id = {str(e["id"]): e for e in bootstrap["elements"]}

    by_pos: dict[str, list[CandidatePlayer]] = {}
    for p in base_pool:
        by_pos.setdefault(p.pos, []).append(p)

    shortlist_ids: set[str] = set()
    for pos, players in by_pos.items():
        top = sorted(players, key=lambda p: p.xp, reverse=True)[: SHORTLIST_PER_POSITION.get(pos, 15)]
        shortlist_ids.update(p.id for p in top)

    matched_team_name: str | None = None
    for p in base_pool:
        if favorite_team and normalize_team_name(p.team) == normalize_team_name(favorite_team):
            shortlist_ids.add(p.id)
            matched_team_name = p.team

    if favorite_team and matched_team_name is None:
        raise RuntimeError(f"No FPL team matches '{favorite_team}'.")

    favorite_matches, unmatched_names = match_player_names(favorite_player_names, base_pool)
    favorite_ids = [p.id for p in favorite_matches]
    matched_names = [p.name for p in favorite_matches]
    shortlist_ids.update(favorite_ids)

    shortlist = [p for p in base_pool if p.id in shortlist_ids]

    injury_notes: dict[str, dict] = {}
    for p in shortlist:
        element = element_by_id[p.id]
        if element.get("status") != "a":
            injury_notes[p.id] = {"status": element.get("status"), "news": element.get("news") or ""}

    min_from_team = {}
    if matched_team_name is not None:
        min_from_team[matched_team_name] = min(min_favorite_team_count, 3)

    squad = optimize_squad(shortlist, must_include_ids=favorite_ids, min_from_team=min_from_team)

    return TeamBuilderResult(
        squad=squad,
        injury_notes=injury_notes,
        shortlisted_count=len(shortlist),
        favorite_team=matched_team_name,
        favorite_players_matched=matched_names,
        favorite_players_unmatched=unmatched_names,
    )
