"""
Fixture-congestion rotation risk: a Premier League team that played in Europe a few days
before this gameweek's PL fixture is measurably more likely to rotate — the well-known "rest
players for the weekend after a midweek Champions League game" pattern. Nothing in the existing
model captures this; `_player_rates`'s start_prob caps (squad-depth pricing, backup-GK, unproven
this season) are all about WHICH player is likely to start, not about a whole squad being more
rotated than usual around a specific fixture.

Data source: football-data.org's UEFA Champions League competition ("CL") — the only UEFA club
competition available on the free tier this project already has a token for (checked live:
Europa League and Conference League both 404 on this plan). So this only catches rotation risk
for the handful of PL clubs in the Champions League in a given season; Europa/Conference League
clubs get no adjustment, which understates their rotation risk. Worth upgrading if a data
source with broader UEFA coverage becomes available.

The discount thresholds below are a reasonable, documented PRIOR (same honesty as this file's
squad-depth constants) — not fit to historical minutes data. A real historical-minutes-vs-
rest-days study would be the natural follow-up to replace these with fitted numbers.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from fantasy_app.providers.football_data import FootballDataClient
from fantasy_app.services.common import current_season_start_year
from fantasy_app.services.team_matching import normalize_team_name

UEFA_COMPETITION_CODES = ("CL",)  # only one available on the free tier — see module docstring

# Rest-days-before-this-PL-kickoff -> start_prob multiplier. A team playing in Europe on
# Tuesday/Wednesday then PL at the weekend (4-5 days) is the normal rhythm most European-
# competition teams operate under all season and isn't treated as elevated risk; a quicker
# turnaround (an early-kickoff PL fixture, or a rearranged midweek PL game) is where real extra
# rotation shows up.
REST_DAYS_HIGH_RISK = 3.0  # fewer days than this before kickoff -> STRONG_DISCOUNT
REST_DAYS_MODERATE_RISK = 5.0  # fewer days than this -> MODERATE_DISCOUNT; at/above -> no discount
STRONG_DISCOUNT = 0.75
MODERATE_DISCOUNT = 0.90

# How far back to look for a UEFA match at all — no point fetching a whole season's fixtures
# when only the last week or so could possibly matter for "rest days before this weekend."
LOOKBACK_DAYS = 7


def _rest_day_discount(rest_days: float) -> float:
    if rest_days < 0:
        return 1.0  # the UEFA match is AFTER this PL kickoff — irrelevant to this fixture
    if rest_days < REST_DAYS_HIGH_RISK:
        return STRONG_DISCOUNT
    if rest_days < REST_DAYS_MODERATE_RISK:
        return MODERATE_DISCOUNT
    return 1.0


def compute_uefa_rotation_factors(
    fd_client: FootballDataClient | None,
    pl_fixture_by_team: dict[int, dict],
    norm_name_by_fpl_id: dict[int, str],
    pl_kickoff_by_team: dict[int, datetime],
) -> dict[int, float]:
    """Returns {fpl_team_id: start_prob multiplier} for PL teams whose most recent (or imminent)
    Champions League fixture falls within `LOOKBACK_DAYS` of their next PL kickoff. Teams with no
    such fixture simply aren't in the returned dict — callers should treat a missing key as 1.0
    (no adjustment), same convention as the other optional-enrichment factors in this codebase
    (e.g. opponent_history.shrinkage_factor). Silently returns {} if no football-data.org token
    is configured or the request fails — this is an optional enrichment, not a hard dependency."""
    if fd_client is None or not pl_fixture_by_team:
        return {}

    earliest_kickoff = min(pl_kickoff_by_team.values())
    latest_kickoff = max(pl_kickoff_by_team.values())
    window_start = earliest_kickoff - timedelta(days=LOOKBACK_DAYS)

    uefa_matches = []
    for code in UEFA_COMPETITION_CODES:
        try:
            uefa_matches += fd_client.matches(code, season=current_season_start_year())
        except Exception:
            continue  # e.g. this plan can't reach the competition, or a transient API error

    team_id_by_norm_name = {name: team_id for team_id, name in norm_name_by_fpl_id.items()}

    factors: dict[int, float] = {}
    for m in uefa_matches:
        played_at = _parse_match_date(m.get("utcDate"))
        if played_at is None or not (window_start <= played_at <= latest_kickoff):
            continue
        for side in ("homeTeam", "awayTeam"):
            team_name = normalize_team_name(m.get(side, {}).get("name", ""))
            team_id = team_id_by_norm_name.get(team_name)
            if team_id is None:
                continue  # a non-PL club in this fixture — not one of ours
            pl_kickoff = pl_kickoff_by_team.get(team_id)
            if pl_kickoff is None:
                continue
            rest_days = (pl_kickoff - played_at).total_seconds() / 86400
            discount = _rest_day_discount(rest_days)
            factors[team_id] = min(factors.get(team_id, 1.0), discount)
    return factors


def _parse_match_date(iso: str | None) -> datetime | None:
    if not iso:
        return None
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))
