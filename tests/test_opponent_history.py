import pytest

from fantasy_app.providers.fpl_history import HistoryRow
from fantasy_app.services.opponent_history import (
    MAX_FACTOR,
    MIN_FACTOR,
    compute_opponent_stats,
    shrinkage_factor,
)


def _row(season, team, opponent, points, goals=0, assists=0, minutes=90):
    return HistoryRow(
        season=season, player="test player", team=team, opponent=opponent, round=1,
        total_points=points, minutes=minutes, goals_scored=goals, assists=assists, was_home=True,
        price=6.0,
    )


def test_compute_opponent_stats_splits_overall_vs_current_team():
    rows = [
        _row("2021-22", "Everton", "Arsenal", 4, goals=1),  # different (old) club vs Arsenal
        _row("2023-24", "Newcastle", "Arsenal", 8, goals=1, assists=1),  # current club vs Arsenal
        _row("2024-25", "Newcastle", "Arsenal", 2),  # current club vs Arsenal
        _row("2024-25", "Newcastle", "Chelsea", 10),  # current club, different opponent — excluded
    ]
    stats = compute_opponent_stats(rows, opponent="Arsenal", current_team="Newcastle")
    assert stats.games_overall == 3
    # avg_points_* is rounded to 2dp for display, so compare with matching tolerance.
    assert stats.avg_points_overall == pytest.approx((4 + 8 + 2) / 3, abs=1e-2)
    assert stats.goals_overall == 2
    assert stats.assists_overall == 1
    assert stats.games_current_team == 2
    assert stats.avg_points_current_team == pytest.approx((8 + 2) / 2, abs=1e-2)


def test_compute_opponent_stats_no_history_returns_none_averages():
    stats = compute_opponent_stats([], opponent="Arsenal", current_team="Newcastle")
    assert stats.games_overall == 0
    assert stats.avg_points_overall is None
    assert stats.games_current_team == 0
    assert stats.avg_points_current_team is None


def test_shrinkage_factor_neutral_with_no_data():
    assert shrinkage_factor([], "Arsenal") == 1.0


def test_shrinkage_factor_neutral_with_no_h2h():
    rows = [_row("2023-24", "Newcastle", "Chelsea", 6), _row("2024-25", "Newcastle", "Spurs", 4)]
    assert shrinkage_factor(rows, "Arsenal") == 1.0


def test_shrinkage_factor_pulls_toward_overall_average():
    # overall avg = (2+4+6+8+10)/5 = 6; single h2h game (vs Arsenal) scored 8.
    # shrunk = (8 + 3*6)/(1+3) = 6.5 -> factor = 6.5/6 ≈ 1.083, well short of the raw 8/6 ratio.
    rows = [
        _row("2020-21", "X", "Chelsea", 2),
        _row("2021-22", "X", "Spurs", 4),
        _row("2022-23", "X", "Everton", 6),
        _row("2023-24", "X", "Arsenal", 8),
        _row("2024-25", "X", "Liverpool", 10),
    ]
    factor = shrinkage_factor(rows, "Arsenal")
    assert factor == pytest.approx(6.5 / 6, rel=1e-6)
    assert factor < 8 / 6


def test_shrinkage_factor_is_clamped():
    rows = [_row("2022-23", "X", "Chelsea", 1), _row("2023-24", "X", "Spurs", 1), _row("2024-25", "X", "Arsenal", 60)]
    factor = shrinkage_factor(rows, "Arsenal")
    assert MIN_FACTOR <= factor <= MAX_FACTOR
