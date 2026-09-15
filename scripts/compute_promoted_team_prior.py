"""
Derives PROMOTED_TEAM_ATTACK_PRIOR / PROMOTED_TEAM_DEFENSE_PRIOR (fantasy_app/services/
fpl_service.py) from real history: for each of the last few completed PL seasons, find the
clubs that were newly promoted into it (present in that season's football-data.org results but
absent from the season before), fit a full-season rating for that season, and average the
promoted clubs' attack/defense across all of them.

Rationale: a newly-promoted club with no historical PL data gets extra L2 shrinkage
(NO_HISTORY_L2_BOOST) so a thin, possibly-lucky current-season sample can't swing its rating to
an extreme (see NOTES-model-improvements.md's Gameweek 4 / Hull City section) -- but shrinking
toward 0 (a league-average team) ignores that promoted clubs are systematically NOT average: they
were in the Championship for a reason. Shrinking toward the historical average of other promoted
clubs' own debut seasons is a strictly better-informed prior for the same job.

Usage (from repo root, FOOTBALL_DATA_TOKEN required):

    python scripts/compute_promoted_team_prior.py

Re-run this whenever another season completes and rewrite the two constants in fpl_service.py by
hand -- deliberately not computed at request time (this needs an extra season fetch beyond what
fit_pl_ratings normally does, purely to find last season's team list as the promotion baseline,
and the result should barely move season to season, so there's no reason to pay that API/compute
cost on every request).
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from fantasy_app.models.strength import MatchResult, fit_ratings
from fantasy_app.services.fpl_service import _try_football_data_client
from fantasy_app.services.team_matching import normalize_team_name
from fantasy_app.services.xp_backtest import require_football_data_token

# How many finished seasons back to look for promoted-club examples, and the earliest season to
# use as a promotion baseline. football-data.org's free tier only exposes the last few seasons
# (older seasons 403) -- 2023 is the oldest that currently works, giving two full promotion
# cycles (into 2024-25 and into 2025-26) to average over, six clubs total.
CANDIDATE_SEASONS = [2024, 2025]
BASELINE_SEASON = 2023


def season_team_set(fd, year: int) -> set[str]:
    matches = fd.matches("PL", season=year, status="FINISHED")
    teams: set[str] = set()
    for m in matches:
        teams.add(normalize_team_name(m["homeTeam"]["name"]))
        teams.add(normalize_team_name(m["awayTeam"]["name"]))
    return teams


def season_match_results(fd, year: int) -> list[MatchResult]:
    raw = fd.matches("PL", season=year, status="FINISHED")
    out = []
    for m in raw:
        score = m.get("score", {}).get("fullTime", {})
        if score.get("home") is None or score.get("away") is None:
            continue
        out.append(
            MatchResult(
                home_team_id=normalize_team_name(m["homeTeam"]["name"]),
                away_team_id=normalize_team_name(m["awayTeam"]["name"]),
                home_goals=score["home"],
                away_goals=score["away"],
                played_at=datetime.fromisoformat(m["utcDate"].replace("Z", "+00:00")),
            )
        )
    return out


def main() -> int:
    fd = require_football_data_token(_try_football_data_client)

    prior_season_teams = season_team_set(fd, BASELINE_SEASON)
    all_attack: list[float] = []
    all_defense: list[float] = []

    for year in CANDIDATE_SEASONS:
        this_season_teams = season_team_set(fd, year)
        promoted = sorted(this_season_teams - prior_season_teams)
        matches = season_match_results(fd, year)
        # Full season, evenly weighted (no early-season/recency taper) -- this is meant to be
        # "how did a promoted club actually do over its whole debut season", not a live rating.
        ratings = fit_ratings(matches, decay_half_life_days=1_000_000)
        print(f"season {year}: promoted = {promoted}")
        for team in promoted:
            a, d = ratings.attack.get(team), ratings.defense.get(team)
            if a is None:
                print(f"  ! {team} not found in season {year} results, skipping")
                continue
            print(f"  {team:20s} attack={a:+.3f} defense={d:+.3f}")
            all_attack.append(a)
            all_defense.append(d)
        prior_season_teams = this_season_teams

    if not all_attack:
        print("No promoted-club examples found -- nothing to average.")
        return 1

    prior_attack = sum(all_attack) / len(all_attack)
    prior_defense = sum(all_defense) / len(all_defense)
    print(f"\nn={len(all_attack)} promoted-club debut seasons")
    print(f"PROMOTED_TEAM_ATTACK_PRIOR = {prior_attack:.3f}")
    print(f"PROMOTED_TEAM_DEFENSE_PRIOR = {prior_defense:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
