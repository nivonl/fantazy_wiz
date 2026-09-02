"""
Multi-season FPL player history, sourced from the community-maintained
vaastav/Fantasy-Premier-League GitHub archive. FPL's own live API only exposes match-by-match
detail for the CURRENT season (`element-summary`'s `history`); past seasons come back as
aggregates only (`history_past`), with no per-match opponent breakdown — so "how has this
player done against this specific opponent over the last 5 seasons" simply isn't answerable
from the live API alone. The vaastav archive is the standard free source the FPL analytics
community uses for exactly this gap: per-gameweek, per-player rows going back years, verified
live (2021-22 through 2025-26 all present and correctly structured as of this writing).

Downloaded CSVs are cached to disk under .cache/fpl_history/ — completed seasons never change,
so once cached there's no reason to hit the network again.
"""

from __future__ import annotations

import csv
import io
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import httpx

REPO_BASE = "https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/master/data"
SEASONS = ["2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]  # last 5 completed PL seasons
CACHE_DIR = Path(__file__).resolve().parent.parent.parent / ".cache" / "fpl_history"


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


def _cached_get(url: str, cache_path: Path) -> str:
    if cache_path.exists():
        return cache_path.read_text(encoding="utf-8")
    r = httpx.get(url, timeout=30, follow_redirects=True)
    r.raise_for_status()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(r.text, encoding="utf-8")
    return r.text


def _load_team_names(season: str) -> dict[str, str]:
    text = _cached_get(f"{REPO_BASE}/{season}/teams.csv", CACHE_DIR / season / "teams.csv")
    reader = csv.DictReader(io.StringIO(text))
    return {row["id"]: row["name"] for row in reader}


def _load_season_rows(season: str) -> list[HistoryRow]:
    team_by_id = _load_team_names(season)
    text = _cached_get(f"{REPO_BASE}/{season}/gws/merged_gw.csv", CACHE_DIR / season / "merged_gw.csv")
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
        for season in SEASONS:
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
