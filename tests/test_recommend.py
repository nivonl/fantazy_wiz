"""Pure logic tests for the squad-construction/transfer/recommendation modules — synthetic
CandidatePlayer data only, no network calls (see test_fpl_integration.py for the live path)."""

from __future__ import annotations

import pytest

from fantasy_app.recommend.fpl import CandidatePlayer, CLUB_CAP, optimize_squad, suggest_transfers
from fantasy_app.recommend.laliga import recommend_laliga


def _make_pool() -> list[CandidatePlayer]:
    pool = []
    teams = ["Alpha", "Beta", "Gamma", "Delta", "Epsilon", "Zeta"]
    counts = {"GK": 4, "DEF": 8, "MID": 8, "FWD": 5}
    pid = 0
    for pos, n in counts.items():
        for i in range(n):
            pid += 1
            team = teams[i % len(teams)]
            # deliberately varied price/xp so the optimizer has real trade-offs to make
            price = 4.0 + (i % 5) * 1.5
            xp = 2.0 + (i % 4) * 1.3 + (0.5 if pos in ("MID", "FWD") else 0.0)
            pool.append(CandidatePlayer(id=f"p{pid}", name=f"{pos}{i}", pos=pos, team=team, price=price, xp=xp))
    return pool


def test_optimize_squad_respects_constraints():
    pool = _make_pool()
    result = optimize_squad(pool)

    assert len(result.squad) == 15
    assert len(result.starters) == 11
    assert len(result.bench) == 4
    assert result.total_price <= 100.0

    pos_counts: dict[str, int] = {}
    team_counts: dict[str, int] = {}
    for p in result.squad:
        pos_counts[p.pos] = pos_counts.get(p.pos, 0) + 1
        team_counts[p.team] = team_counts.get(p.team, 0) + 1
    assert pos_counts == {"GK": 2, "DEF": 5, "MID": 5, "FWD": 3}
    assert all(c <= CLUB_CAP for c in team_counts.values())

    assert result.captain.xp >= result.vice_captain.xp
    assert result.captain in result.starters


def test_optimize_squad_must_include_forces_a_low_xp_player_in():
    pool = _make_pool()
    weak_fav = CandidatePlayer(id="fav1", name="FavMID", pos="MID", team="Alpha", price=4.5, xp=0.1)
    pool.append(weak_fav)
    result = optimize_squad(pool, must_include_ids=["fav1"])
    assert weak_fav in result.squad


def test_optimize_squad_min_from_team_enforced():
    pool = _make_pool()
    result = optimize_squad(pool, min_from_team={"Alpha": 3})
    alpha_count = sum(1 for p in result.squad if p.team == "Alpha")
    assert alpha_count >= 3


def test_optimize_squad_raises_on_infeasible_constraints():
    pool = _make_pool()
    gks = [p for p in pool if p.pos == "GK"]
    assert len(gks) >= 3
    with pytest.raises(RuntimeError):
        # the squad shape requires exactly 2 GK; forcing 3 GK in via must_include is
        # infeasible by construction, regardless of budget/team-cap.
        optimize_squad(pool, must_include_ids=[gks[0].id, gks[1].id, gks[2].id])


def test_optimize_squad_maximizes_xp_over_a_cheaper_worse_alternative():
    # A pool where one obviously-dominant GK exists (same price, higher xp than the rest) —
    # the optimizer should always take it.
    pool = _make_pool()
    star = CandidatePlayer(id="star_gk", name="StarGK", pos="GK", team="Alpha", price=4.0, xp=99.0)
    pool.append(star)
    result = optimize_squad(pool)
    assert star in result.squad


def test_suggest_transfers_finds_obvious_upgrade():
    weak = CandidatePlayer(id="weak", name="Weak", pos="FWD", team="Alpha", price=5.0, xp=1.0)
    strong = CandidatePlayer(id="strong", name="Strong", pos="FWD", team="Beta", price=5.0, xp=9.0)
    squad = [weak]
    pool = [weak, strong]
    suggestions = suggest_transfers(squad, pool, bank=0.0, free_transfers=1)
    assert len(suggestions) == 1
    assert suggestions[0].player_out.id == "weak"
    assert suggestions[0].player_in.id == "strong"
    assert suggestions[0].is_hit is False


def test_suggest_transfers_respects_budget():
    weak = CandidatePlayer(id="weak", name="Weak", pos="FWD", team="Alpha", price=5.0, xp=1.0)
    too_expensive = CandidatePlayer(id="rich", name="TooExpensive", pos="FWD", team="Beta", price=50.0, xp=9.0)
    squad = [weak]
    pool = [weak, too_expensive]
    suggestions = suggest_transfers(squad, pool, bank=0.0, free_transfers=1)
    assert suggestions == []  # can't afford it, no transfer suggested


def test_recommend_laliga_picks_top_xp_captain_and_flags_upgrades():
    squad = [
        CandidatePlayer(id="s1", name="StarterMID", pos="MID", team="A", price=8.0, xp=4.0),
        CandidatePlayer(id="s2", name="StarterFWD", pos="FWD", team="B", price=9.0, xp=6.0),
    ]
    watchlist = [
        CandidatePlayer(id="w1", name="BetterMID", pos="MID", team="C", price=8.5, xp=7.0),
    ]
    rec = recommend_laliga(squad, squad + watchlist)
    assert rec.captain.id == "s2"  # highest xp in the squad
    assert len(rec.transfer_flags) == 1
    assert rec.transfer_flags[0].player_out.id == "s1"
    assert rec.transfer_flags[0].player_in.id == "w1"
