"""
Team strength ratings, fit directly from historical match results (goals for/against) —
NOT derived from bookmaker odds. This is the deliberate departure from
`prev_project/betting/tools/ev.py`, which backs expected goals out of sharp lines; that's
fine for a one-off knockout fixture but this product runs over a full domestic season where
we have hundreds of prior results to learn from directly.

Model: for a match between home team h and away team a,
    lambda_home = exp(attack[h] - defense[a] + home_advantage)
    lambda_away = exp(attack[a] - defense[h])
and each side's goals are ~ Poisson(lambda). Parameters are fit by maximizing the
(time-decay-weighted) Poisson log-likelihood over observed results, with a small L2 penalty
on attack/defense for identifiability (the log-linear form is only defined up to an additive
shift between attack and defense scales; the penalty pins it down instead of an explicit
equality constraint, which keeps the optimizer a plain unconstrained L-BFGS-B problem).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

import numpy as np
from scipy.optimize import minimize
from scipy.special import gammaln


@dataclass(frozen=True)
class MatchResult:
    home_team_id: str
    away_team_id: str
    home_goals: int
    away_goals: int
    played_at: datetime


@dataclass(frozen=True)
class Ratings:
    attack: dict[str, float]
    defense: dict[str, float]
    home_advantage: float

    def expected_goals(self, home_team_id: str, away_team_id: str) -> tuple[float, float]:
        # A team absent from the fit (newly promoted, or simply hasn't played yet) gets a
        # neutral attack=defense=0.0 prior rather than a KeyError — consistent with the L2
        # penalty in fit_ratings already shrinking sparse teams toward exactly this value, so
        # "no data at all" is just the limit of that same shrinkage, not a special case.
        attack_home = self.attack.get(home_team_id, 0.0)
        defense_home = self.defense.get(home_team_id, 0.0)
        attack_away = self.attack.get(away_team_id, 0.0)
        defense_away = self.defense.get(away_team_id, 0.0)
        lam_home = math.exp(attack_home - defense_away + self.home_advantage)
        lam_away = math.exp(attack_away - defense_home)
        return lam_home, lam_away


def fit_ratings(
    matches: list[MatchResult],
    as_of: datetime | None = None,
    decay_half_life_days: float = 180.0,
    l2: float = 0.005,
) -> Ratings:
    """
    Fit attack/defense/home-advantage from a list of played matches. Recent matches are
    weighted more heavily via exponential decay (half-life in days, relative to `as_of`,
    which defaults to the most recent match's date).
    """
    if not matches:
        raise ValueError("fit_ratings requires at least one match")

    as_of = as_of or max(m.played_at for m in matches)
    team_ids = sorted({m.home_team_id for m in matches} | {m.away_team_id for m in matches})
    idx = {t: i for i, t in enumerate(team_ids)}
    n = len(team_ids)

    weights = np.array(
        [0.5 ** (max((as_of - m.played_at).days, 0) / decay_half_life_days) for m in matches]
    )
    home_idx = np.array([idx[m.home_team_id] for m in matches])
    away_idx = np.array([idx[m.away_team_id] for m in matches])
    home_goals = np.array([m.home_goals for m in matches], dtype=float)
    away_goals = np.array([m.away_goals for m in matches], dtype=float)

    def unpack(x: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
        return x[:n], x[n : 2 * n], x[2 * n]

    def neg_log_likelihood(x: np.ndarray) -> float:
        attack, defense, home_adv = unpack(x)
        lam_home = np.clip(np.exp(attack[home_idx] - defense[away_idx] + home_adv), 1e-6, 15.0)
        lam_away = np.clip(np.exp(attack[away_idx] - defense[home_idx]), 1e-6, 15.0)
        ll_home = home_goals * np.log(lam_home) - lam_home - gammaln(home_goals + 1)
        ll_away = away_goals * np.log(lam_away) - lam_away - gammaln(away_goals + 1)
        log_lik = float(np.sum(weights * (ll_home + ll_away)))
        penalty = l2 * float(np.sum(attack**2) + np.sum(defense**2))
        return -log_lik + penalty

    x0 = np.zeros(2 * n + 1)
    x0[2 * n] = 0.25  # sane home-advantage starting point speeds convergence
    result = minimize(neg_log_likelihood, x0, method="L-BFGS-B")
    attack, defense, home_adv = unpack(result.x)

    return Ratings(
        attack={t: float(attack[idx[t]]) for t in team_ids},
        defense={t: float(defense[idx[t]]) for t in team_ids},
        home_advantage=float(home_adv),
    )


def team_goal_averages(matches: list[MatchResult]) -> dict[str, float]:
    """Mean goals scored per match, per team, over the same match list used to fit ratings.
    Used upstream to turn a player's raw per-match goal rate into a *share* of their team's
    output, so that share can then be rescaled by a specific fixture's expected goals."""
    goals: dict[str, list[int]] = {}
    for m in matches:
        goals.setdefault(m.home_team_id, []).append(m.home_goals)
        goals.setdefault(m.away_team_id, []).append(m.away_goals)
    return {team_id: sum(vals) / len(vals) for team_id, vals in goals.items()}
