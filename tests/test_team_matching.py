from fantasy_app.services.team_matching import find_best_match, names_match, normalize_team_name


def test_normalize_strips_suffix_and_aliases():
    assert normalize_team_name("Manchester City FC") == "manchester city"
    assert normalize_team_name("Man City") == "manchester city"
    assert normalize_team_name("Spurs") == "tottenham hotspur"
    assert normalize_team_name("Real Madrid CF") == "real madrid"


def test_names_match_across_sources():
    assert names_match("Man Utd", "Manchester United FC")
    assert names_match("Wolves", "Wolverhampton Wanderers FC")
    assert not names_match("Arsenal", "Aston Villa FC")


def test_find_best_match_picks_the_right_candidate():
    candidates = ["Manchester City FC", "Manchester United FC", "Arsenal FC"]
    assert find_best_match("Man City", candidates) == "Manchester City FC"
    assert find_best_match("Arsenal", candidates) == "Arsenal FC"
    assert find_best_match("Nonexistent Town FC", candidates) is None
