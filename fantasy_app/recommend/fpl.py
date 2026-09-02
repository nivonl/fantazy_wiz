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


def optimize_squad(
    pool: list[CandidatePlayer],
    budget: float = BUDGET,
    club_cap: int = CLUB_CAP,
    must_include_ids: list[str] | None = None,
    min_from_team: dict[str, int] | None = None,
) -> SquadResult:
    """
    Build the best 15 from scratch: maximize total squad xp under budget/shape/club-cap, then
    pick the best valid starting XI out of those 15.

    must_include_ids: player ids that must be in the 15 regardless of xp (e.g. favorite
    players) — the optimizer still picks the other 15-minus-len(must_include_ids) freely.
    min_from_team: {team_name: minimum count in the 15} (e.g. "at least 3 from my favorite
    club") — capped at club_cap since a min above the max would make the problem infeasible.
    """
    must_include_ids = must_include_ids or []
    min_from_team = min_from_team or {}

    prob = pulp.LpProblem("squad_15", pulp.LpMaximize)
    x = {p.id: pulp.LpVariable(f"pick_{p.id}", cat="Binary") for p in pool}
    prob += pulp.lpSum(p.xp * x[p.id] for p in pool)
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

    prob.solve(pulp.PULP_CBC_CMD(msg=False))
    if pulp.LpStatus[prob.status] != "Optimal":
        raise RuntimeError(
            f"Could not build a valid 15-player squad under the given constraints "
            f"({pulp.LpStatus[prob.status]}) — try relaxing the favorite-team minimum or "
            f"favorite-player picks."
        )

    squad = [p for p in pool if x[p.id].value() == 1]
    starters, bench = pick_starting_xi(squad)
    ranked_starters = sorted(starters, key=lambda p: p.xp, reverse=True)
    captain, vice = ranked_starters[0], ranked_starters[1]

    return SquadResult(
        squad=squad,
        starters=starters,
        bench=bench,
        captain=captain,
        vice_captain=vice,
        total_price=round(sum(p.price for p in squad), 1),
        starting_xp=round(sum(p.xp for p in starters), 2),
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
    owning `wanted_player`, ranked by projected xp net of any transfer hits. One ILP per combo
    (the same maximize-xp-under-budget/shape/club-cap pattern as optimize_squad), using a
    standard "no-good cut" to force each re-solve toward a genuinely different combination of
    trades, rather than a bespoke search algorithm.

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

    old_total_xp = sum(pool_by_id[p.id].xp for p in current_squad)
    total_budget = round(bank + sum(pool_by_id[p.id].price for p in current_squad), 2)

    combos: list[TradeCombo] = []
    excluded_solutions: list[tuple[frozenset[str], frozenset[str]]] = []

    for attempt in range(top_k):
        prob = pulp.LpProblem("trade_combo", pulp.LpMaximize)
        x = {p.id: pulp.LpVariable(f"pick_{p.id}", cat="Binary") for p in pool}
        hits = pulp.LpVariable("hits", lowBound=0)

        prob += pulp.lpSum(p.xp * x[p.id] for p in pool) - hit_cost * hits
        prob += pulp.lpSum(p.price * x[p.id] for p in pool) <= total_budget

        for pos, count in SQUAD_SHAPE.items():
            prob += pulp.lpSum(x[p.id] for p in pool if p.pos == pos) == count

        for team in {p.team for p in pool}:
            prob += pulp.lpSum(x[p.id] for p in pool if p.team == team) <= club_cap

        prob += x[wanted_player.id] == 1

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


def suggest_transfers(
    current_squad: list[CandidatePlayer],
    pool: list[CandidatePlayer],
    bank: float,
    free_transfers: int,
    club_cap: int = CLUB_CAP,
) -> list[TransferSuggestion]:
    """
    Greedy sequential transfer search: repeatedly take the single best same-position swap
    (highest xp gain, affordable from bank + the outgoing player's price, respecting the club
    cap) and apply it, stopping once free transfers are used up and the next available gain
    no longer clears the -4 hit cost, or no positive-gain swap remains. This is a heuristic,
    not a joint optimum over multiple weeks — reasonable for a weekly "what should I do" nudge.
    """
    squad = list(current_squad)
    squad_ids = {p.id for p in squad}
    remaining_bank = bank
    suggestions: list[TransferSuggestion] = []

    for i in range(MAX_SUGGESTED_TRANSFERS):
        team_counts: dict[str, int] = {}
        for p in squad:
            team_counts[p.team] = team_counts.get(p.team, 0) + 1

        best: TransferSuggestion | None = None
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
                if best is None or gain > best.xp_gain:
                    best = TransferSuggestion(player_out=out_p, player_in=in_p, xp_gain=gain, is_hit=False)

        if best is None or best.xp_gain <= 0:
            break

        is_hit = i >= free_transfers
        if is_hit and best.xp_gain <= TRANSFER_HIT_COST:
            break

        applied = TransferSuggestion(
            player_out=best.player_out, player_in=best.player_in, xp_gain=best.xp_gain, is_hit=is_hit
        )
        suggestions.append(applied)
        remaining_bank = remaining_bank + best.player_out.price - best.player_in.price
        squad = [p for p in squad if p.id != best.player_out.id] + [best.player_in]
        squad_ids = {p.id for p in squad}

    return suggestions
