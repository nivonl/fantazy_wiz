"""
Multi-season FPL player history, sourced from the community-maintained
vaastav/Fantasy-Premier-League GitHub archive. FPL's own live API only exposes match-by-match
detail for the CURRENT season (`element-summary`'s `history`); past seasons come back as
aggregates only (`history_past`), with no per-match opponent breakdown — so "how has this
player done against this specific opponent over the last 5 seasons" simply isn't answerable
from the live API alone. The vaastav archive is the standard free source the FPL analytics
community uses for exactly this gap: per-gameweek, per-player rows going back years, verified
live (2021-22 through 2025-26 all present and correctly structured as of this writing).

Downloaded CSVs are cached to disk under .cache/fpl_history/ — completed seasons never change, so
once cached there's no reason to hit the network again. The season still in progress is the
exception: its file is re-downloaded every time rather than trusted from cache, since (unlike a
finished season) it keeps changing gameweek to gameweek and this archive is the only source this
codebase has for current-season per-gameweek rows old enough to have fallen out of FPL's own
element-summary "recent form" window.
"""

from __future__ import annotations

import csv
import io
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import httpx

REPO_BASE = "https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/master/data"
CACHE_DIR = Path(__file__).resolve().parent.parent.parent / ".cache" / "fpl_history"
SEASONS_BACK = 5  # how many seasons of archive to load, most recent (current, in-progress) first


def current_season_label(today: datetime | None = None) -> str:
    """Same Jul-rollover rule as services.common.current_season_start_year, duplicated locally
    (a 2-line pure date calc) rather than imported, so this lower-level provider module doesn't
    have to depend on the services layer above it."""
    today = today or datetime.now(timezone.utc)
    start = today.year if today.month >= 7 else today.year - 1
    return f"{start}-{str(start + 1)[2:]}"


def _seasons_list() -> list[str]:
    """The last SEASONS_BACK season labels ending with whatever season is current right now —
    computed fresh each call (cheap) instead of a hardcoded literal, so this never silently goes
    stale as real seasons roll over."""
    current = current_season_label()
    start_year = int(current.split("-")[0])
    return [f"{y}-{str(y + 1)[2:]}" for y in range(start_year - SEASONS_BACK + 1, start_year + 1)]


# Letters that DON'T have an NFKD decomposition (they're distinct letters, not a base+combining-
# mark pair) — NFKD + ascii-ignore silently DROPS them rather than transliterating, which would
# turn e.g. "Ødegaard" into "degaard" instead of "odegaard". Handle these explicitly first;
# everything NFKD-decomposable (é, ñ, á, ...) is already handled correctly by the ascii-ignore
# pass below.
_EXTRA_TRANSLATIONS = str.maketrans(
    {"Ø": "O", "ø": "o", "Æ": "AE", "æ": "ae", "Đ": "D", "đ": "d", "ß": "ss", "Ł": "L", "ł": "l"}
)


def normalize_person_name(name: str) -> str:
    """Lowercase + strip accents, so 'Ødegaard' and 'Martín' compare equal across sources
    regardless of minor encoding/rendering differences between FPL's live API and the archive."""
    translated = name.translate(_EXTRA_TRANSLATIONS)
    stripped = unicodedata.normalize("NFKD", translated).encode("ascii", "ignore").decode("ascii")
    return " ".join(stripped.lower().split())


@dataclass(frozen=True)
class HistoryRow:
    season: str
    player: str  # normalized full name
    team: str  # the club they were AT for this match (not normalized via team_matching — raw
    # FPL-style short name, e.g. "Man City" — callers compare via team_matching.names_match)
    opponent: str
    round: int
    total_points: int
    minutes: int
    goals_scored: int
    assists: int
    was_home: bool
    price: float  # £m, this gameweek's actual price (archive's "value" column, /10)
    # Everything below is Optional and None when the season's CSV lacks the column (the archive's
    # schema grew over the seasons -- e.g. xG/xA only from 2023-24, defensive_contribution only
    # from 2025-26) or the cell was blank. None (not 0) is load-bearing: aggregations that skip
    # None rows are how a stat's career average ends up covering only the seasons it actually
    # existed in, with no extra filtering logic needed anywhere.
    clean_sheets: int | None = None
    goals_conceded: int | None = None
    saves: int | None = None
    bonus: int | None = None
    bps: int | None = None
    yellow_cards: int | None = None
    red_cards: int | None = None
    influence: float | None = None
    creativity: float | None = None
    threat: float | None = None
    expected_goals: float | None = None
    expected_assists: float | None = None
    clearances_blocks_interceptions: int | None = None
    recoveries: int | None = None
    tackles: int | None = None
    defensive_contribution: int | None = None


def _cached_get(url: str, cache_path: Path, force_refresh: bool = False) -> str:
    if cache_path.exists() and not force_refresh:
        return cache_path.read_text(encoding="utf-8")
    r = httpx.get(url, timeout=30, follow_redirects=True)
    r.raise_for_status()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(r.text, encoding="utf-8")
    return r.text


def _load_team_names(season: str, force_refresh: bool) -> dict[str, str]:
    text = _cached_get(f"{REPO_BASE}/{season}/teams.csv", CACHE_DIR / season / "teams.csv", force_refresh)
    reader = csv.DictReader(io.StringIO(text))
    return {row["id"]: row["name"] for row in reader}


def _opt_int(r: dict, key: str) -> int | None:
    v = r.get(key)
    if v is None or v == "":
        return None
    try:
        return int(v)
    except ValueError:
        return None


def _opt_float(r: dict, key: str) -> float | None:
    v = r.get(key)
    if v is None or v == "":
        return None
    try:
        return float(v)
    except ValueError:
        return None


def _load_season_rows(season: str) -> list[HistoryRow]:
    force_refresh = season == current_season_label()
    team_by_id = _load_team_names(season, force_refresh)
    text = _cached_get(f"{REPO_BASE}/{season}/gws/merged_gw.csv", CACHE_DIR / season / "merged_gw.csv", force_refresh)
    reader = csv.DictReader(io.StringIO(text))
    rows: list[HistoryRow] = []
    for r in reader:
        try:
            minutes = int(r["minutes"] or 0)
            if minutes <= 0:
                continue  # didn't play — no opponent-relevant signal
            opponent_name = team_by_id.get(r["opponent_team"], "")
            if not opponent_name:
                continue
            rows.append(
                HistoryRow(
                    season=season,
                    player=normalize_person_name(r["name"]),
                    team=r["team"],
                    opponent=opponent_name,
                    round=int(r["round"] or 0),
                    total_points=int(r["total_points"] or 0),
                    minutes=minutes,
                    goals_scored=int(r["goals_scored"] or 0),
                    assists=int(r["assists"] or 0),
                    was_home=(r["was_home"] or "").strip().lower() == "true",
                    price=int(r["value"] or 0) / 10.0,
                    clean_sheets=_opt_int(r, "clean_sheets"),
                    goals_conceded=_opt_int(r, "goals_conceded"),
                    saves=_opt_int(r, "saves"),
                    bonus=_opt_int(r, "bonus"),
                    bps=_opt_int(r, "bps"),
                    yellow_cards=_opt_int(r, "yellow_cards"),
                    red_cards=_opt_int(r, "red_cards"),
                    influence=_opt_float(r, "influence"),
                    creativity=_opt_float(r, "creativity"),
                    threat=_opt_float(r, "threat"),
                    expected_goals=_opt_float(r, "expected_goals"),
                    expected_assists=_opt_float(r, "expected_assists"),
                    clearances_blocks_interceptions=_opt_int(r, "clearances_blocks_interceptions"),
                    recoveries=_opt_int(r, "recoveries"),
                    tackles=_opt_int(r, "tackles"),
                    defensive_contribution=_opt_int(r, "defensive_contribution"),
                )
            )
        except (KeyError, ValueError):
            continue
    return rows


_rows_cache: list[HistoryRow] | None = None
_index_cache: dict[str, list[HistoryRow]] | None = None


def load_all_history() -> list[HistoryRow]:
    """
    Best-effort: a GitHub hiccup on one season (or all of them) degrades to less data, not a
    crash — this is an enrichment layer (opponent-history stats + a shrinkage nudge to xP), and
    the rest of the app (ratings, predictions, squad building) works fine without it, just less
    informed. Callers see an empty/partial index and everything downstream treats "no history"
    as a neutral prior rather than an error.
    """
    global _rows_cache
    if _rows_cache is None:
        rows: list[HistoryRow] = []
        for season in _seasons_list():
            try:
                rows.extend(_load_season_rows(season))
            except (httpx.HTTPError, OSError):
                continue
        _rows_cache = rows
    return _rows_cache


def index_by_player() -> dict[str, list[HistoryRow]]:
    """Cached in-process for the life of the server — rebuilding a ~40k-row index on every
    request would add needless latency to every single prediction/recommendation call."""
    global _index_cache
    if _index_cache is None:
        index: dict[str, list[HistoryRow]] = {}
        for row in load_all_history():
            index.setdefault(row.player, []).append(row)
        _index_cache = index
    return _index_cache
