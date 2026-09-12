"""
Full FPL recommendation features: build a squad from scratch, suggest transfers against an
existing squad (single-gameweek or multi-gameweek horizon, depending on the `xp` values the
caller feeds in), and pick the optimal starting XI/captain/vice from a fixed 15. All decisions
are driven by `xp` values the caller computes upstream (models/player_points.py fed by
models/predict.py, orchestrated per-horizon in services/fpl_service.py) — this module is pure
squad-construction/optimization logic, position-and-budget-aware, with no opinion on what
timeframe the xp values represent.
"""

from __future__ import annotations

from dataclasses import dataclass

import pulp

BUDGET = 100.0
CLUB_CAP = 3
SQUAD_SHAPE = {"GK": 2, "DEF": 5, "MID": 5, "FWD": 3}
STARTING_MIN = {"GK": 1, "DEF": 3, "MID": 2, "FWD": 1}
STARTING_MAX = {"GK": 1, "DEF": 5, "MID": 5, "FWD": 3}
STARTING_XI_SIZE = 11
TRANSFER_HIT_COST = 4.0
MAX_SUGGESTED_TRANSFERS = 3

# A pooled-budget package (suggest_transfer_package) only replaces the greedy one-swap-at-a-time
# list (suggest_transfers) in the UI when it's clearly better, not just solver noise/a tie
# dressed up as a different combo -- half a point over a multi-gameweek horizon isn't a
# difference a manager should reshape their transfers around.
PACKAGE_DEAL_MIN_EDGE = 0.5

# suggest_transfers' greedy candidate ranking (in.xp - out.xp) is cheap but position-only -- it
# can't see whether a swap actually changes the starting XI or just strengthens the bench. This
# many of its top raw candidates get their true starting-XI-plus-captain impact checked (a few
# small pick_starting_xi solves, not one per candidate in the whole pool) before the search
# gives up on an iteration.
TRANSFER_SHORTLIST_SIZE = 5


@dataclass(frozen=True)
class OpponentStats:
    """How this player has performed against their upcoming opponent, over the last 5 PL
    seasons — both overall (any club) and specifically while at their current club. Populated
    by services/opponent_history.py; lives here (next to CandidatePlayer) since it's a display
    value object consumed wherever a player is shown, not fetching/business logic itself."""

    opponent: str
    games_overall: int
    avg_points_overall: float | None
    goals_overall: int
    assists_overall: int
    games_current_team: int
    avg_points_current_team: float | None


@dataclass(frozen=True)
class CandidatePlayer:
    id: str
    name: str
    pos: str  # GK | DEF | MID | FWD
    team: str
    price: float
    xp: float
    opponent_stats: OpponentStats | None = None


@dataclass
class SquadResult:
    squad: list[CandidatePlayer]
    starters: list[CandidatePlayer]
    bench: list[CandidatePlayer]  # ordered best-first
    captain: CandidatePlayer
    vice_captain: CandidatePlayer
    total_price: float
    starting_xp: float


@dataclass
class TransferSuggestion:
    player_out: CandidatePlayer
    player_in: CandidatePlayer
    xp_gain: float
    is_hit: bool  # True if this transfer costs -4 (beyond the free allowance)


@dataclass(frozen=True)
class TradeCombo:
    players_out: list[CandidatePlayer]
    players_in: list[CandidatePlayer]  # always includes the wanted player
    hits: int
    hit_cost: float
    xp_gain: float  # net xp change vs the current squad, over whatever horizon `pool` prices in, hits already subtracted
    new_bank: float


def pick_starting_xi(squad: list[CandidatePlayer]) -> tuple[list[CandidatePlayer], list[CandidatePlayer]]:
    """Best valid starting XI (by xp) from a fixed 15; returns (starters, bench_best_first)."""
    prob = pulp.LpProblem("starting_xi", pulp.LpMaximize)
    x = {p.id: pulp.LpVariable(f"start_{p.id}", cat="Binary") for p in squad}
    prob += pulp.lpSum(p.xp * x[p.id] for p in squad)
    prob += pulp.lpSum(x.values()) == STARTING_XI_SIZE
    for pos, lo in STARTING_MIN.items():
        pos_players = [p for p in squad if p.pos == pos]
        prob += pulp.lpSum(x[p.id] for p in pos_players) >= lo
        prob += pulp.lpSum(x[p.id] for p in pos_players) <= STARTING_MAX[pos]
    prob.solve(pulp.PULP_CBC_CMD(msg=False))
    if pulp.LpStatus[prob.status] != "Optimal":
        raise RuntimeError(f"Could not pick a valid starting XI from the given 15 ({pulp.LpStatus[prob.status]}).")

    starters = [p for p in squad if x[p.id].value() == 1]
    bench = sorted((p for p in squad if x[p.id].value() != 1), key=lambda p: p.xp, reverse=True)
    return starters, bench


def _starting_xi_total_with_captain(squad: list[CandidatePlayer]) -> float:
    """
    Starting-XI xp plus the captain's xp a second time -- what a real gameweek score actually
    counts (see optimize_squad's docstring for why bench points don't count the same). Falls
    back to a plain sum over whatever's given when the squad is too small or oddly-shaped to
    field a legal XI at all (e.g. a partial manual entry, or a synthetic/test squad) -- the same
    number every caller of this used before starting-XI-awareness existed, rather than a hard
    failure for a squad that was already being evaluated somehow.
    """
    try:
        starters, _ = pick_starting_xi(squad)
    except RuntimeError:
        return sum(p.xp for p in squad)
    captain = max(starters, key=lambda p: p.xp)
    return sum(p.xp for p in starters) + captain.xp


def optimize_squad(
    pool: list[CandidatePlayer],
    budget: float = BUDGET,
    club_cap: int = CLUB_CAP,
    must_include_ids: list[str] | None = None,
    min_from_team: dict[str, int] | None = None,
) -> SquadResult:
    """
    Build the best 15 from scratch: jointly pick the 15, which 11 of them start, and who
    captains, maximizing starting-XI xp plus the captain's xp a second time (a real gameweek
    score never counts the bench, short of Bench Boost, which is handled separately as its own
    chip lift) — under budget/shape/club-cap. Picking the 15 by raw 15-player total first and
    only choosing a starting XI afterward (the old approach) could rate a squad higher for
    bench strength that never scores a real point; solving both together is what actually
    matches real FPL scoring.

    must_include_ids: player ids that must be in the 15 regardless of xp (e.g. favorite
    players) — the optimizer still picks the other 15-minus-len(must_include_ids) freely.
    min_from_team: {team_name: minimum count in the 15} (e.g. "at least 3 from my favorite
    club") — capped at club_cap since a min above the max would make the problem infeasible.
    """
    must_include_ids = must_include_ids or []
    min_from_team = min_from_team or {}

    prob = pulp.LpProblem("squad_15", pulp.LpMaximize)
    x = {p.id: pulp.LpVariable(f"pick_{p.id}", cat="Binary") for p in pool}
    starter_x = {p.id: pulp.LpVariable(f"start_{p.id}", cat="Binary") for p in pool}
    captain_x = {p.id: pulp.LpVariable(f"cap_{p.id}", cat="Binary") for p in pool}

    prob += (
        pulp.lpSum(p.xp * starter_x[p.id] for p in pool) + pulp.lpSum(p.xp * captain_x[p.id] for p in pool)
    )
    prob += pulp.lpSum(p.price * x[p.id] for p in pool) <= budget

    for pos, count in SQUAD_SHAPE.items():
        prob += pulp.lpSum(x[p.id] for p in pool if p.pos == pos) == count

    teams = {p.team for p in pool}
    for team in teams:
        prob += pulp.lpSum(x[p.id] for p in pool if p.team == team) <= club_cap

    pool_ids = {p.id for p in pool}
    for player_id in must_include_ids:
        if player_id not in pool_ids:
            raise RuntimeError(f"must_include player id {player_id} isn't in the candidate pool.")
        prob += x[player_id] == 1

    for team, min_count in min_from_team.items():
        min_count = min(min_count, club_cap)
        prob += pulp.lpSum(x[p.id] for p in pool if p.team == team) >= min_count

    # Starting XI: 11 of the 15, same position bounds as pick_starting_xi.
    for p in pool:
        prob += starter_x[p.id] <= x[p.id]
    prob += pulp.lpSum(starter_x.values()) == STARTING_XI_SIZE
    for pos, lo in STARTING_MIN.items():
        pos_players = [p for p in pool if p.pos == pos]
        prob += pulp.lpSum(starter_x[p.id] for p in pos_players) >= lo
        prob += pulp.lpSum(starter_x[p.id] for p in pos_players) <= STARTING_MAX[pos]

    # Captain: exactly one starter, doubled via the second xp term in the objective above.
    for p in pool:
        prob += captain_x[p.id] <= starter_x[p.id]
    prob += pulp.lpSum(captain_x.values()) == 1

    prob.solve(pulp.PULP_CBC_CMD(msg=False))
    if pulp.LpStatus[prob.status] != "Optimal":
        raise RuntimeError(
            f"Could not build a valid 15-player squad under the given constraints "
            f"({pulp.LpStatus[prob.status]}) — try relaxing the favorite-team minimum or "
            f"favorite-player picks."
        )

    squad = [p for p in pool if x[p.id].value() == 1]
    starters = [p for p in pool if starter_x[p.id].value() == 1]
    starter_ids = {p.id for p in starters}
    bench = sorted((p for p in squad if p.id not in starter_ids), key=lambda p: p.xp, reverse=True)
    captain = next(p for p in pool if captain_x[p.id].value() == 1)
    vice = max((p for p in starters if p.id != captain.id), key=lambda p: p.xp)

    return SquadResult(
        squad=squad,
        starters=starters,
        bench=bench,
        captain=captain,
        vice_captain=vice,
        total_price=round(sum(p.price for p in squad), 1),
        # Starting XI total plus the captain's own xp a second time -- matches a real gameweek
        # score, not a bare sum of 11 raw xp values.
        starting_xp=round(sum(p.xp for p in starters) + captain.xp, 2),
    )


def best_transfer_targets_by_position(
    pool: list[CandidatePlayer], current_squad: list[CandidatePlayer], budget: float
) -> dict[str, CandidatePlayer | None]:
    """
    For each position, the single best player NOT already in the squad, priced at or below
    `budget`, ranked by the pool's xp — a standalone "if I have this much to spend, who's best
    in each position" lookup, independent of any specific outgoing player. The caller decides
    what `xp` and `budget` mean (e.g. a 5-gameweek-summed pool and bank + an outgoing player's
    sale price). None for a position with no affordable candidate.
    """
    squad_ids = {p.id for p in current_squad}
    return {
        pos: max(
            (p for p in pool if p.pos == pos and p.id not in squad_ids and p.price <= budget),
            key=lambda p: p.xp,
            default=None,
        )
        for pos in SQUAD_SHAPE
    }


_POSITION_ORDER = {"GK": 0, "DEF": 1, "MID": 2, "FWD": 3}


def find_trade_combos_for_target(
    current_squad: list[CandidatePlayer],
    wanted_player: CandidatePlayer,
    pool: list[CandidatePlayer],
    bank: float,
    free_transfers: int,
    club_cap: int = CLUB_CAP,
    hit_cost: float = TRANSFER_HIT_COST,
    top_k: int = 3,
) -> list[TradeCombo]:
    """
    The best (and 2nd/3rd-best) ways to reshuffle `current_squad` -- without a chip -- to end up
    owning `wanted_player`, ranked by projected starting-XI-plus-captain xp net of any transfer
    hits (see optimize_squad's docstring for why bench points don't count the same as a real
    gameweek score). One ILP per combo (the same joint squad/starting-XI/captain pattern as
    optimize_squad), using a standard "no-good cut" to force each re-solve toward a genuinely
    different combination of trades, rather than a bespoke search algorithm. `wanted_player`
    only has to end up in the 15 -- the solver decides whether they'd actually start, same as a
    real squad-depth buy would be.

    Not artificially restricted to the minimum trades needed to afford the target: any transfer
    beyond what's free always costs `hit_cost` in the shared objective, so the solver only makes
    an extra swap when it's independently worth that cost -- exactly the trade-off a manager
    actually faces when taking a hit, not scope creep.
    """
    squad_ids = {p.id for p in current_squad}
    if wanted_player.id in squad_ids:
        raise RuntimeError(f"{wanted_player.name} is already in this squad.")

    pool_by_id = {p.id: p for p in pool}
    for p in current_squad:
        if p.id not in pool_by_id:
            raise RuntimeError(f"'{p.name}' isn't in the candidate pool for this horizon (no fixture?).")
    if wanted_player.id not in pool_by_id:
        raise RuntimeError(f"'{wanted_player.name}' isn't in the candidate pool for this horizon.")

    old_total_xp = _starting_xi_total_with_captain([pool_by_id[p.id] for p in current_squad])
    total_budget = round(bank + sum(pool_by_id[p.id].price for p in current_squad), 2)

    combos: list[TradeCombo] = []
    excluded_solutions: list[tuple[frozenset[str], frozenset[str]]] = []

    for attempt in range(top_k):
        prob = pulp.LpProblem("trade_combo", pulp.LpMaximize)
        x = {p.id: pulp.LpVariable(f"pick_{p.id}", cat="Binary") for p in pool}
        starter_x = {p.id: pulp.LpVariable(f"start_{p.id}", cat="Binary") for p in pool}
        captain_x = {p.id: pulp.LpVariable(f"cap_{p.id}", cat="Binary") for p in pool}
        hits = pulp.LpVariable("hits", lowBound=0)

        prob += (
            pulp.lpSum(p.xp * starter_x[p.id] for p in pool)
            + pulp.lpSum(p.xp * captain_x[p.id] for p in pool)
            - hit_cost * hits
        )
        prob += pulp.lpSum(p.price * x[p.id] for p in pool) <= total_budget

        for pos, count in SQUAD_SHAPE.items():
            prob += pulp.lpSum(x[p.id] for p in pool if p.pos == pos) == count

        for team in {p.team for p in pool}:
            prob += pulp.lpSum(x[p.id] for p in pool if p.team == team) <= club_cap

        prob += x[wanted_player.id] == 1

        for p in pool:
            prob += starter_x[p.id] <= x[p.id]
        prob += pulp.lpSum(starter_x.values()) == STARTING_XI_SIZE
        for pos, lo in STARTING_MIN.items():
            pos_players = [p for p in pool if p.pos == pos]
            prob += pulp.lpSum(starter_x[p.id] for p in pos_players) >= lo
            prob += pulp.lpSum(starter_x[p.id] for p in pos_players) <= STARTING_MAX[pos]

        for p in pool:
            prob += captain_x[p.id] <= starter_x[p.id]
        prob += pulp.lpSum(captain_x.values()) == 1

        transfers_out = pulp.lpSum(1 - x[p.id] for p in current_squad)
        prob += hits >= transfers_out - free_transfers

        for out_ids, in_ids in excluded_solutions:
            prob += pulp.lpSum(x[pid] for pid in out_ids) + pulp.lpSum(1 - x[pid] for pid in in_ids) >= 1

        prob.solve(pulp.PULP_CBC_CMD(msg=False))
        if pulp.LpStatus[prob.status] != "Optimal":
            if attempt == 0:
                raise RuntimeError(
                    f"No legal way to fit {wanted_player.name} into this squad even liquidating "
                    f"everything ({pulp.LpStatus[prob.status]}) -- they may be unaffordable, or "
                    f"push a club over the {club_cap}-per-club cap no matter who's dropped."
                )
            break  # no further genuinely distinct combo exists -- return what we have

        new_squad_ids = {p.id for p in pool if x[p.id].value() == 1}
        players_out = sorted(
            (p for p in current_squad if p.id not in new_squad_ids),
            key=lambda p: _POSITION_ORDER[p.pos],
        )
        players_in = sorted(
            (pool_by_id[pid] for pid in new_squad_ids if pid not in squad_ids),
            key=lambda p: _POSITION_ORDER[p.pos],
        )
        hits_value = round(hits.value())
        new_bank = round(total_budget - sum(pool_by_id[pid].price for pid in new_squad_ids), 2)

        combos.append(
            TradeCombo(
                players_out=players_out,
                players_in=players_in,
                hits=hits_value,
                hit_cost=hits_value * hit_cost,
                xp_gain=round(pulp.value(prob.objective) - old_total_xp, 2),
                new_bank=new_bank,
            )
        )
        excluded_solutions.append((frozenset(p.id for p in players_out), frozenset(p.id for p in players_in)))

    combos.sort(key=lambda c: c.xp_gain, reverse=True)
    return combos


def suggest_transfer_package(
    current_squad: list[CandidatePlayer],
    pool: list[CandidatePlayer],
    bank: float,
    free_transfers: int,
    club_cap: int = CLUB_CAP,
    hit_cost: float = TRANSFER_HIT_COST,
    max_transfers: int | None = None,
    top_k: int = 1,
) -> list[TradeCombo]:
    """
    The best way(s) to use up to `free_transfers` transfers (or a few more, at a hit) to
    reshuffle the whole squad at once, pooling the budget every sale frees up jointly rather
    than each sale only funding its own single replacement. This is what finds "downgrade two
    mid-price players to afford one premium upgrade" — a combo suggest_transfers' one-swap-at-a-
    time greedy search can never reach, since greedy always locks in the single best immediate
    swap without considering that a smaller swap now might have funded a much bigger one later.

    `max_transfers` caps how many players can change hands at all (defaults to the same
    max(MAX_SUGGESTED_TRANSFERS, free_transfers) ceiling suggest_transfers uses) — without it,
    a squad with several injured/departed players makes "spend a dozen hits to half-rebuild the
    team" technically optimal, which isn't a transfer package, it's the Wildcard-lift calculation
    (optimize_squad) wearing this function's name. This is deliberately still a "some transfers"
    tool, not "how many would even be worth it with no cap."

    Ranked by projected starting-XI-plus-captain xp, same as find_trade_combos_for_target and
    optimize_squad — bench points don't count toward a real gameweek score. Same ILP as
    find_trade_combos_for_target, minus the "must end up owning this one named player"
    constraint — so unlike that function, leaving the squad exactly as it is is always a valid
    (if usually not the returned) answer here, never an infeasibility.
    """
    pool_by_id = {p.id: p for p in pool}
    for p in current_squad:
        if p.id not in pool_by_id:
            raise RuntimeError(f"'{p.name}' isn't in the candidate pool for this horizon (no fixture?).")

    if max_transfers is None:
        max_transfers = max(MAX_SUGGESTED_TRANSFERS, free_transfers)

    squad_ids = {p.id for p in current_squad}
    old_total_xp = _starting_xi_total_with_captain([pool_by_id[p.id] for p in current_squad])
    total_budget = round(bank + sum(pool_by_id[p.id].price for p in current_squad), 2)

    combos: list[TradeCombo] = []
    excluded_solutions: list[tuple[frozenset[str], frozenset[str]]] = []

    for _attempt in range(top_k):
        prob = pulp.LpProblem("transfer_package", pulp.LpMaximize)
        x = {p.id: pulp.LpVariable(f"pick_{p.id}", cat="Binary") for p in pool}
        starter_x = {p.id: pulp.LpVariable(f"start_{p.id}", cat="Binary") for p in pool}
        captain_x = {p.id: pulp.LpVariable(f"cap_{p.id}", cat="Binary") for p in pool}
        hits = pulp.LpVariable("hits", lowBound=0)

        prob += (
            pulp.lpSum(p.xp * starter_x[p.id] for p in pool)
            + pulp.lpSum(p.xp * captain_x[p.id] for p in pool)
            - hit_cost * hits
        )
        prob += pulp.lpSum(p.price * x[p.id] for p in pool) <= total_budget

        for pos, count in SQUAD_SHAPE.items():
            prob += pulp.lpSum(x[p.id] for p in pool if p.pos == pos) == count

        for team in {p.team for p in pool}:
            prob += pulp.lpSum(x[p.id] for p in pool if p.team == team) <= club_cap

        for p in pool:
            prob += starter_x[p.id] <= x[p.id]
        prob += pulp.lpSum(starter_x.values()) == STARTING_XI_SIZE
        for pos, lo in STARTING_MIN.items():
            pos_players = [p for p in pool if p.pos == pos]
            prob += pulp.lpSum(starter_x[p.id] for p in pos_players) >= lo
            prob += pulp.lpSum(starter_x[p.id] for p in pos_players) <= STARTING_MAX[pos]

        for p in pool:
            prob += captain_x[p.id] <= starter_x[p.id]
        prob += pulp.lpSum(captain_x.values()) == 1

        transfers_out = pulp.lpSum(1 - x[p.id] for p in current_squad)
        prob += hits >= transfers_out - free_transfers
        prob += transfers_out <= max_transfers

        for out_ids, in_ids in excluded_solutions:
            prob += pulp.lpSum(x[pid] for pid in out_ids) + pulp.lpSum(1 - x[pid] for pid in in_ids) >= 1

        prob.solve(pulp.PULP_CBC_CMD(msg=False))
        if pulp.LpStatus[prob.status] != "Optimal":
            break  # no further genuinely distinct combo exists

        new_squad_ids = {p.id for p in pool if x[p.id].value() == 1}
        players_out = sorted(
            (p for p in current_squad if p.id not in new_squad_ids),
            key=lambda p: _POSITION_ORDER[p.pos],
        )
        if not players_out:
            break  # the optimum is "change nothing" -- not a package worth surfacing, and every
                    # remaining attempt (only excluded from this one) would score no better

        players_in = sorted(
            (pool_by_id[pid] for pid in new_squad_ids if pid not in squad_ids),
            key=lambda p: _POSITION_ORDER[p.pos],
        )
        hits_value = round(hits.value())
        new_bank = round(total_budget - sum(pool_by_id[pid].price for pid in new_squad_ids), 2)

        combos.append(
            TradeCombo(
                players_out=players_out,
                players_in=players_in,
                hits=hits_value,
                hit_cost=hits_value * hit_cost,
                xp_gain=round(pulp.value(prob.objective) - old_total_xp, 2),
                new_bank=new_bank,
            )
        )
        excluded_solutions.append((frozenset(p.id for p in players_out), frozenset(p.id for p in players_in)))

    combos.sort(key=lambda c: c.xp_gain, reverse=True)
    return combos


def suggest_transfers(
    current_squad: list[CandidatePlayer],
    pool: list[CandidatePlayer],
    bank: float,
    free_transfers: int,
    club_cap: int = CLUB_CAP,
) -> list[TransferSuggestion]:
    """
    Greedy sequential transfer search: repeatedly take the best same-position swap and apply it,
    stopping once free transfers are used up and the next available gain no longer clears the -4
    hit cost, or no positive-gain swap remains. This is a heuristic, not a joint optimum over
    multiple weeks — reasonable for a weekly "what should I do" nudge. Each swap spends only its
    own outgoing player's price, one at a time — it never holds back on an early swap to bank
    extra budget for a later, bigger one. See suggest_transfer_package for the joint-optimum
    version that can do that.

    Candidates are still shortlisted by the cheap in.xp - out.xp comparison (checking every
    combination's real starting-XI impact would mean a full pick_starting_xi solve per candidate,
    for hundreds of candidates every iteration) — but the reported gain, and the decision of
    whether a swap is worth making at all, comes from each shortlisted candidate's actual effect
    on starting-XI-plus-captain xp (see optimize_squad's docstring for why bench xp doesn't
    count the same as a real gameweek score), not the raw player-vs-player number. A swap that
    only strengthens the bench correctly shows little or no real gain, even if its two players'
    raw xp gap looked big.
    """
    squad = list(current_squad)
    squad_ids = {p.id for p in squad}
    remaining_bank = bank
    suggestions: list[TransferSuggestion] = []

    # At least enough attempts to cover every free transfer, plus the usual headroom to also
    # surface a couple of hit-worthy extra moves beyond them.
    num_attempts = max(MAX_SUGGESTED_TRANSFERS, free_transfers)
    for i in range(num_attempts):
        team_counts: dict[str, int] = {}
        for p in squad:
            team_counts[p.team] = team_counts.get(p.team, 0) + 1

        candidates: list[TransferSuggestion] = []
        for out_p in squad:
            afford = remaining_bank + out_p.price
            same_team_count_without_out = team_counts.get(out_p.team, 0) - 1
            for in_p in pool:
                if in_p.id in squad_ids or in_p.pos != out_p.pos:
                    continue
                if in_p.price > afford:
                    continue
                new_team_count = same_team_count_without_out + (1 if in_p.team == out_p.team else 0)
                if in_p.team != out_p.team:
                    new_team_count = team_counts.get(in_p.team, 0) + 1
                if new_team_count > club_cap:
                    continue
                gain = in_p.xp - out_p.xp
                if gain > 0:
                    candidates.append(TransferSuggestion(player_out=out_p, player_in=in_p, xp_gain=gain, is_hit=False))

        if not candidates:
            break
        candidates.sort(key=lambda c: c.xp_gain, reverse=True)

        old_total = _starting_xi_total_with_captain(squad)

        best: TransferSuggestion | None = None
        true_gain = 0.0
        for cand in candidates[:TRANSFER_SHORTLIST_SIZE]:
            new_squad = [p for p in squad if p.id != cand.player_out.id] + [cand.player_in]
            new_total = _starting_xi_total_with_captain(new_squad)
            candidate_true_gain = new_total - old_total
            if candidate_true_gain > 0:
                best, true_gain = cand, candidate_true_gain
                break

        if best is None:
            break

        is_hit = i >= free_transfers
        if is_hit and true_gain <= TRANSFER_HIT_COST:
            break

        applied = TransferSuggestion(
            player_out=best.player_out, player_in=best.player_in, xp_gain=round(true_gain, 2), is_hit=is_hit
        )
        suggestions.append(applied)
        remaining_bank = remaining_bank + best.player_out.price - best.player_in.price
        squad = [p for p in squad if p.id != best.player_out.id] + [best.player_in]
        squad_ids = {p.id for p in squad}

    return suggestions
