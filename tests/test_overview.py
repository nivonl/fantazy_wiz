from fantasy_app.services.overview import _find_fpl_team_id, difficulty_tier


def test_difficulty_tier_thresholds():
    assert difficulty_tier(0.75) == 1  # strong favorite -> easiest
    assert difficulty_tier(0.50) == 2
    assert difficulty_tier(0.40) == 3
    assert difficulty_tier(0.25) == 4
    assert difficulty_tier(0.05) == 5  # heavy underdog -> hardest


def test_difficulty_tier_boundary_values_are_inclusive():
    assert difficulty_tier(0.60) == 1
    assert difficulty_tier(0.20) == 4


def test_find_fpl_team_id_exact_and_fuzzy_match():
    norm_name_by_id = {1: "arsenal", 2: "manchester city", 3: "tottenham hotspur"}
    assert _find_fpl_team_id("Arsenal", norm_name_by_id) == 1
    assert _find_fpl_team_id("Man City", norm_name_by_id) == 2  # normalized alias match
    assert _find_fpl_team_id("Nonexistent FC", norm_name_by_id) is None
