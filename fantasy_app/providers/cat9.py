"""
9cat.co.il (La Liga classic fantasy) client.

No documented API. During planning, hitting the SPA's classic-fantasy route while logged out
redirected straight back to the homepage — the real endpoints only surface once authenticated.
Capturing them (same technique `prev_project/fantasy/continuation-protocol.md` used for
fantasy.one.co.il) requires the user to log in once in a browser we control so we can read the
network calls; see NOTES-9cat.md for the exact steps.

Until that capture happens, `load_manual_squad()` is the supported path: the user maintains
their current La Liga squad as a small JSON file and the rest of the pipeline (predict +
recommend) doesn't care where the squad came from.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel


class ManualSquadPlayer(BaseModel):
    name: str
    position: str  # GK | DEF | MID | FWD
    team: str  # real-world club name, must match a team name pulled via football_data.py
    price: float
    is_starter: bool = True
    is_captain: bool = False

    # Optional analyst inputs (goal-share/assist-share/start_prob), same spirit as
    # `prev_project/fantasy/players.md`: leave these null unless you've actually researched
    # the player this gameweek. Null means player_points.py falls back to a team-level-only
    # estimate (appearance + clean-sheet/conceded for GK/DEF) rather than inventing a number —
    # `model.md`'s rule was "fabricating inputs and presenting model output as analysis is
    # worse than just reading the actual numbers," and the same logic applies here.
    goal_share: float | None = None
    assist_share: float | None = None
    start_prob: float | None = None


class ManualSquad(BaseModel):
    bank: float = 0.0
    free_transfers: int = 1
    players: list[ManualSquadPlayer]
    # Players you're considering bringing in — the only pool `recommend_laliga` can suggest
    # transfers from, since there's no live full-player-pool source for this platform yet.
    watchlist: list[ManualSquadPlayer] = []


def load_manual_squad(path: str | Path) -> ManualSquad:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return ManualSquad.model_validate(data)


SAMPLE_SQUAD_JSON = """
{
  "bank": 0.5,
  "free_transfers": 1,
  "players": [
    {"name": "Example GK", "position": "GK", "team": "Real Madrid", "price": 5.0, "is_starter": true},
    {"name": "Example DEF", "position": "DEF", "team": "Barcelona", "price": 6.5, "is_starter": true}
  ]
}
"""


class Cat9Client:
    """Placeholder for the authenticated API once captured. Raises until then."""

    def __init__(self, *_, **__):
        raise NotImplementedError(
            "9cat.co.il's authenticated endpoints haven't been captured yet. "
            "See NOTES-9cat.md, or use providers.cat9.load_manual_squad() in the meantime."
        )
