"""
Shared expected-points (xP) engine — the official FPL classic scoring table, applied to
BOTH leagues (the user confirmed 9cat.co.il's La Liga classic fantasy scores the same way).
One scoring module, two data providers feeding it.

Combines fixture-level probabilities from predict.py (a team's expected goals, an opponent's
expected goals, clean-sheet probability) with player-level rates. Those rates should come
from real per-90 history (FPL's element-summary, or 9cat data once the provider is live)
whenever it exists — mirrors `prev_project/fantasy/model.md`'s rule that a player's actual
observed output always overrides an analyst estimate. goal_share/assist_share here are
"expected goals/assists this player registers in this specific fixture", already scaled to
the fixture (i.e. goal_share=0.30 means this player is expected to score 30% of NEW team
goals in the match, not a per-90 rate) so callers multiply by lam_team upstream of position
scoring, not by 90 minutes.
"""

from __future__ import annotations

from dataclasses import dataclass

# Points per position: GK, DEF, MID, FWD (official FPL classic scoring)
GOAL_PTS = {"GK": 6, "DEF": 6, "MID": 5, "FWD": 4}
ASSIST_PTS = {"GK": 3, "DEF": 3, "MID": 3, "FWD": 3}
CLEAN_SHEET_PTS = {"GK": 4, "DEF": 4, "MID": 1, "FWD": 0}
CONCEDE_PENALTY_POSITIONS = {"GK", "DEF"}  # -1 per 2 goals conceded while on the pitch

APPEARANCE_60 = 2.0
YELLOW_PTS = -1.0
SAVE_PTS_PER_3 = 1.0 / 3.0


@dataclass(frozen=True)
class PlayerXP:
    name: str
    pos: str
    price: float
    xp: float
    xp_per_price: float | None
    is_captain: bool
    breakdown: dict[str, float]


def player_xp(
    *,
    name: str,
    pos: str,  # "GK" | "DEF" | "MID" | "FWD"
    price: float,
    lam_team: float,  # this player's team's expected goals in the fixture (from predict.py)
    lam_opponent: float,  # the opponent's expected goals (drives the conceded penalty)
    p_cs: float,  # this team's clean-sheet probability in the fixture
    goal_share: float = 0.0,  # fraction of lam_team this player is expected to score
    assist_share: float = 0.0,  # expected assists this player registers in the fixture
    defensive_contribution: float = 0.0,  # analyst/BPS-style flat estimate (CBIT threshold points)
    save_rate: float = 0.0,  # GK only: expected saves in the fixture
    start_prob: float = 1.0,  # P(starts and plays 60+)
    yellow_prob: float = 0.15,
    is_captain: bool = False,
) -> PlayerXP:
    goal_xp = lam_team * goal_share * GOAL_PTS[pos]
    assist_xp = assist_share * ASSIST_PTS[pos]
    cs_xp = p_cs * CLEAN_SHEET_PTS[pos]
    conceded_xp = -(lam_opponent / 2.0) if pos in CONCEDE_PENALTY_POSITIONS else 0.0
    save_xp = save_rate * SAVE_PTS_PER_3 if pos == "GK" else 0.0
    card_xp = yellow_prob * YELLOW_PTS

    on_pitch = (
        APPEARANCE_60
        + goal_xp
        + assist_xp
        + cs_xp
        + conceded_xp
        + save_xp
        + defensive_contribution
        + card_xp
    )
    xp = start_prob * on_pitch
    if is_captain:
        xp *= 2

    return PlayerXP(
        name=name,
        pos=pos,
        price=price,
        xp=round(xp, 3),
        xp_per_price=round(xp / price, 4) if price else None,
        is_captain=is_captain,
        breakdown={
            "appearance": round(start_prob * APPEARANCE_60, 3),
            "goals": round(start_prob * goal_xp, 3),
            "assists": round(start_prob * assist_xp, 3),
            "clean_sheet": round(start_prob * cs_xp, 3),
            "conceded": round(start_prob * conceded_xp, 3),
            "saves": round(start_prob * save_xp, 3),
            "defensive_contribution": round(start_prob * defensive_contribution, 3),
            "cards": round(start_prob * card_xp, 3),
            "start_prob": start_prob,
        },
    )


def rank(candidates: list[PlayerXP]) -> list[PlayerXP]:
    return sorted(candidates, key=lambda p: p.xp, reverse=True)
