"""
La Liga recommendations — deliberately lighter than fpl.py per the user's scope call: no
from-scratch squad optimizer, just "given my current team, what should I do this week."
Reuses `recommend.fpl.CandidatePlayer` (same shape: id/name/pos/team/price/xp) so the same
xP pipeline (models/player_points.py fed by models/predict.py) drives both leagues.
"""

from __future__ import annotations

from dataclasses import dataclass

from fantasy_app.recommend.fpl import CandidatePlayer

MAX_TRANSFER_FLAGS = 2


@dataclass(frozen=True)
class TransferFlag:
    player_out: CandidatePlayer
    player_in: CandidatePlayer
    xp_gain: float
    price_delta: float  # player_in.price - player_out.price; not budget-enforced, just informational


@dataclass(frozen=True)
class LaLigaRecommendation:
    captain: CandidatePlayer
    transfer_flags: list[TransferFlag]


def recommend_laliga(
    current_squad: list[CandidatePlayer],
    pool: list[CandidatePlayer],
    max_flags: int = MAX_TRANSFER_FLAGS,
) -> LaLigaRecommendation:
    if not current_squad:
        raise ValueError("current_squad is empty")

    captain = max(current_squad, key=lambda p: p.xp)

    squad_ids = {p.id for p in current_squad}
    candidate_flags: list[TransferFlag] = []
    for out_p in current_squad:
        best_in = None
        for in_p in pool:
            if in_p.id in squad_ids or in_p.pos != out_p.pos:
                continue
            if best_in is None or in_p.xp > best_in.xp:
                best_in = in_p
        if best_in is not None and best_in.xp > out_p.xp:
            candidate_flags.append(
                TransferFlag(
                    player_out=out_p,
                    player_in=best_in,
                    xp_gain=round(best_in.xp - out_p.xp, 3),
                    price_delta=round(best_in.price - out_p.price, 2),
                )
            )

    candidate_flags.sort(key=lambda f: f.xp_gain, reverse=True)
    return LaLigaRecommendation(captain=captain, transfer_flags=candidate_flags[:max_flags])
