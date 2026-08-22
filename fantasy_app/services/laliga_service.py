"""
Wires football-data.org (match results, for the ratings fit) and a manually-maintained squad
(providers/cat9.py, until the real 9cat.co.il API is captured — see NOTES-9cat.md) into the
same prediction/recommendation engine FPL uses. Deliberately lighter than fpl_service.py: no
full player-pool xP build, since there's no live source for La Liga player prices/rates yet.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from fantasy_app.models.player_points import player_xp
from fantasy_app.models.predict import FixturePrediction, predict_fixture
from fantasy_app.models.strength import MatchResult, Ratings, fit_ratings, team_goal_averages
from fantasy_app.providers.cat9 import ManualSquad, ManualSquadPlayer
from fantasy_app.providers.football_data import LA_LIGA_CODE, FootballDataClient
from fantasy_app.recommend.fpl import CandidatePlayer
from fantasy_app.services.common import current_season_start_year
from fantasy_app.services.team_matching import find_best_match

MIN_MATCHES_FOR_FIT = 50


def _parse_kickoff(iso: str | None) -> datetime:
    if not iso:
        return datetime.now(timezone.utc)
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


def _to_match_results(matches: list[dict]) -> list[MatchResult]:
    out = []
    for m in matches:
        score = m.get("score", {}).get("fullTime", {})
        if score.get("home") is None or score.get("away") is None:
            continue
        out.append(
            MatchResult(
                home_team_id=str(m["homeTeam"]["id"]),
                away_team_id=str(m["awayTeam"]["id"]),
                home_goals=score["home"],
                away_goals=score["away"],
                played_at=_parse_kickoff(m.get("utcDate")),
            )
        )
    return out


def fit_laliga_ratings(client: FootballDataClient) -> tuple[Ratings, dict[str, float]]:
    current_year = current_season_start_year()
    matches = client.matches(LA_LIGA_CODE, season=current_year, status="FINISHED")
    if len(matches) < MIN_MATCHES_FOR_FIT:
        # Early in the season: blend in last season's results. Time-decay in fit_ratings
        # naturally down-weights these rather than needing separate handling.
        matches += client.matches(LA_LIGA_CODE, season=current_year - 1, status="FINISHED")

    results = _to_match_results(matches)
    if not results:
        raise RuntimeError("No finished La Liga matches found to fit ratings from.")

    ratings = fit_ratings(results)
    goal_avgs = team_goal_averages(results)
    return ratings, goal_avgs


@dataclass(frozen=True)
class NamedFixturePrediction:
    home_team: str
    away_team: str
    prediction: FixturePrediction


def predict_matchday(client: FootballDataClient, matchday: int | None = None) -> list[NamedFixturePrediction]:
    ratings, _ = fit_laliga_ratings(client)
    params: dict = {"status": "SCHEDULED"}
    upcoming = client.matches(LA_LIGA_CODE, status="SCHEDULED")
    if matchday is not None:
        upcoming = [m for m in upcoming if m.get("matchday") == matchday]
    else:
        # default to the nearest upcoming matchday
        matchdays = sorted({m["matchday"] for m in upcoming if m.get("matchday") is not None})
        if matchdays:
            upcoming = [m for m in upcoming if m.get("matchday") == matchdays[0]]

    out = []
    for m in upcoming:
        home_id, away_id = str(m["homeTeam"]["id"]), str(m["awayTeam"]["id"])
        if home_id not in ratings.attack or away_id not in ratings.attack:
            continue  # promoted/relegated team with no fitted history yet
        pred = predict_fixture(ratings, home_id, away_id)
        out.append(
            NamedFixturePrediction(
                home_team=m["homeTeam"]["name"], away_team=m["awayTeam"]["name"], prediction=pred
            )
        )
    return out


def _find_team_id(team_name: str, teams: list[dict]) -> str | None:
    by_name = {t.get("name", ""): t for t in teams}
    candidates = [n for n in by_name if n]
    match = find_best_match(team_name, candidates)
    if match is not None:
        return str(by_name[match]["id"])
    # fall back to shortName/tla, which find_best_match doesn't see above
    needle = team_name.strip().lower()
    for t in teams:
        for c in (t.get("shortName", ""), t.get("tla", "")):
            if c and c.strip().lower() == needle:
                return str(t["id"])
    return None


def _squad_player_to_candidate(
    p: ManualSquadPlayer,
    team_id: str | None,
    ratings: Ratings,
    goal_avgs: dict[str, float],
    fixture_by_team: dict[str, dict],
) -> CandidatePlayer:
    xp_value = 0.0
    if team_id is not None and team_id in fixture_by_team:
        f = fixture_by_team[team_id]
        is_home = f["home_team_id"] == team_id
        pred = predict_fixture(ratings, f["home_team_id"], f["away_team_id"])
        lam_team = pred.lam_home if is_home else pred.lam_away
        lam_opponent = pred.lam_away if is_home else pred.lam_home
        p_cs = pred.p_home_clean_sheet if is_home else pred.p_away_clean_sheet

        goal_share = p.goal_share
        if goal_share is None:
            goal_share = 0.0  # unknown — no fabricated estimate, team-level-only xP
        assist_share = p.assist_share or 0.0
        start_prob = p.start_prob if p.start_prob is not None else 1.0

        xp_value = player_xp(
            name=p.name,
            pos=p.position,
            price=p.price,
            lam_team=lam_team,
            lam_opponent=lam_opponent,
            p_cs=p_cs,
            goal_share=goal_share,
            assist_share=assist_share,
            start_prob=start_prob,
        ).xp

    return CandidatePlayer(
        id=p.name,  # no stable external id for manually-entered players; name is the key
        name=p.name,
        pos=p.position,
        team=p.team,
        price=p.price,
        xp=xp_value,
    )


def build_squad_and_watchlist_pool(
    client: FootballDataClient, squad: ManualSquad
) -> tuple[list[CandidatePlayer], list[CandidatePlayer]]:
    """Returns (current_squad_candidates, full_pool_including_watchlist)."""
    ratings, goal_avgs = fit_laliga_ratings(client)
    teams = client.teams(LA_LIGA_CODE)
    upcoming = client.matches(LA_LIGA_CODE, status="SCHEDULED")
    matchdays = sorted({m["matchday"] for m in upcoming if m.get("matchday") is not None})
    next_matchday_fixtures = [m for m in upcoming if m.get("matchday") == matchdays[0]] if matchdays else []

    fixture_by_team: dict[str, dict] = {}
    for m in next_matchday_fixtures:
        home_id, away_id = str(m["homeTeam"]["id"]), str(m["awayTeam"]["id"])
        entry = {"home_team_id": home_id, "away_team_id": away_id}
        fixture_by_team[home_id] = entry
        fixture_by_team[away_id] = entry

    def to_candidates(players: list[ManualSquadPlayer]) -> list[CandidatePlayer]:
        result = []
        for p in players:
            team_id = _find_team_id(p.team, teams)
            result.append(_squad_player_to_candidate(p, team_id, ratings, goal_avgs, fixture_by_team))
        return result

    squad_candidates = to_candidates(squad.players)
    pool_candidates = squad_candidates + to_candidates(squad.watchlist)
    return squad_candidates, pool_candidates
