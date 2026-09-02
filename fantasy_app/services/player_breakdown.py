"""
Per-player gameweek-by-gameweek points breakdown, for the "click a player's name" popup.

Always fetched live from FPL's element-summary endpoint (no caching anywhere in this module,
unlike the ratings/candidate-pool pipeline elsewhere), so it reflects whatever the most
recently confirmed gameweek result is the moment it's confirmed.

Falls back to the historical archive (providers/fpl_history.py) for PREVIOUS-season
gameweeks, but only to fill in what this season doesn't have enough of yet (a new signing, or
gameweek 1-2 of the season). That fallback carries a smaller field set — goals/assists/minutes/
price/total only, all that source's CSV schema records — so each row is tagged with its own
season and only the fields that source actually has are ever populated, never guessed at.
"""

from __future__ import annotations

from dataclasses import dataclass

from fantasy_app.providers import fpl_history
from fantasy_app.providers.fpl import FPLClient
from fantasy_app.services.common import current_season_start_year

RECENT_GAMEWEEKS = 3


@dataclass(frozen=True)
class GameweekPoints:
    season: str
    gameweek: int
    total_points: int
    minutes: int
    price: float | None = None  # £m at this gameweek
    opponent: str | None = None
    was_home: bool | None = None
    goals_scored: int | None = None
    assists: int | None = None
    clean_sheets: int | None = None
    goals_conceded: int | None = None
    own_goals: int | None = None
    penalties_saved: int | None = None
    penalties_missed: int | None = None
    yellow_cards: int | None = None
    red_cards: int | None = None
    saves: int | None = None
    bonus: int | None = None


@dataclass(frozen=True)
class PlayerBreakdown:
    recent: list[GameweekPoints]  # chronological order, oldest to most recent
    note: str | None  # explains a previous-season fallback, when one happened


@dataclass(frozen=True)
class PricePoint:
    season: str
    gameweek: int
    price: float


def current_season_label(today=None) -> str:
    start = current_season_start_year(today)
    return f"{start}-{str(start + 1)[2:]}"


def build_player_breakdown(client: FPLClient, element_id: int, n: int = RECENT_GAMEWEEKS) -> PlayerBreakdown:
    bootstrap = client.bootstrap()
    team_name_by_id = {t["id"]: t["name"] for t in bootstrap["teams"]}
    element = next((e for e in bootstrap["elements"] if e["id"] == element_id), None)
    if element is None:
        raise RuntimeError(f"No FPL player with id {element_id}.")

    season = current_season_label()
    summary = client.element_summary(element_id)
    this_season = sorted(
        (
            GameweekPoints(
                season=season,
                gameweek=h["round"],
                total_points=h["total_points"],
                minutes=h["minutes"],
                price=(h["value"] / 10.0) if h.get("value") is not None else None,
                opponent=team_name_by_id.get(h.get("opponent_team")),
                was_home=h.get("was_home"),
                goals_scored=h.get("goals_scored"),
                assists=h.get("assists"),
                clean_sheets=h.get("clean_sheets"),
                goals_conceded=h.get("goals_conceded"),
                own_goals=h.get("own_goals"),
                penalties_saved=h.get("penalties_saved"),
                penalties_missed=h.get("penalties_missed"),
                yellow_cards=h.get("yellow_cards"),
                red_cards=h.get("red_cards"),
                saves=h.get("saves"),
                bonus=h.get("bonus"),
            )
            for h in summary.get("history", [])
        ),
        key=lambda r: r.gameweek,
    )
    recent = this_season[-n:]
    played_this_season = len(recent)

    note = None
    missing = n - played_this_season
    if missing > 0:
        full_name = fpl_history.normalize_person_name(f"{element['first_name']} {element['second_name']}")
        past_rows = [r for r in fpl_history.index_by_player().get(full_name, []) if r.season != season]
        past_rows.sort(key=lambda r: (r.season, r.round), reverse=True)
        fallback_rows = past_rows[:missing]
        if fallback_rows:
            fallback = [
                GameweekPoints(
                    season=r.season,
                    gameweek=r.round,
                    total_points=r.total_points,
                    minutes=r.minutes,
                    price=r.price,
                    opponent=r.opponent,
                    was_home=r.was_home,
                    goals_scored=r.goals_scored,
                    assists=r.assists,
                )
                for r in reversed(fallback_rows)  # chronological within the fallback subset
            ]
            recent = fallback + recent
            fallback_seasons = sorted({r.season for r in fallback}, reverse=True)
            note = (
                f"Only {played_this_season} gameweek(s) played this season ({season}) — "
                f"showing {len(fallback)} more from {', '.join(fallback_seasons)}."
            )

    return PlayerBreakdown(recent=recent, note=note)


def build_price_history(client: FPLClient, element_id: int) -> list[PricePoint]:
    """
    Every gameweek's real price this season, plus every gameweek of the immediately preceding
    season if the player has history there -- a genuine price-over-time view, deliberately
    separate from build_player_breakdown's short "recent form" window (RECENT_GAMEWEEKS), since
    price moves meaningfully over a full season, not just the last few gameweeks. Capped at one
    prior season rather than the full multi-year archive -- more than that is mostly flat noise
    for a single page section.
    """
    bootstrap = client.bootstrap()
    element = next((e for e in bootstrap["elements"] if e["id"] == element_id), None)
    if element is None:
        raise RuntimeError(f"No FPL player with id {element_id}.")

    season = current_season_label()
    summary = client.element_summary(element_id)
    this_season = sorted(
        (
            PricePoint(season=season, gameweek=h["round"], price=h["value"] / 10.0)
            for h in summary.get("history", [])
            if h.get("value") is not None
        ),
        key=lambda p: p.gameweek,
    )

    full_name = fpl_history.normalize_person_name(f"{element['first_name']} {element['second_name']}")
    past_rows = [r for r in fpl_history.index_by_player().get(full_name, []) if r.season != season]
    prev_season_points: list[PricePoint] = []
    if past_rows:
        most_recent_past_season = max(r.season for r in past_rows)
        prev_season_points = sorted(
            (PricePoint(season=r.season, gameweek=r.round, price=r.price) for r in past_rows if r.season == most_recent_past_season),
            key=lambda p: p.gameweek,
        )

    return prev_season_points + this_season
