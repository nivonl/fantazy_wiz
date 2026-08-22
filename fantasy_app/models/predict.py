"""
Turns fitted `strength.Ratings` into a fixture-level score prediction: the full scoreline
probability matrix plus the derived probabilities everything else in this app consumes
(win/draw/loss, clean-sheet, BTTS, over/under). Independent-Poisson grid, same shape as
`ev.py`'s `dixon_coles_matrix` in the prior project, but the inputs come from ratings fit on
real results (strength.py) rather than from inverting bookmaker odds.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import exp, factorial

from fantasy_app.models.strength import Ratings

MAX_GOALS = 10


def _poisson_pmf(k: int, lam: float) -> float:
    return (lam**k) * exp(-lam) / factorial(k)


def score_matrix(lam_home: float, lam_away: float, max_goals: int = MAX_GOALS) -> list[list[float]]:
    """matrix[i][j] = P(home scores i AND away scores j), truncated at max_goals and renormalized."""
    home_probs = [_poisson_pmf(i, lam_home) for i in range(max_goals + 1)]
    away_probs = [_poisson_pmf(j, lam_away) for j in range(max_goals + 1)]
    matrix = [[hp * ap for ap in away_probs] for hp in home_probs]
    total = sum(sum(row) for row in matrix)
    return [[p / total for p in row] for row in matrix]


@dataclass(frozen=True)
class FixturePrediction:
    home_team_id: str
    away_team_id: str
    lam_home: float
    lam_away: float
    p_home_win: float
    p_draw: float
    p_away_win: float
    p_home_clean_sheet: float
    p_away_clean_sheet: float
    p_btts: float
    p_over_2_5: float
    most_likely_score: tuple[int, int]
    most_likely_score_prob: float


def predict_fixture(
    ratings: Ratings, home_team_id: str, away_team_id: str, max_goals: int = MAX_GOALS
) -> FixturePrediction:
    lam_home, lam_away = ratings.expected_goals(home_team_id, away_team_id)
    matrix = score_matrix(lam_home, lam_away, max_goals)

    p_home_win = sum(matrix[i][j] for i in range(max_goals + 1) for j in range(max_goals + 1) if i > j)
    p_draw = sum(matrix[i][i] for i in range(max_goals + 1))
    p_away_win = sum(matrix[i][j] for i in range(max_goals + 1) for j in range(max_goals + 1) if i < j)

    p_home_cs = sum(matrix[i][0] for i in range(max_goals + 1))  # away scores 0
    p_away_cs = sum(matrix[0][j] for j in range(max_goals + 1))  # home scores 0

    p_btts = sum(
        matrix[i][j] for i in range(1, max_goals + 1) for j in range(1, max_goals + 1)
    )
    p_over_2_5 = sum(
        matrix[i][j] for i in range(max_goals + 1) for j in range(max_goals + 1) if i + j >= 3
    )

    best_i, best_j, best_p = 0, 0, 0.0
    for i in range(max_goals + 1):
        for j in range(max_goals + 1):
            if matrix[i][j] > best_p:
                best_i, best_j, best_p = i, j, matrix[i][j]

    return FixturePrediction(
        home_team_id=home_team_id,
        away_team_id=away_team_id,
        lam_home=lam_home,
        lam_away=lam_away,
        p_home_win=p_home_win,
        p_draw=p_draw,
        p_away_win=p_away_win,
        p_home_clean_sheet=p_home_cs,
        p_away_clean_sheet=p_away_cs,
        p_btts=p_btts,
        p_over_2_5=p_over_2_5,
        most_likely_score=(best_i, best_j),
        most_likely_score_prob=best_p,
    )
