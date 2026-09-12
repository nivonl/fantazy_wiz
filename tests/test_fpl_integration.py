"""
End-to-end check against the real FPL API. Since this is being written in preseason (zero
finished fixtures yet — confirmed live), it patches in synthetic "finished" scores for the
ratings fit while using the real, unplayed gameweek-1 fixtures for prediction, so the full
build_candidate_pool -> optimize_squad pipeline gets exercised against real player/team data.
Once the season has real results, this still passes unchanged (the patch just becomes unused
plumbing that's harmless to keep, since it swaps a different config through the same seams
predict_gameweek/build_candidate_pool call).
"""

from __future__ import annotations

import random

import pytest

from fantasy_app.providers.fpl import FPLClient
from fantasy_app.recommend.fpl import CLUB_CAP, SQUAD_SHAPE, optimize_squad
from fantasy_app.services import fpl_service


def _synthesize_finished_fixtures(real_fixtures: list[dict]) -> list[dict]:
    rng = random.Random(7)
    out = []
    for f in real_fixtures[:80]:
        g = dict(f)
        g["finished"] = True
        g["team_h_score"] = rng.randint(0, 3)
        g["team_a_score"] = rng.randint(0, 3)
        out.append(g)
    return out


@pytest.fixture(scope="module")
def real_fpl_data() -> tuple[dict, list[dict]]:
    try:
        with FPLClient() as client:
            bootstrap = client.bootstrap()
            fixtures = client.fixtures()
    except Exception as e:  # network unavailable in this environment
        pytest.skip(f"FPL API unreachable: {e}")
    return bootstrap, fixtures


def test_build_and_optimize_squad_end_to_end(real_fpl_data):
    bootstrap, real_fixtures = real_fpl_data
    synthetic_finished = _synthesize_finished_fixtures(real_fixtures)
    current_event = 1

    class PatchedClient(FPLClient):
        def bootstrap(self) -> dict:
            return bootstrap

        def fixtures(self, event: int | None = None) -> list[dict]:
            if event is None:
                return synthetic_finished
            return [f for f in real_fixtures if f["event"] == event]

        def current_event(self, bootstrap: dict | None = None) -> int:
            return current_event

    with PatchedClient() as client:
        pool = fpl_service.build_candidate_pool(client, event=current_event)

    assert len(pool) > 300  # most of the ~587 real elements should have a GW1 fixture

    result = optimize_squad(pool)
    assert len(result.squad) == 15
    assert len(result.starters) == 11
    assert len(result.bench) == 4
    assert result.total_price <= 100.0

    pos_counts: dict[str, int] = {}
    for p in result.squad:
        pos_counts[p.pos] = pos_counts.get(p.pos, 0) + 1
    assert pos_counts == SQUAD_SHAPE

    team_counts: dict[str, int] = {}
    for p in result.squad:
        team_counts[p.team] = team_counts.get(p.team, 0) + 1
    assert all(c <= CLUB_CAP for c in team_counts.values())


def test_player_gameweek_projections_are_per_gameweek_not_summed(real_fpl_data):
    bootstrap, real_fixtures = real_fpl_data
    synthetic_finished = _synthesize_finished_fixtures(real_fixtures)
    current_event = 1

    class PatchedClient(FPLClient):
        def bootstrap(self) -> dict:
            return bootstrap

        def fixtures(self, event: int | None = None) -> list[dict]:
            if event is None:
                return synthetic_finished
            return [f for f in real_fixtures if f["event"] == event]

        def current_event(self, bootstrap: dict | None = None) -> int:
            return current_event

    with PatchedClient() as client:
        pool = fpl_service.build_candidate_pool(client, event=current_event)
        player = pool[0]
        projections = fpl_service.player_gameweek_projections(
            client, player.id, start_event=current_event, num_gameweeks=5
        )

    assert projections
    assert len(projections) <= 5
    events = [p.event for p in projections]
    assert events == sorted(events)
    assert events[0] >= current_event
    assert all(p.opponent and p.opponent != "?" for p in projections)


def test_bulk_player_gameweek_projections_covers_the_whole_pool(real_fpl_data):
    bootstrap, real_fixtures = real_fpl_data
    synthetic_finished = _synthesize_finished_fixtures(real_fixtures)
    current_event = 1

    class PatchedClient(FPLClient):
        def bootstrap(self) -> dict:
            return bootstrap

        def fixtures(self, event: int | None = None) -> list[dict]:
            if event is None:
                return synthetic_finished
            return [f for f in real_fixtures if f["event"] == event]

        def current_event(self, bootstrap: dict | None = None) -> int:
            return current_event

    with PatchedClient() as client:
        pool = fpl_service.build_candidate_pool(client, event=current_event)
        by_player = fpl_service.bulk_player_gameweek_projections(client, start_event=current_event, num_gameweeks=3)
        single = fpl_service.player_gameweek_projections(
            client, pool[0].id, start_event=current_event, num_gameweeks=3
        )

    assert len(by_player) > 300  # same real-pool-size expectation as build_candidate_pool_multi_gw
    # The single-player wrapper is just this same bulk result sliced by id.
    assert by_player.get(pool[0].id) == single
