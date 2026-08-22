import pytest

from fantasy_app.models.player_points import player_xp


def test_mid_xp_matches_hand_computation():
    result = player_xp(
        name="Test MID",
        pos="MID",
        price=8.0,
        lam_team=1.8,
        lam_opponent=1.0,
        p_cs=0.4,
        goal_share=0.3,
        assist_share=0.2,
        start_prob=0.9,
        yellow_prob=0.15,
    )
    # appearance 2 + goals(1.8*0.3*5=2.7) + assists(0.2*3=0.6) + cs(0.4*1=0.4)
    # + conceded(0, MID exempt) + cards(0.15*-1=-0.15) = 5.55, scaled by start_prob 0.9 = 4.995
    assert result.xp == pytest.approx(4.995, abs=1e-6)
    assert result.xp_per_price == pytest.approx(4.995 / 8.0, abs=1e-4)


def test_captain_doubles_xp():
    base = player_xp(
        name="X", pos="FWD", price=9.0, lam_team=2.0, lam_opponent=1.0, p_cs=0.3, goal_share=0.4
    )
    captained = player_xp(
        name="X", pos="FWD", price=9.0, lam_team=2.0, lam_opponent=1.0, p_cs=0.3, goal_share=0.4,
        is_captain=True,
    )
    assert captained.xp == pytest.approx(base.xp * 2, abs=1e-6)


def test_def_conceded_penalty_applied():
    result = player_xp(
        name="Test DEF", pos="DEF", price=5.0, lam_team=1.2, lam_opponent=2.0, p_cs=0.2,
        start_prob=1.0, yellow_prob=0.0,
    )
    # appearance 2 + cs(0.2*4=0.8) + conceded(-2.0/2=-1.0) = 1.8
    assert result.xp == pytest.approx(1.8, abs=1e-6)


def test_fwd_exempt_from_conceded_and_clean_sheet():
    result = player_xp(
        name="Test FWD", pos="FWD", price=7.0, lam_team=1.5, lam_opponent=3.0, p_cs=0.1,
        start_prob=1.0, yellow_prob=0.0,
    )
    # clean_sheet_pts for FWD is 0 and FWD is exempt from the conceded penalty
    assert result.breakdown["clean_sheet"] == 0.0
    assert result.breakdown["conceded"] == 0.0
