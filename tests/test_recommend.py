"""Pure logic tests for the squad-construction/transfer/recommendation modules — synthetic
CandidatePlayer data only, no network calls (see test_fpl_integration.py for the live path)."""

from __future__ import annotations

import pytest

from fantasy_app.recommend.fpl import (
    CandidatePlayer,
    CLUB_CAP,
    MAX_SUGGESTED_TRANSFERS,
    best_transfer_targets_by_position,
    find_trade_combos_for_target,
    optimize_squad,
    suggest_transfer_package,
    suggest_transfers,
)
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


def test_optimize_squad_starting_xp_counts_the_captain_twice_and_never_the_bench():
    pool = _make_pool()
    result = optimize_squad(pool)

    assert result.captain in result.starters
    expected = round(sum(p.xp for p in result.starters) + result.captain.xp, 2)
    assert result.starting_xp == expected
    # Sanity: that's strictly more than a plain (uncaptained) starting-XI sum whenever the
    # captain has any xp at all -- the whole point of doubling them.
    assert result.starting_xp > round(sum(p.xp for p in result.starters), 2)


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


def test_best_transfer_targets_picks_highest_xp_per_position_within_budget():
    squad = [CandidatePlayer(id="owned_mid", name="Owned", pos="MID", team="Alpha", price=6.0, xp=5.0)]
    pool = squad + [
        CandidatePlayer(id="cheap_mid", name="CheapMid", pos="MID", team="Beta", price=5.0, xp=3.0),
        CandidatePlayer(id="best_mid", name="BestMid", pos="MID", team="Gamma", price=6.5, xp=9.0),
        CandidatePlayer(id="too_pricey_mid", name="Pricey", pos="MID", team="Delta", price=15.0, xp=20.0),
        CandidatePlayer(id="only_fwd", name="OnlyFwd", pos="FWD", team="Epsilon", price=7.0, xp=4.0),
    ]
    targets = best_transfer_targets_by_position(pool, squad, budget=10.0)
    assert targets["MID"].id == "best_mid"  # highest xp of the affordable, unowned MIDs
    assert targets["FWD"].id == "only_fwd"
    assert targets["GK"] is None  # no GK candidates in the pool at all


def test_best_transfer_targets_never_returns_an_owned_player():
    owned = CandidatePlayer(id="owned_fwd", name="Owned", pos="FWD", team="Alpha", price=5.0, xp=99.0)
    squad = [owned]
    pool = [owned, CandidatePlayer(id="rival_fwd", name="Rival", pos="FWD", team="Beta", price=5.0, xp=1.0)]
    targets = best_transfer_targets_by_position(pool, squad, budget=100.0)
    assert targets["FWD"].id == "rival_fwd"


def test_best_transfer_targets_none_when_nothing_affordable():
    squad: list[CandidatePlayer] = []
    pool = [CandidatePlayer(id="rich_gk", name="Rich", pos="GK", team="Alpha", price=6.0, xp=5.0)]
    targets = best_transfer_targets_by_position(pool, squad, budget=4.0)
    assert targets["GK"] is None


def _base_squad():
    """15 players, exactly 2/5/5/3, each on its own distinct team (no incidental club-cap
    interactions unless a test deliberately introduces one) — a plain, affordable starting
    point for the trade-combo tests below."""
    squad = []
    squad.append(CandidatePlayer(id="gk0", name="GK0", pos="GK", team="GK-A", price=4.0, xp=3.0))
    squad.append(CandidatePlayer(id="gk1", name="GK1", pos="GK", team="GK-B", price=4.0, xp=3.0))
    for i in range(5):
        squad.append(CandidatePlayer(id=f"def{i}", name=f"Def{i}", pos="DEF", team=f"DEF-{i}", price=4.5, xp=3.0))
    for i in range(5):
        squad.append(CandidatePlayer(id=f"mid{i}", name=f"Mid{i}", pos="MID", team=f"MID-{i}", price=6.0, xp=4.0))
    for i in range(3):
        squad.append(CandidatePlayer(id=f"fwd{i}", name=f"Fwd{i}", pos="FWD", team=f"FWD-{i}", price=7.0, xp=5.0))
    return squad


def _new_squad_after(current_squad, combo):
    out_ids = {p.id for p in combo.players_out}
    return [p for p in current_squad if p.id not in out_ids] + combo.players_in


def test_find_trade_combos_single_swap_when_affordable():
    squad = _base_squad()
    wanted = CandidatePlayer(id="wanted_mid", name="WantedMid", pos="MID", team="NewTeam", price=8.0, xp=9.0)
    pool = squad + [wanted]

    combos = find_trade_combos_for_target(squad, wanted, pool, bank=2.0, free_transfers=1, top_k=1)

    best = combos[0]
    assert best.hits == 0
    assert len(best.players_out) == 1
    assert best.players_out[0].pos == "MID"
    assert best.players_in == [wanted]
    new_squad = _new_squad_after(squad, best)
    assert sum(p.price for p in new_squad) <= 2.0 + sum(p.price for p in squad) + 1e-6


def test_find_trade_combos_needs_secondary_downgrade_to_close_budget_gap():
    squad = _base_squad()
    # Priced well beyond what selling any single MID (6.0) plus a 2.0 bank can cover (8.0).
    wanted = CandidatePlayer(id="wanted_mid", name="WantedMid", pos="MID", team="NewTeam", price=13.0, xp=9.0)
    # The only way to free the remaining 5.0m: downgrade one FWD (7.0 each) to this cheaper one.
    cheap_fwd = CandidatePlayer(id="cheap_fwd", name="CheapFwd", pos="FWD", team="CheapTeam", price=2.0, xp=3.0)
    pool = squad + [wanted, cheap_fwd]

    combos = find_trade_combos_for_target(squad, wanted, pool, bank=2.0, free_transfers=2)

    best = combos[0]
    assert wanted in best.players_in
    assert cheap_fwd in best.players_in
    assert len(best.players_out) == 2
    assert any(p.pos == "FWD" for p in best.players_out)
    new_squad = _new_squad_after(squad, best)
    assert sum(p.price for p in new_squad) <= 2.0 + sum(p.price for p in squad) + 1e-6


def test_find_trade_combos_never_breaks_club_cap():
    squad = _base_squad()
    # Stack 3 non-MID players on "Stack" (at the cap already) plus one of the MIDs.
    squad = [
        p if p.id not in {"def0", "fwd0", "mid0"} else CandidatePlayer(p.id, p.name, p.pos, "Stack", p.price, p.xp)
        for p in squad
    ]
    wanted = CandidatePlayer(id="wanted_mid", name="WantedMid", pos="MID", team="Stack", price=8.0, xp=9.0)
    pool = squad + [wanted]

    combos = find_trade_combos_for_target(squad, wanted, pool, bank=2.0, free_transfers=2, top_k=3)

    assert combos  # at least one legal combo exists
    for combo in combos:
        new_squad = _new_squad_after(squad, combo)
        team_counts: dict[str, int] = {}
        for p in new_squad:
            team_counts[p.team] = team_counts.get(p.team, 0) + 1
        assert all(count <= CLUB_CAP for count in team_counts.values())


def test_find_trade_combos_hit_cost_suppresses_an_unaffordable_extra_swap():
    squad = _base_squad()
    wanted = CandidatePlayer(id="wanted_mid", name="WantedMid", pos="MID", team="NewTeam", price=8.0, xp=9.0)
    # Same price as fwd2 (no budget impact), a modest +1.5 xp upgrade -- worth taking for free,
    # not worth an extra -4 hit.
    small_upgrade = CandidatePlayer(id="small_upgrade_fwd", name="SmallUpgrade", pos="FWD", team="UpTeam", price=7.0, xp=6.5)
    pool = squad + [wanted, small_upgrade]

    with_one_free = find_trade_combos_for_target(squad, wanted, pool, bank=2.0, free_transfers=1)[0]
    assert with_one_free.hits == 0
    assert small_upgrade not in with_one_free.players_in  # not worth a 2nd hit for +1.5 xp

    with_two_free = find_trade_combos_for_target(squad, wanted, pool, bank=2.0, free_transfers=2)[0]
    assert with_two_free.hits == 0
    assert small_upgrade in with_two_free.players_in  # free to take now, so take it


def test_find_trade_combos_already_owned_raises():
    squad = _base_squad()
    owned = next(p for p in squad if p.id == "mid0")
    with pytest.raises(RuntimeError, match="already in this squad"):
        find_trade_combos_for_target(squad, owned, squad, bank=0.0, free_transfers=1)


def test_find_trade_combos_unaffordable_even_liquidating_everything_raises():
    squad = _base_squad()
    wanted = CandidatePlayer(id="wanted_mid", name="WantedMid", pos="MID", team="NewTeam", price=999.0, xp=9.0)
    pool = squad + [wanted]
    with pytest.raises(RuntimeError, match="No legal way to fit"):
        find_trade_combos_for_target(squad, wanted, pool, bank=0.0, free_transfers=1)


def test_suggest_transfer_package_finds_budget_pooled_upgrade_greedy_cant_reach():
    squad = _base_squad()
    # Priced beyond what selling any single MID (6.0) plus 0 bank can cover -- unreachable by a
    # same-position, self-funded swap. Only affordable by also downgrading a FWD elsewhere, which
    # greedy would never do on its own since that downgrade is a negative-gain move in isolation.
    premium_mid = CandidatePlayer(id="premium_mid", name="PremiumMid", pos="MID", team="NewTeam", price=12.0, xp=20.0)
    cheap_fwd = CandidatePlayer(id="cheap_fwd", name="CheapFwd", pos="FWD", team="CheapTeam", price=1.0, xp=1.0)
    pool = squad + [premium_mid, cheap_fwd]

    greedy = suggest_transfers(squad, pool, bank=0.0, free_transfers=2)
    assert premium_mid.id not in {t.player_in.id for t in greedy}

    package = suggest_transfer_package(squad, pool, bank=0.0, free_transfers=2)
    best = package[0]
    assert premium_mid in best.players_in
    assert cheap_fwd in best.players_in
    assert best.hits == 0
    assert best.xp_gain > 0
    new_squad = _new_squad_after(squad, best)
    assert sum(p.price for p in new_squad) <= sum(p.price for p in squad) + 1e-6


def test_suggest_transfer_package_empty_when_nothing_beats_the_current_squad():
    squad = _base_squad()
    pool = list(squad)  # no alternative anywhere in the pool
    assert suggest_transfer_package(squad, pool, bank=0.0, free_transfers=2) == []


def test_suggest_transfer_package_never_exceeds_the_transfer_cap():
    # Every squad member is worthless (e.g. injured/left the club) and the pool is full of much
    # better replacements at every position -- unbounded, "sell everyone" would be optimal even
    # after paying for every hit. That's the Wildcard-lift calculation, not a transfer package,
    # so the default cap (max(MAX_SUGGESTED_TRANSFERS, free_transfers)) must hold it back.
    squad = [CandidatePlayer(id=p.id, name=p.name, pos=p.pos, team=p.team, price=p.price, xp=0.0) for p in _base_squad()]
    pool = squad + [
        CandidatePlayer(id=f"star_{p.pos}_{i}", name=f"Star{p.pos}{i}", pos=p.pos, team=f"Star{i}", price=p.price, xp=20.0)
        for i, p in enumerate(squad)
    ]

    combos = suggest_transfer_package(squad, pool, bank=0.0, free_transfers=2)

    assert combos
    assert len(combos[0].players_out) <= max(MAX_SUGGESTED_TRANSFERS, 2)


def test_suggest_transfer_package_never_breaks_club_cap():
    squad = _base_squad()
    squad = [
        p if p.id not in {"def0", "fwd0", "mid0"} else CandidatePlayer(p.id, p.name, p.pos, "Stack", p.price, p.xp)
        for p in squad
    ]
    premium_mid = CandidatePlayer(id="premium_mid", name="PremiumMid", pos="MID", team="Stack", price=12.0, xp=20.0)
    cheap_fwd = CandidatePlayer(id="cheap_fwd", name="CheapFwd", pos="FWD", team="Stack", price=1.0, xp=1.0)
    pool = squad + [premium_mid, cheap_fwd]

    combos = suggest_transfer_package(squad, pool, bank=0.0, free_transfers=2, top_k=2)
    for combo in combos:
        new_squad = _new_squad_after(squad, combo)
        team_counts: dict[str, int] = {}
        for p in new_squad:
            team_counts[p.team] = team_counts.get(p.team, 0) + 1
        assert all(count <= CLUB_CAP for count in team_counts.values())


def _squad_with_a_clear_bench_gk():
    """_base_squad(), but with one GK given a commanding lead (always starts) and the other a
    low score (always benched, since only 1 of 2 GKs ever starts) -- a fixture for proving a
    "bench-only upgrade" is no longer counted as a real gain."""
    squad = _base_squad()
    return [
        CandidatePlayer(p.id, p.name, p.pos, p.team, p.price, 10.0) if p.id == "gk0"
        else CandidatePlayer(p.id, p.name, p.pos, p.team, p.price, 1.0) if p.id == "gk1"
        else p
        for p in squad
    ]


def test_suggest_transfer_package_does_not_count_a_bench_only_upgrade_as_real_gain():
    squad = _squad_with_a_clear_bench_gk()
    # A big raw upgrade over the bench GK (1.0 -> 8.0) but still clearly worse than the starting
    # GK (10.0) -- neither ever starts, so the real gameweek score doesn't move at all. The old
    # flat-15-sum objective would have reported this as a +7.0 xp gain.
    bench_upgrade_gk = CandidatePlayer(id="bench_upgrade_gk", name="BenchUpgradeGK", pos="GK", team="NewTeam", price=4.0, xp=8.0)
    pool = squad + [bench_upgrade_gk]

    combos = suggest_transfer_package(squad, pool, bank=0.0, free_transfers=1)

    assert not combos or combos[0].xp_gain <= 1e-6


def test_suggest_transfers_does_not_suggest_a_bench_only_upgrade():
    squad = _squad_with_a_clear_bench_gk()
    bench_upgrade_gk = CandidatePlayer(id="bench_upgrade_gk", name="BenchUpgradeGK", pos="GK", team="NewTeam", price=4.0, xp=8.0)
    pool = squad + [bench_upgrade_gk]

    suggestions = suggest_transfers(squad, pool, bank=0.0, free_transfers=1)

    assert bench_upgrade_gk.id not in {t.player_in.id for t in suggestions}


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
