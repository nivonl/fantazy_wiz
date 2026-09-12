from datetime import datetime, timezone

import pytest

from fantasy_app.services.fpl_service import (
    _expected_defcon_points_if_playing,
    _expected_saves_if_playing,
    _fixture_assist_share,
)
from fantasy_app.services.fpl_service import PriceRatePrior
from fantasy_app.services.xp_backtest import (
    CutoffFPLClient,
    accumulate_element_asof,
    evidence_bucket,
    mean_absolute_error,
    model_version_ladder,
    momentum_factor_ablation,
    player_rates_for_version,
    require_football_data_token,
    summarize_mae_by_bucket,
)


def test_fixture_assist_share_scales_with_lam_team():
    # Same per-90 rate, tougher fixture (higher λ) => more expected assists.
    low = _fixture_assist_share(assist_rate=0.3, lam_team=1.0, team_avg_goals=1.5)
    high = _fixture_assist_share(assist_rate=0.3, lam_team=2.0, team_avg_goals=1.5)
    assert high == pytest.approx(2 * low)
    assert high == pytest.approx(2.0 * (0.3 / 1.5))


def test_expected_saves_only_for_gk_with_minutes():
    gk = {"minutes": 180, "saves": 6}
    assert _expected_saves_if_playing(gk, "GK") == pytest.approx(3.0)
    assert _expected_saves_if_playing(gk, "DEF") == 0.0
    assert _expected_saves_if_playing({"minutes": 0, "saves": 6}, "GK") == 0.0


def test_expected_defcon_points_per_90():
    el = {"minutes": 90, "defensive_contribution": 2}
    assert _expected_defcon_points_if_playing(el) == pytest.approx(2.0)
    assert _expected_defcon_points_if_playing({"minutes": 0}) == 0.0


def test_mean_absolute_error():
    assert mean_absolute_error([1.0, 3.0], [2.0, 1.0]) == pytest.approx(1.5)


def test_cutoff_fpl_client_filters_finished_before_cutoff():
    class Inner:
        def fixtures(self, event=None):
            if event is not None:
                return [{"event": event, "id": 99}]
            return [
                {
                    "finished": True,
                    "kickoff_time": "2025-08-10T14:00:00Z",
                    "id": 1,
                },
                {
                    "finished": True,
                    "kickoff_time": "2025-08-20T14:00:00Z",
                    "id": 2,
                },
                {
                    "finished": False,
                    "kickoff_time": "2025-08-15T14:00:00Z",
                    "id": 3,
                },
            ]

        def bootstrap(self):
            return {}

    cutoff = datetime(2025, 8, 15, tzinfo=timezone.utc)
    client = CutoffFPLClient(Inner(), cutoff)
    finished = client.fixtures()
    assert [f["id"] for f in finished] == [1]
    assert client.fixtures(event=3)[0]["id"] == 99


def test_require_football_data_token_fails_loud():
    try:
        require_football_data_token(lambda: None)
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert "FOOTBALL_DATA_TOKEN" in str(e)


def test_model_version_ladder_names():
    names = [v.name for v in model_version_ladder()]
    assert names == ["V0", "V1", "V1-mom", "V2"]
    assert model_version_ladder(boost=3.0)[-1].early_season_l2_boost == 3.0
    assert model_version_ladder()[2].use_momentum is True


def test_evidence_bucket_edges():
    assert evidence_bucket(0) == "0"
    assert evidence_bucket(1.5) == "1-2"
    assert evidence_bucket(4) == "3-5"
    assert evidence_bucket(6) == "6+"


def test_momentum_factor_ablation_clamped():
    assert momentum_factor_ablation({"form": 8, "points_per_game": 4}) == 1.5  # capped
    assert momentum_factor_ablation({"form": 1, "points_per_game": 4}) == 0.5  # floored
    assert momentum_factor_ablation({"form": 0, "points_per_game": 0}) == 1.0


def test_player_rates_v0_starts_only_ignores_sub_minutes():
    v0 = model_version_ladder()[0]
    flat = {
        "GK": PriceRatePrior(0, 0, 0, 0),
        "DEF": PriceRatePrior(0, 0, 0, 0),
        "MID": PriceRatePrior(0, 0, 0, 0),
        "FWD": PriceRatePrior(0, 0, 0, 0),
    }
    # Sub minutes + assists but starts=0 → V0 hard-zeros rates (Cherki-style failure).
    el = {
        "minutes": 27,
        "starts": 0,
        "goals_scored": 0,
        "assists": 2,
        "element_type": 3,
        "now_cost": 65,
        "chance_of_playing_next_round": None,
    }
    g, a, _ = player_rates_for_version(el, flat, v0)
    assert g == 0.0 and a == 0.0


def test_accumulate_element_asof_sums_prior_rounds_only():
    base = {"id": 1, "now_cost": 70, "element_type": 3, "web_name": "X", "team": 1}
    hist = [
        {"round": 1, "minutes": 90, "goals_scored": 1, "assists": 0, "starts": 1, "total_points": 8, "value": 70},
        {"round": 2, "minutes": 45, "goals_scored": 0, "assists": 1, "starts": 0, "total_points": 4, "value": 71},
        {"round": 3, "minutes": 90, "goals_scored": 0, "assists": 0, "starts": 1, "total_points": 2, "value": 71},
    ]
    asof = accumulate_element_asof(base, hist, before_round=3)
    assert asof["minutes"] == 135
    assert asof["goals_scored"] == 1
    assert asof["assists"] == 1
    assert asof["starts"] == 1
    assert asof["now_cost"] == 71


def test_summarize_mae_by_bucket_overall():
    rows = [
        {"version": "V0", "abs_err": 2.0, "evidence_bucket": "0", "early_season": True},
        {"version": "V0", "abs_err": 4.0, "evidence_bucket": "6+", "early_season": False},
        {"version": "V1", "abs_err": 1.0, "evidence_bucket": "0", "early_season": True},
    ]
    summary = summarize_mae_by_bucket(rows)
    overall = {r["version"]: r for r in summary if r["facet"] == "overall"}
    assert overall["V0"]["mae"] == pytest.approx(3.0)
    assert overall["V1"]["mae"] == pytest.approx(1.0)
