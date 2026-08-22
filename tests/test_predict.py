from fantasy_app.models.predict import predict_fixture, score_matrix
from fantasy_app.models.strength import Ratings


def test_score_matrix_sums_to_one():
    m = score_matrix(1.4, 1.1)
    total = sum(sum(row) for row in m)
    assert abs(total - 1.0) < 1e-9


def test_score_matrix_is_nonnegative():
    m = score_matrix(2.0, 0.3)
    assert all(p >= 0 for row in m for p in row)


def test_predict_fixture_higher_attack_favoured():
    ratings = Ratings(attack={"H": 0.8, "A": -0.2}, defense={"H": 0.1, "A": 0.1}, home_advantage=0.2)
    pred = predict_fixture(ratings, "H", "A")
    assert pred.p_home_win > pred.p_away_win
    assert abs(pred.p_home_win + pred.p_draw + pred.p_away_win - 1.0) < 1e-6


def test_predict_fixture_clean_sheet_probs_reasonable():
    ratings = Ratings(attack={"H": -2.0, "A": -2.0}, defense={"H": 2.0, "A": 2.0}, home_advantage=0.0)
    pred = predict_fixture(ratings, "H", "A")
    assert pred.p_home_clean_sheet > 0.5
    assert pred.p_away_clean_sheet > 0.5


def test_predict_fixture_handles_team_missing_from_ratings():
    # e.g. a newly-promoted team with zero fitted history — must not KeyError, and should
    # fall back to a neutral (0.0/0.0) prior for the missing side only.
    ratings = Ratings(attack={"H": 0.5}, defense={"H": 0.1}, home_advantage=0.2)
    pred = predict_fixture(ratings, "H", "PROMOTED_TEAM")
    assert pred.lam_home > 0
    assert pred.lam_away > 0
    assert abs(pred.p_home_win + pred.p_draw + pred.p_away_win - 1.0) < 1e-6
