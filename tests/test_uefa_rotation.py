from datetime import datetime, timedelta, timezone

from fantasy_app.services.uefa_rotation import (
    MODERATE_DISCOUNT,
    STRONG_DISCOUNT,
    _rest_day_discount,
    compute_uefa_rotation_factors,
)


class _FakeFootballDataClient:
    """Stands in for FootballDataClient — only `.matches()` is used by
    compute_uefa_rotation_factors, so that's all this needs to fake."""

    def __init__(self, matches: list[dict]):
        self._matches = matches
        self.call_count = 0

    def matches(self, competition: str, season: int | None = None, status: str | None = None) -> list[dict]:
        self.call_count += 1
        return self._matches


def _match(home: str, away: str, when: datetime) -> dict:
    return {
        "utcDate": when.isoformat().replace("+00:00", "Z"),
        "homeTeam": {"name": home},
        "awayTeam": {"name": away},
    }


def test_rest_day_discount_thresholds():
    assert _rest_day_discount(1.0) == STRONG_DISCOUNT
    assert _rest_day_discount(2.9) == STRONG_DISCOUNT
    assert _rest_day_discount(3.0) == MODERATE_DISCOUNT
    assert _rest_day_discount(4.9) == MODERATE_DISCOUNT
    assert _rest_day_discount(5.0) == 1.0
    assert _rest_day_discount(10.0) == 1.0


def test_rest_day_discount_ignores_a_uefa_match_played_after_the_pl_kickoff():
    # A team due to play in Europe AFTER this weekend's PL game isn't rotation risk for THIS
    # fixture — that's a future gameweek's problem, not this one's.
    assert _rest_day_discount(-2.0) == 1.0


def test_compute_uefa_rotation_factors_flags_a_quick_turnaround():
    pl_kickoff = datetime(2026, 9, 13, 15, 30, tzinfo=timezone.utc)
    uefa_match = pl_kickoff - timedelta(days=2)  # Man City played Tuesday, PL is Sunday -> tight
    fd_client = _FakeFootballDataClient([_match("Manchester City FC", "FC Porto", uefa_match)])

    pl_fixture_by_team = {1: {}}
    norm_name_by_fpl_id = {1: "manchester city"}
    pl_kickoff_by_team = {1: pl_kickoff}

    factors = compute_uefa_rotation_factors(fd_client, pl_fixture_by_team, norm_name_by_fpl_id, pl_kickoff_by_team)
    assert factors == {1: STRONG_DISCOUNT}


def test_compute_uefa_rotation_factors_ignores_teams_with_no_recent_uefa_match():
    pl_kickoff = datetime(2026, 9, 13, 15, 30, tzinfo=timezone.utc)
    fd_client = _FakeFootballDataClient([])  # no UEFA fixtures at all this window

    factors = compute_uefa_rotation_factors(
        fd_client, {1: {}}, {1: "manchester city"}, {1: pl_kickoff}
    )
    assert factors == {}


def test_compute_uefa_rotation_factors_ignores_non_pl_clubs_in_the_uefa_fixture():
    # Real Madrid isn't one of ours -- the match should be skipped entirely, not raise or
    # attribute the discount to some other team.
    pl_kickoff = datetime(2026, 9, 13, 15, 30, tzinfo=timezone.utc)
    uefa_match = pl_kickoff - timedelta(days=2)
    fd_client = _FakeFootballDataClient([_match("Real Madrid CF", "FC Internazionale Milano", uefa_match)])

    factors = compute_uefa_rotation_factors(
        fd_client, {1: {}}, {1: "manchester city"}, {1: pl_kickoff}
    )
    assert factors == {}


def test_compute_uefa_rotation_factors_returns_empty_without_a_client():
    assert compute_uefa_rotation_factors(None, {1: {}}, {1: "manchester city"}, {1: datetime.now(timezone.utc)}) == {}


def test_compute_uefa_rotation_factors_reuses_matches_across_calls_with_the_same_client():
    # bulk_player_gameweek_projections calls this once per gameweek in its window (up to
    # MAX_PLAYER_PROJECTION_GAMEWEEKS times) with the same fd_client instance threaded through
    # every iteration -- without caching, that's a fresh football-data.org call every single
    # gameweek for one request, which both wastes time and risks tripping the free tier's rate
    # limit. The season's UEFA schedule doesn't change between one gameweek and the next in the
    # same run, so the underlying matches() call should only happen once per client instance.
    pl_kickoff = datetime(2026, 9, 13, 15, 30, tzinfo=timezone.utc)
    uefa_match = pl_kickoff - timedelta(days=2)
    fd_client = _FakeFootballDataClient([_match("Manchester City FC", "FC Porto", uefa_match)])

    for _ in range(5):
        factors = compute_uefa_rotation_factors(fd_client, {1: {}}, {1: "manchester city"}, {1: pl_kickoff})
        assert factors == {1: STRONG_DISCOUNT}
    assert fd_client.call_count == 1

    # A different client instance (e.g. a separate request's own FootballDataClient) must not
    # see another instance's cached matches -- it has its own fixtures to fetch and cache.
    other_client = _FakeFootballDataClient([])
    assert compute_uefa_rotation_factors(other_client, {1: {}}, {1: "manchester city"}, {1: pl_kickoff}) == {}
    assert other_client.call_count == 1
