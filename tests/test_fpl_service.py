import httpx
import pytest

from fantasy_app.recommend.fpl import CandidatePlayer
from fantasy_app.services.fpl_service import (
    PriceRatePrior,
    _fit_price_rate_priors,
    _is_backup_goalkeeper,
    _is_priced_like_backup,
    _is_unproven_this_season,
    _max_gk_minutes_by_team,
    _player_rates,
    _risk_flags,
    _squad_depth_price_threshold,
    _team_games_played,
    entry_squad_and_starters,
    match_player_names,
)

_FLAT_PRIOR = {"GK": PriceRatePrior(0.0, 0.0, 0.0, 0.0), "DEF": PriceRatePrior(0.0, 0.0, 0.0, 0.0),
               "MID": PriceRatePrior(0.0, 0.0, 0.0, 0.0), "FWD": PriceRatePrior(0.0, 0.0, 0.0, 0.0)}


def test_player_rates_zero_minutes_falls_back_to_the_price_prior():
    # No minutes at all this season (a completely blank slate) — with a flat (zero) prior,
    # goal/assist rate must be exactly 0, not a fabricated non-zero figure. A stray
    # goals_scored>0 with 0 minutes (a leftover stat from before a season reset) must not leak
    # through either, since it can't be divided into a real per-90 rate.
    element = {
        "minutes": 0, "goals_scored": 11, "assists": 0, "chance_of_playing_next_round": None,
        "element_type": 4, "now_cost": 70,
    }
    goal_rate, assist_rate, start_prob = _player_rates(element, _FLAT_PRIOR)
    assert goal_rate == 0.0
    assert assist_rate == 0.0


def test_player_rates_blends_observed_rate_with_price_prior():
    # 90 minutes (1 "effective match") of real evidence, blended with a non-flat prior that
    # predicts a higher rate at this player's price — the result should sit strictly between
    # the two, not equal either one outright (a single match shouldn't fully override a prior
    # tuned on many established players, and shouldn't be fully overridden by it either).
    prior = {"FWD": PriceRatePrior(goal_slope=0.05, goal_intercept=0.0, assist_slope=0.0, assist_intercept=0.0)}
    element = {"minutes": 90, "goals_scored": 0, "assists": 0, "chance_of_playing_next_round": 100,
               "element_type": 4, "now_cost": 100}
    goal_rate, assist_rate, start_prob = _player_rates(element, prior)
    prior_rate = prior["FWD"].predict(10.0)[0]
    assert 0.0 < goal_rate < prior_rate
    assert start_prob == 1.0


def test_player_rates_observed_form_dominates_once_established():
    # Many effective matches of real, consistent output should push the blended rate close to
    # the observed rate, largely swamping a prior tuned for a completely different price level.
    prior = {"MID": PriceRatePrior(goal_slope=0.0, goal_intercept=0.01, assist_slope=0.0, assist_intercept=0.0)}
    element = {"minutes": 3600, "goals_scored": 20, "assists": 0, "chance_of_playing_next_round": None,
               "element_type": 3, "now_cost": 80}
    goal_rate, _, _ = _player_rates(element, prior)
    assert goal_rate == pytest.approx(0.5, abs=0.05)  # 20 goals in 3600 mins = 0.5/90


def test_fit_price_rate_priors_learns_a_positive_price_goal_relationship():
    # Synthetic but realistic: pricier forwards score more per 90 than cheaper ones. The fitted
    # line should reflect that (a higher price predicts a higher rate), not just default flat.
    elements = [
        {"element_type": 4, "now_cost": p, "minutes": 900, "goals_scored": g, "assists": 0}
        for p, g in [(45, 1), (55, 2), (65, 4), (75, 5), (85, 7), (95, 8), (105, 9), (150, 12)]
    ]
    priors = _fit_price_rate_priors({"elements": elements})
    cheap_rate, _ = priors["FWD"].predict(4.5)
    expensive_rate, _ = priors["FWD"].predict(15.0)
    assert expensive_rate > cheap_rate


def test_fit_price_rate_priors_falls_back_when_a_position_has_too_few_established_players():
    # Only 2 established players total, all midfielders — below MIN_PLAYERS_FOR_PRICE_PRIOR_FIT
    # for both the position-specific fit AND the pooled fallback, so every position should get
    # the same flat, zero-slope prior rather than an unstable line fit on 2 points.
    elements = [
        {"element_type": 3, "now_cost": 60, "minutes": 900, "goals_scored": 2, "assists": 1},
        {"element_type": 3, "now_cost": 90, "minutes": 900, "goals_scored": 5, "assists": 3},
    ]
    priors = _fit_price_rate_priors({"elements": elements})
    for pos in ("GK", "DEF", "MID", "FWD"):
        assert priors[pos].goal_slope == 0.0
        assert priors[pos].goal_intercept == 0.0


def _squad(team, pos, prices):
    return [{"team": team, "element_type": pos, "now_cost": int(p * 10)} for p in prices]


def test_squad_depth_flags_a_cheap_player_behind_expensive_teammates():
    # 5 defenders at one club, priced 8/7/6/4.5/3 (element_type 2 = DEF, 4 typical starters) —
    # the cheapest is well below 75% of the 4th-most-expensive (4.5), so should read as squad depth.
    elements = _squad(team=1, pos=2, prices=[8.0, 7.0, 6.0, 4.5, 3.0])
    thresholds = _squad_depth_price_threshold({"elements": elements})
    assert _is_priced_like_backup(elements[4], thresholds, team_games_played={}) is True


def test_squad_depth_ignores_the_regular_starters():
    elements = _squad(team=1, pos=2, prices=[8.0, 7.0, 6.0, 4.5, 3.0])
    thresholds = _squad_depth_price_threshold({"elements": elements})
    assert _is_priced_like_backup(elements[0], thresholds, team_games_played={}) is False


def test_squad_depth_defers_to_real_minutes_evidence():
    # Same cheap defender as above, but now with real evidence of actually starting most of
    # the team's games — that should win over the price-based guess.
    elements = _squad(team=1, pos=2, prices=[8.0, 7.0, 6.0, 4.5, 3.0])
    elements[4]["starts"] = 4
    thresholds = _squad_depth_price_threshold({"elements": elements})
    assert _is_priced_like_backup(elements[4], thresholds, team_games_played={1: 5}) is False


class _FakePicks404Client:
    def bootstrap(self):
        return {"events": [{"id": 1, "is_current": True, "finished": False}]}

    def current_event(self, bootstrap=None):
        return 1

    def entry_picks(self, entry_id, event):
        request = httpx.Request("GET", f"https://fantasy.premierleague.com/api/entry/{entry_id}/event/{event}/picks/")
        response = httpx.Response(404, request=request)
        raise httpx.HTTPStatusError("404", request=request, response=response)


def test_entry_squad_and_starters_explains_pre_deadline_404():
    # Real behavior, confirmed live: FPL 404s an entry's picks for a gameweek until that
    # gameweek's deadline has passed (so rivals can't copy a team before lock). Must surface
    # as an explainable RuntimeError, not a generic "upstream 404".
    with pytest.raises(RuntimeError, match="picks aren't public yet"):
        entry_squad_and_starters(_FakePicks404Client(), entry_id=2730386, pool=[])


def _pool():
    return [
        CandidatePlayer(id="1", name="M.Salah", pos="MID", team="Liverpool", price=13.0, xp=8.0),
        CandidatePlayer(id="2", name="Haaland", pos="FWD", team="Man City", price=15.5, xp=9.0),
        CandidatePlayer(id="3", name="Saka", pos="MID", team="Arsenal", price=10.0, xp=7.0),
        CandidatePlayer(id="4", name="Ødegaard", pos="MID", team="Arsenal", price=9.0, xp=7.5),
    ]


def test_match_player_names_exact_match():
    matched, unmatched = match_player_names(["Haaland"], _pool())
    assert [p.name for p in matched] == ["Haaland"]
    assert unmatched == []


def test_match_player_names_substring_match():
    # "Salah" typed by a user should still find FPL's "M.Salah"
    matched, unmatched = match_player_names(["Salah"], _pool())
    assert [p.name for p in matched] == ["M.Salah"]
    assert unmatched == []


def test_match_player_names_is_accent_insensitive():
    # Regression: plain lowercase substring matching missed FPL's real "Ødegaard" when the
    # user typed the plain-ASCII "Odegaard" ('o' != 'ø').
    matched, unmatched = match_player_names(["Odegaard"], _pool())
    assert [p.name for p in matched] == ["Ødegaard"]
    assert unmatched == []


def _gk(name, team, minutes, element_type=1):
    return {"web_name": name, "team": team, "minutes": minutes, "element_type": element_type}


def test_backup_goalkeeper_detected_from_relative_minutes():
    # Regression, confirmed live: Ipswich's Walton (0 starts, 0 minutes) got the same 90%
    # default start_prob as their actual starter, Scherpen (90 minutes) — because neither had
    # an injury flag. Real relative playing time should catch this even though the flag can't.
    bootstrap = {
        "elements": [
            _gk("Scherpen", team=12, minutes=90),
            _gk("Walton", team=12, minutes=0),
            _gk("Palmer", team=12, minutes=0),
        ]
    }
    max_minutes = _max_gk_minutes_by_team(bootstrap)
    assert max_minutes[12] == 90
    assert _is_backup_goalkeeper(bootstrap["elements"][0], max_minutes) is False  # Scherpen: the starter
    assert _is_backup_goalkeeper(bootstrap["elements"][1], max_minutes) is True  # Walton: clear backup
    assert _is_backup_goalkeeper(bootstrap["elements"][2], max_minutes) is True  # Palmer: clear backup


def test_backup_goalkeeper_no_signal_when_nobodys_played_yet():
    # True preseason (everyone at 0 minutes) — no relative signal exists, so don't guess.
    bootstrap = {"elements": [_gk("A", team=1, minutes=0), _gk("B", team=1, minutes=0)]}
    max_minutes = _max_gk_minutes_by_team(bootstrap)
    assert _is_backup_goalkeeper(bootstrap["elements"][0], max_minutes) is False
    assert _is_backup_goalkeeper(bootstrap["elements"][1], max_minutes) is False


def test_backup_goalkeeper_ignores_outfield_players():
    bootstrap = {"elements": [_gk("Striker", team=1, minutes=90, element_type=4)]}
    max_minutes = _max_gk_minutes_by_team(bootstrap)
    assert _is_backup_goalkeeper(bootstrap["elements"][0], max_minutes) is False


class _FakeFixturesClient:
    def __init__(self, fixtures):
        self._fixtures = fixtures

    def fixtures(self, event=None):
        return self._fixtures


def test_team_games_played_counts_only_finished_fixtures():
    fixtures = [
        {"team_h": 1, "team_a": 2, "finished": True},
        {"team_h": 1, "team_a": 3, "finished": True},
        {"team_h": 2, "team_a": 3, "finished": False},  # not played yet — shouldn't count
    ]
    games = _team_games_played(_FakeFixturesClient(fixtures))
    assert games == {1: 2, 2: 1, 3: 1}


def test_is_unproven_this_season_regression_watkins_gyokeres():
    # Real case, confirmed live: both had starts=0, minutes=0, chance_of_playing_next_round=None
    # — indistinguishable from a fit undisputed starter by FPL's own fields — but their teams
    # had already played a fixture. That's the real signal FPL's fields miss.
    element = {"team": 7, "starts": 0}
    assert _is_unproven_this_season(element, {7: 1}) is True


def test_is_unproven_this_season_false_in_true_preseason():
    # Nobody's team has played yet — zero starts is uninformative, not evidence of anything.
    element = {"team": 7, "starts": 0}
    assert _is_unproven_this_season(element, {7: 0}) is False
    assert _is_unproven_this_season(element, {}) is False


def test_is_unproven_this_season_false_once_a_player_has_started():
    element = {"team": 7, "starts": 2}
    assert _is_unproven_this_season(element, {7: 3}) is False


def test_match_player_names_reports_unmatched():
    matched, unmatched = match_player_names(["Nonexistent Player"], _pool())
    assert matched == []
    assert unmatched == ["Nonexistent Player"]


class _FakeEntryClient:
    """Squad: elements 1 (starter), 2 (starter), 3 (bench) — position 1-11 = starting XI."""

    def bootstrap(self):
        return {"events": [{"id": 1, "is_current": True, "finished": False}]}

    def current_event(self, bootstrap=None):
        return 1

    def entry_picks(self, entry_id, event):
        return {
            "picks": [
                {"element": 1, "position": 1},
                {"element": 2, "position": 5},
                {"element": 3, "position": 12},
            ]
        }


def test_entry_squad_and_starters_splits_by_position():
    pool = [
        CandidatePlayer(id="1", name="A", pos="GK", team="X", price=5.0, xp=3.0),
        CandidatePlayer(id="2", name="B", pos="DEF", team="X", price=5.0, xp=4.0),
        CandidatePlayer(id="3", name="C", pos="DEF", team="X", price=5.0, xp=2.0),
    ]
    squad, starter_ids = entry_squad_and_starters(_FakeEntryClient(), entry_id=1, pool=pool)
    assert {p.id for p in squad} == {"1", "2", "3"}
    assert starter_ids == {"1", "2"}  # position 12 (element 3) is bench, not a starter


def test_risk_flags_flags_non_available_status_with_a_replacement():
    healthy = CandidatePlayer(id="1", name="Healthy", pos="MID", team="X", price=8.0, xp=5.0)
    doubtful = CandidatePlayer(id="2", name="Doubtful", pos="MID", team="Y", price=8.0, xp=6.0)
    squad = [healthy, doubtful]
    pool = squad + [
        CandidatePlayer(id="3", name="BenchOption", pos="MID", team="Z", price=8.0, xp=4.0),
        CandidatePlayer(id="4", name="BetterOption", pos="MID", team="Z", price=8.0, xp=7.0),
    ]
    element_by_id = {
        "1": {"status": "a", "news": ""},
        "2": {"status": "d", "news": "Knock - 50% chance of playing"},
    }
    flags = _risk_flags(squad, pool, element_by_id)
    assert len(flags) == 1
    assert flags[0].player.id == "2"
    assert flags[0].status == "d"
    assert flags[0].suggested_replacement.id == "4"  # highest xP same-position player not in squad


def test_risk_flags_empty_when_all_available():
    squad = [CandidatePlayer(id="1", name="Healthy", pos="MID", team="X", price=8.0, xp=5.0)]
    element_by_id = {"1": {"status": "a", "news": ""}}
    assert _risk_flags(squad, squad, element_by_id) == []
