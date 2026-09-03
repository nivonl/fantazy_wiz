import pytest

from fantasy_app.providers.fpl_history import HistoryRow
from fantasy_app.services import player_radar
from fantasy_app.services.player_radar import (
    GROUP_ALL,
    GROUP_POSITION,
    _category_scores,
    _outfield_categories,
    _per90_rate,
    _percentile,
    build_player_radar_table,
)


def _row(season, minutes=90, round_=1, goals_scored=0, assists=0, **fields):
    return HistoryRow(
        season=season, player="test player", team="Arsenal", opponent="Chelsea", round=round_,
        total_points=2, minutes=minutes, goals_scored=goals_scored, assists=assists, was_home=True,
        price=6.0,
        **fields,
    )


def test_per90_rate_skips_seasons_missing_the_field():
    # 2021-22-style row has no expected_goals column at all (None); 2023-24-style row does.
    rows = [
        _row("2021-22", minutes=90, expected_goals=None),
        _row("2023-24", minutes=90, expected_goals=1.8),
    ]
    rate = _per90_rate(rows, "expected_goals")
    # If the None row were treated as 0 this would be 1.8 / 180 * 90 = 0.9, not 1.8.
    assert rate == pytest.approx(1.8)


def test_per90_rate_no_data_returns_none():
    rows = [_row("2021-22", minutes=90, expected_goals=None)]
    assert _per90_rate(rows, "expected_goals") is None


def test_per90_rate_scales_by_minutes():
    rows = [_row("2024-25", minutes=45, goals_scored=1)]
    assert _per90_rate(rows, "goals_scored") == pytest.approx(2.0)


def test_percentile_direction_and_inversion():
    pool = {"a": 1.0, "b": 2.0, "c": 3.0, "d": 4.0, "e": 5.0}
    # Highest value, higher-is-better -> highest percentile in the pool.
    assert _percentile(pool, "e", higher_is_better=True) == pytest.approx(90.0)
    # Same player, but the stat is "lower is better" (e.g. goals conceded) -> inverted, lowest.
    assert _percentile(pool, "e", higher_is_better=False) == pytest.approx(10.0)
    # Lowest value, higher-is-better -> lowest percentile; inverted -> highest.
    assert _percentile(pool, "a", higher_is_better=True) == pytest.approx(10.0)
    assert _percentile(pool, "a", higher_is_better=False) == pytest.approx(90.0)


def test_percentile_requires_at_least_two_in_pool():
    assert _percentile({"a": 1.0}, "a", higher_is_better=True) is None
    assert _percentile({}, "a", higher_is_better=True) is None
    assert _percentile({"a": 1.0, "b": 2.0}, "z", higher_is_better=True) is None


def test_category_scores_omits_categories_with_no_data():
    categories = _outfield_categories("FWD")
    pools = {"goals_scored": {"me": 5.0, "other": 1.0}}  # only one Scoring field has any pool
    scores = _category_scores(categories, pools, "me")
    assert scores == {"scoring": 75.0}  # single-field average; other 3 categories have zero data


def test_forward_defending_excludes_team_stats():
    fwd_fields = dict(_outfield_categories("FWD")["defending"][1])
    def_fields = dict(_outfield_categories("DEF")["defending"][1])
    assert "clean_sheets" not in fwd_fields
    assert "goals_conceded" not in fwd_fields
    assert "clean_sheets" in def_fields
    assert "goals_conceded" in def_fields
    # Individual defensive actions still count for a forward.
    assert "tackles" in fwd_fields
    assert "defensive_contribution" in fwd_fields


def test_build_player_radar_table_end_to_end(monkeypatch):
    # 3 forwards (a clear "best scorer") + 1 GK, each with >= MIN_SAMPLE_MINUTES qualifying
    # minutes across 3 previous-season games, so both pool inclusion and percentile ranking are
    # exercised without needing real network/archive data.
    history = {
        "top scorer": [
            _row("2025-26", minutes=90, round_=1, goals_scored=3, expected_goals=2.5),
            _row("2025-26", minutes=90, round_=2, goals_scored=2, expected_goals=1.8),
            _row("2025-26", minutes=90, round_=3, goals_scored=1, expected_goals=1.0),
        ],
        "mid scorer": [
            _row("2025-26", minutes=90, round_=1, goals_scored=1, expected_goals=0.8),
            _row("2025-26", minutes=90, round_=2, goals_scored=0, expected_goals=0.4),
            _row("2025-26", minutes=90, round_=3, goals_scored=0, expected_goals=0.3),
        ],
        "low scorer": [
            _row("2025-26", minutes=90, round_=1, goals_scored=0, expected_goals=0.1),
            _row("2025-26", minutes=90, round_=2, goals_scored=0, expected_goals=0.1),
            _row("2025-26", minutes=90, round_=3, goals_scored=0, expected_goals=0.1),
        ],
        "the keeper": [
            _row("2025-26", minutes=90, round_=1, saves=5, clean_sheets=1, goals_conceded=0),
            _row("2025-26", minutes=90, round_=2, saves=2, clean_sheets=0, goals_conceded=2),
            _row("2025-26", minutes=90, round_=3, saves=4, clean_sheets=1, goals_conceded=0),
        ],
        "backup keeper": [
            _row("2025-26", minutes=90, round_=1, saves=1, clean_sheets=0, goals_conceded=3),
            _row("2025-26", minutes=90, round_=2, saves=0, clean_sheets=0, goals_conceded=2),
            _row("2025-26", minutes=90, round_=3, saves=1, clean_sheets=0, goals_conceded=1),
        ],
    }
    monkeypatch.setattr(player_radar.fpl_history, "index_by_player", lambda: history)
    monkeypatch.setattr(player_radar.fpl_history, "current_season_label", lambda: "2026-27")

    bootstrap = {
        "elements": [
            {"id": 1, "element_type": 4, "first_name": "Top", "second_name": "Scorer"},
            {"id": 2, "element_type": 4, "first_name": "Mid", "second_name": "Scorer"},
            {"id": 3, "element_type": 4, "first_name": "Low", "second_name": "Scorer"},
            {"id": 4, "element_type": 1, "first_name": "The", "second_name": "Keeper"},
            {"id": 5, "element_type": 1, "first_name": "Backup", "second_name": "Keeper"},
        ]
    }

    table = build_player_radar_table(bootstrap)

    # The forwards' previous_season data (2025-26) qualifies -- current season is 2026-27.
    top = table["1"]["previous_season"]
    low = table["3"]["previous_season"]
    assert top[GROUP_ALL]["scoring"] > low[GROUP_ALL]["scoring"]
    assert top[GROUP_POSITION]["scoring"] > low[GROUP_POSITION]["scoring"]

    # Forwards get no clean-sheet-based defending signal -- category present but from tackling-
    # style fields only, none of which these synthetic rows populate, so it's omitted entirely.
    assert "defending" not in top

    # Goalkeeper gets the GK-specific category set, no "all players" pool, real position scores.
    gk = table["4"]
    assert gk["categoryLabels"] == {
        "shot_stopping": "Shot Stopping",
        "clean_sheets": "Clean Sheets",
        "goals_prevented": "Goals Prevented",
        "involvement": "Involvement",
    }
    assert gk["previous_season"][GROUP_ALL] is None
    assert gk["previous_season"][GROUP_POSITION] is not None
