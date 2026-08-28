"""
Derived views for the Overview dashboard: a fixture-difficulty ticker and a player's recent
scoring sparkline, plus the assembled overview response. Built on top of fpl_service's core
engine (ratings, candidate pool) rather than duplicating it.
"""

from __future__ import annotations

from dataclasses import dataclass

from fantasy_app.models.predict import predict_fixture
from fantasy_app.providers.football_data import FootballDataClient
from fantasy_app.providers.fpl import FPLClient
from fantasy_app.recommend.fpl import CandidatePlayer, TransferSuggestion, pick_starting_xi, suggest_transfers
from fantasy_app.services import fpl_service
from fantasy_app.services.team_matching import normalize_team_name

# Tiers come straight from the team's own predicted win probability in that fixture — the same
# trusted number already shown in Score Predictions, not a separate invented metric.
DIFFICULTY_THRESHOLDS = [(0.60, 1), (0.45, 2), (0.33, 3), (0.20, 4)]  # below all of these -> 5
TOP_PLAYERS_COUNT = 6
RECENT_POINTS_COUNT = 6


def difficulty_tier(win_prob: float) -> int:
    """1 (easiest fixture) .. 5 (hardest), from this team's own predicted win probability."""
    for threshold, tier in DIFFICULTY_THRESHOLDS:
        if win_prob >= threshold:
            return tier
    return 5


@dataclass(frozen=True)
class FixtureDifficulty:
    event: int
    opponent: str
    is_home: bool
    tier: int
    win_prob: float


def _find_fpl_team_id(team_name: str, norm_name_by_id: dict[int, str]) -> int | None:
    target = normalize_team_name(team_name)
    for tid, name in norm_name_by_id.items():
        if name == target:
            return tid
    for tid, name in norm_name_by_id.items():
        if target in name or name in target:
            return tid
    return None


def fixture_difficulty_run(
    client: FPLClient,
    team_name: str,
    start_event: int | None = None,
    num_gameweeks: int = 5,
    fd_client: FootballDataClient | None = None,
) -> list[FixtureDifficulty]:
    bootstrap = client.bootstrap()
    ratings, _, norm_name_by_id = fpl_service.fit_pl_ratings(client, bootstrap, fd_client=fd_client)
    start_event = start_event or client.current_event(bootstrap)
    team_name_by_id = {t["id"]: t["name"] for t in bootstrap["teams"]}

    team_id = _find_fpl_team_id(team_name, norm_name_by_id)
    if team_id is None:
        raise RuntimeError(f"No FPL team matches '{team_name}'.")

    results: list[FixtureDifficulty] = []
    for offset in range(num_gameweeks):
        event = start_event + offset
        fixtures = client.fixtures(event=event)
        fixture = next((f for f in fixtures if f["team_h"] == team_id or f["team_a"] == team_id), None)
        if fixture is None:
            continue  # blank gameweek for this team
        is_home = fixture["team_h"] == team_id
        pred = predict_fixture(ratings, norm_name_by_id[fixture["team_h"]], norm_name_by_id[fixture["team_a"]])
        win_prob = pred.p_home_win if is_home else pred.p_away_win
        opponent_id = fixture["team_a"] if is_home else fixture["team_h"]
        results.append(
            FixtureDifficulty(
                event=event,
                opponent=team_name_by_id[opponent_id],
                is_home=is_home,
                tier=difficulty_tier(win_prob),
                win_prob=round(win_prob, 3),
            )
        )
    return results


def player_recent_points(client: FPLClient, element_id: str | int, n: int = RECENT_POINTS_COUNT) -> list[int]:
    summary = client.element_summary(int(element_id))
    history = summary.get("history", [])
    return [g["total_points"] for g in history[-n:]]


@dataclass(frozen=True)
class TeamTotals:
    total_points: int
    overall_rank: int
    event_points: int
    squad_value: float


@dataclass(frozen=True)
class TopPlayerCard:
    player: CandidatePlayer
    recent_points: list[int]


@dataclass(frozen=True)
class OverviewResult:
    team_totals: TeamTotals | None
    recommended_move: TransferSuggestion | None
    top_players: list[TopPlayerCard]
    fixture_run: list[FixtureDifficulty]
    fixture_run_team: str | None


def build_overview(
    client: FPLClient,
    current_squad: list[CandidatePlayer],
    pool: list[CandidatePlayer],
    bank: float,
    entry_totals: dict | None = None,
    fd_client: FootballDataClient | None = None,
    event: int | None = None,
) -> OverviewResult:
    team_totals = None
    if entry_totals is not None:
        team_totals = TeamTotals(
            total_points=entry_totals.get("summary_overall_points", 0) or 0,
            overall_rank=entry_totals.get("summary_overall_rank", 0) or 0,
            event_points=entry_totals.get("summary_event_points", 0) or 0,
            squad_value=(entry_totals.get("last_deadline_value", 0) or 0) / 10.0,
        )

    transfers = suggest_transfers(current_squad, pool, bank=bank, free_transfers=1) if current_squad else []
    recommended_move = transfers[0] if transfers else None

    ranked = sorted(pool, key=lambda p: p.xp, reverse=True)[:TOP_PLAYERS_COUNT]
    top_players = []
    for p in ranked:
        try:
            recent = player_recent_points(client, p.id)
        except Exception:
            recent = []
        top_players.append(TopPlayerCard(player=p, recent_points=recent))

    # The fixture-difficulty ticker follows your captain's club (the most personally relevant
    # team), falling back to the top overall candidate's club if there's no current squad yet.
    fixture_run_team = None
    if current_squad:
        starters, _ = pick_starting_xi(current_squad)
        fixture_run_team = max(starters, key=lambda p: p.xp).team
    elif ranked:
        fixture_run_team = ranked[0].team

    fixture_run: list[FixtureDifficulty] = []
    if fixture_run_team:
        try:
            fixture_run = fixture_difficulty_run(client, fixture_run_team, start_event=event, fd_client=fd_client)
        except Exception:
            fixture_run = []

    return OverviewResult(
        team_totals=team_totals,
        recommended_move=recommended_move,
        top_players=top_players,
        fixture_run=fixture_run,
        fixture_run_team=fixture_run_team,
    )
