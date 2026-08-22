import math
from datetime import datetime, timedelta

import numpy as np

from fantasy_app.models.strength import MatchResult, fit_ratings


def test_fit_ratings_recovers_relative_attack_order():
    """Given a large synthetic dataset with a known attack/defense/home-advantage generating
    process, the MLE fit should recover the correct relative ordering of team strengths."""
    rng = np.random.default_rng(42)
    true_attack = {"A": 0.6, "B": 0.2, "C": -0.1, "D": -0.5}
    true_defense = {"A": 0.3, "B": 0.1, "C": -0.1, "D": -0.3}
    home_adv = 0.25
    teams = list(true_attack)

    base_date = datetime(2026, 1, 1)
    matches = []
    day = 0
    for home in teams:
        for away in teams:
            if home == away:
                continue
            lam_h = math.exp(true_attack[home] - true_defense[away] + home_adv)
            lam_a = math.exp(true_attack[away] - true_defense[home])
            for _ in range(15):
                hg = int(rng.poisson(lam_h))
                ag = int(rng.poisson(lam_a))
                matches.append(MatchResult(home, away, hg, ag, base_date + timedelta(days=day)))
                day += 1

    # Effectively disable time-decay for this test: all matches should count equally since
    # they're generated from a stationary process, not a team actually improving over time.
    ratings = fit_ratings(matches, decay_half_life_days=1_000_000)

    fitted_order = sorted(teams, key=lambda t: ratings.attack[t], reverse=True)
    true_order = sorted(teams, key=lambda t: true_attack[t], reverse=True)
    assert fitted_order == true_order
    assert ratings.home_advantage > 0


def test_fit_ratings_requires_matches():
    try:
        fit_ratings([])
        assert False, "expected ValueError"
    except ValueError:
        pass
