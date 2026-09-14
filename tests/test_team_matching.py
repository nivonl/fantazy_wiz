from fantasy_app.services.team_matching import find_best_match, names_match, normalize_team_name


def test_normalize_strips_suffix_and_aliases():
    assert normalize_team_name("Manchester City FC") == "manchester city"
    assert normalize_team_name("Man City") == "manchester city"
    assert normalize_team_name("Spurs") == "tottenham hotspur"
    assert normalize_team_name("Real Madrid CF") == "real madrid"


def test_normalize_handles_prefix_club_names():
    # Real bug: "AFC" as a PREFIX (a club naming convention, "AFC Bournemouth") wasn't handled at
    # all -- only "X AFC" as a SUFFIX was. football-data.org's "AFC Bournemouth" and FPL's plain
    # "Bournemouth" normalized to two different strings, silently dropping Bournemouth's entire
    # historical-season match history from the ratings fit.
    assert normalize_team_name("AFC Bournemouth") == normalize_team_name("Bournemouth")


def test_normalize_handles_ampersand_variants():
    # Real bug: football-data.org's "Brighton & Hove Albion FC" kept its ampersand after suffix
    # stripping ("brighton & hove albion"), while the "brighton" alias mapped FPL's plain
    # "Brighton" to "brighton hove albion" (no ampersand) -- same silent historical-data loss.
    assert normalize_team_name("Brighton & Hove Albion FC") == normalize_team_name("Brighton")


def test_names_match_across_sources():
    assert names_match("Man Utd", "Manchester United FC")
    assert names_match("Wolves", "Wolverhampton Wanderers FC")
    assert not names_match("Arsenal", "Aston Villa FC")


def test_find_best_match_picks_the_right_candidate():
    candidates = ["Manchester City FC", "Manchester United FC", "Arsenal FC"]
    assert find_best_match("Man City", candidates) == "Manchester City FC"
    assert find_best_match("Arsenal", candidates) == "Arsenal FC"
    assert find_best_match("Nonexistent Town FC", candidates) is None
