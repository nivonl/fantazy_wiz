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


def test_early_season_l2_shrinks_hot_streak_attack():
    """Two blowout wins early in a season should not produce as extreme an attack rating when
    early_season_l2_boost is on — the GW3 Bogle failure mode in miniature.

    Opponents are given a full current-season sample so only Hot is extra-shrunk; otherwise
    shrinking a porous defense toward 0 can force Hot's attack *up* to explain the same 4–0s.
    """
    base = datetime(2025, 8, 1)
    history: list[MatchResult] = []
    for i in range(40):
        history.append(MatchResult("Hot", "Cold", 1, 1, base + timedelta(days=i)))
        history.append(MatchResult("Cold", "Hot", 1, 1, base + timedelta(days=i, hours=12)))
        history.append(MatchResult("Other", "Fourth", 1, 1, base + timedelta(days=i, hours=1)))
        history.append(MatchResult("Fourth", "Other", 1, 1, base + timedelta(days=i, hours=2)))

    current_start = base + timedelta(days=400)
    current = [
        MatchResult("Hot", "Cold", 4, 0, current_start),
        MatchResult("Hot", "Other", 4, 0, current_start + timedelta(days=7)),
    ]
    # Padding matches among the non-Hot clubs so only Hot is sample-thin.
    for i in range(8):
        current.append(
            MatchResult("Cold", "Other", 1, 1, current_start + timedelta(days=i, hours=3))
        )
        current.append(
            MatchResult("Other", "Fourth", 1, 1, current_start + timedelta(days=i, hours=4))
        )
        current.append(
            MatchResult("Fourth", "Cold", 1, 1, current_start + timedelta(days=i, hours=5))
        )

    matches = history + current
    as_of = current_start + timedelta(days=10)
    current_counts = {"Hot": 2, "Cold": 10, "Other": 10, "Fourth": 8}

    baseline = fit_ratings(
        matches,
        as_of=as_of,
        team_current_season_matches=current_counts,
        early_season_l2_boost=0.0,
    )
    shrunk = fit_ratings(
        matches,
        as_of=as_of,
        team_current_season_matches=current_counts,
        early_season_l2_boost=5.0,
        early_season_full_strength_matches=8,
    )
    assert shrunk.attack["Hot"] < baseline.attack["Hot"]
    lam_base, _ = baseline.expected_goals("Hot", "Cold")
    lam_shrunk, _ = shrunk.expected_goals("Hot", "Cold")
    assert lam_shrunk < lam_base


def test_no_history_l2_boost_shrinks_promoted_team_harder_than_anchored_team():
    """A newly-promoted club with zero rows in the historical blend and an established club with
    real historical seasons behind it can post an identical thin-sample current-season hot streak
    (e.g. clean sheets) -- only the promoted club should get the *extra* no_history_l2_boost
    shrinkage on top of the shared early-season boost (the Hull City / NOTES GW4 failure mode:
    a fitted defense rating far more extreme than any team with a real historical anchor)."""
    base = datetime(2023, 8, 1)
    historical: list[MatchResult] = []
    for i in range(40):
        historical.append(MatchResult("Established", "Filler", 1, 1, base + timedelta(days=i)))
        historical.append(MatchResult("Filler", "Established", 1, 1, base + timedelta(days=i, hours=12)))

    current_start = base + timedelta(days=800)
    current = [
        MatchResult("Promoted", "Filler", 3, 0, current_start),
        MatchResult("Filler", "Promoted", 0, 0, current_start + timedelta(days=7)),
        MatchResult("Established", "Filler", 3, 0, current_start + timedelta(days=1)),
        MatchResult("Filler", "Established", 0, 0, current_start + timedelta(days=8)),
    ]
    # Padding so Filler itself isn't sample-thin.
    for i in range(8):
        current.append(MatchResult("Filler", "Filler2", 1, 1, current_start + timedelta(days=i, hours=3)))
        current.append(MatchResult("Filler2", "Filler", 1, 1, current_start + timedelta(days=i, hours=4)))

    matches = historical + current
    as_of = current_start + timedelta(days=10)
    current_counts = {"Promoted": 2, "Established": 2, "Filler": 18, "Filler2": 16}

    baseline = fit_ratings(
        matches,
        as_of=as_of,
        team_current_season_matches=current_counts,
        early_season_l2_boost=5.0,
        early_season_full_strength_matches=8,
        no_history_l2_boost=0.0,
    )
    boosted = fit_ratings(
        matches,
        as_of=as_of,
        team_current_season_matches=current_counts,
        early_season_l2_boost=5.0,
        early_season_full_strength_matches=8,
        no_history_l2_boost=10.0,
    )

    promoted_shrinkage = baseline.defense["Promoted"] - boosted.defense["Promoted"]
    established_shrinkage = baseline.defense["Established"] - boosted.defense["Established"]
    # Established already has a real historical anchor so it isn't *directly* penalized by
    # no_history_l2_boost -- it still moves some from sharing an opponent (Filler) with Promoted
    # in the same joint fit, but should move distinctly less than Promoted itself.
    assert promoted_shrinkage > established_shrinkage > 0
