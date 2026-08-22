"""
Turns a player's multi-season match log (providers/fpl_history.py) into fixture-level insight:
how have they performed against THIS specific opponent over the last 5 PL seasons — both
overall (any club they were at, per the user's request to consider all their PL seasons, not
just time at their current club) and specifically while at their current club — plus an
empirical-Bayes-shrunk adjustment factor for xP so a handful of head-to-head games doesn't
overreact against the player's real overall level.
"""

from __future__ import annotations

from fantasy_app.providers.fpl_history import HistoryRow
from fantasy_app.recommend.fpl import OpponentStats
from fantasy_app.services.team_matching import names_match

PRIOR_WEIGHT = 3.0  # the player's own all-time average is worth this many "games" of evidence
MIN_FACTOR = 0.5
MAX_FACTOR = 1.8


def compute_opponent_stats(rows: list[HistoryRow], opponent: str, current_team: str) -> OpponentStats:
    vs_opponent = [r for r in rows if names_match(r.opponent, opponent)]
    current_team_rows = [r for r in vs_opponent if names_match(r.team, current_team)]
    avg_overall = sum(r.total_points for r in vs_opponent) / len(vs_opponent) if vs_opponent else None
    avg_current = (
        sum(r.total_points for r in current_team_rows) / len(current_team_rows) if current_team_rows else None
    )
    return OpponentStats(
        opponent=opponent,
        games_overall=len(vs_opponent),
        avg_points_overall=round(avg_overall, 2) if avg_overall is not None else None,
        goals_overall=sum(r.goals_scored for r in vs_opponent),
        assists_overall=sum(r.assists for r in vs_opponent),
        games_current_team=len(current_team_rows),
        avg_points_current_team=round(avg_current, 2) if avg_current is not None else None,
    )


def shrinkage_factor(rows: list[HistoryRow], opponent: str) -> float:
    """
    Empirical-Bayes shrinkage: blend this player's scoring specifically against `opponent`
    (any club they were at) with their all-time, all-opponent average, weighted by how many
    head-to-head games actually exist. Zero games collapses cleanly to a neutral 1.0 (pure
    prior) rather than guessing from no evidence; a handful of games gets pulled most of the
    way back to their real level rather than taken at face value.
    """
    if not rows:
        return 1.0
    overall_avg = sum(r.total_points for r in rows) / len(rows)
    if overall_avg <= 0:
        return 1.0
    vs_opponent = [r.total_points for r in rows if names_match(r.opponent, opponent)]
    if not vs_opponent:
        return 1.0
    n = len(vs_opponent)
    shrunk = (sum(vs_opponent) + PRIOR_WEIGHT * overall_avg) / (n + PRIOR_WEIGHT)
    factor = shrunk / overall_avg
    return max(MIN_FACTOR, min(MAX_FACTOR, factor))
