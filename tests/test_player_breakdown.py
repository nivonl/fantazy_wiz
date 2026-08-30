import pytest

from fantasy_app.providers.fpl_history import HistoryRow
from fantasy_app.services import player_breakdown
from fantasy_app.services.player_breakdown import build_player_breakdown, current_season_label


def _bootstrap():
    return {
        "teams": [{"id": 1, "name": "Arsenal"}, {"id": 2, "name": "Chelsea"}],
        "elements": [{"id": 42, "first_name": "Martin", "second_name": "Ødegaard"}],
    }


def _gw_row(round_, points, opponent_team=2, was_home=True, **extra):
    row = {
        "round": round_, "total_points": points, "minutes": 90, "opponent_team": opponent_team,
        "was_home": was_home, "goals_scored": 0, "assists": 0, "clean_sheets": 0, "goals_conceded": 1,
        "own_goals": 0, "penalties_saved": 0, "penalties_missed": 0, "yellow_cards": 0, "red_cards": 0,
        "saves": 0, "bonus": 0,
    }
    row.update(extra)
    return row


class _FakeClient:
    def __init__(self, history):
        self._history = history

    def bootstrap(self):
        return _bootstrap()

    def element_summary(self, element_id):
        return {"history": self._history}


def test_build_player_breakdown_uses_this_season_when_enough_played():
    history = [_gw_row(1, 2), _gw_row(2, 8, goals_scored=1), _gw_row(3, 5, bonus=2)]
    result = build_player_breakdown(_FakeClient(history), element_id=42, n=3)

    assert result.note is None
    assert [r.gameweek for r in result.recent] == [1, 2, 3]
    assert all(r.season == current_season_label() for r in result.recent)
    assert result.recent[1].goals_scored == 1
    assert result.recent[2].bonus == 2
    assert result.recent[0].opponent == "Chelsea"


def test_build_player_breakdown_only_takes_the_most_recent_n():
    history = [_gw_row(1, 1), _gw_row(2, 2), _gw_row(3, 3), _gw_row(4, 4)]
    result = build_player_breakdown(_FakeClient(history), element_id=42, n=2)
    assert [r.gameweek for r in result.recent] == [3, 4]
    assert result.note is None


def test_build_player_breakdown_falls_back_to_previous_season(monkeypatch):
    history = [_gw_row(1, 9)]  # only 1 gameweek played this season
    fake_index = {
        "martin odegaard": [
            HistoryRow(season="2024-25", player="martin odegaard", team="Arsenal", opponent="Spurs",
                       round=36, total_points=6, minutes=90, goals_scored=0, assists=1, was_home=False),
            HistoryRow(season="2024-25", player="martin odegaard", team="Arsenal", opponent="Everton",
                       round=37, total_points=11, minutes=90, goals_scored=1, assists=0, was_home=True),
            HistoryRow(season="2024-25", player="martin odegaard", team="Arsenal", opponent="Wolves",
                       round=38, total_points=3, minutes=90, goals_scored=0, assists=0, was_home=False),
        ]
    }
    monkeypatch.setattr(player_breakdown.fpl_history, "index_by_player", lambda: fake_index)

    result = build_player_breakdown(_FakeClient(history), element_id=42, n=3)

    assert [(r.season, r.gameweek) for r in result.recent] == [
        ("2024-25", 37), ("2024-25", 38), (current_season_label(), 1),
    ]
    assert result.note is not None
    assert "2024-25" in result.note
    assert "1 gameweek(s) played this season" in result.note


def test_build_player_breakdown_no_fallback_available_leaves_note_none(monkeypatch):
    monkeypatch.setattr(player_breakdown.fpl_history, "index_by_player", lambda: {})
    result = build_player_breakdown(_FakeClient([_gw_row(1, 4)]), element_id=42, n=3)
    assert len(result.recent) == 1
    assert result.note is None


def test_build_player_breakdown_raises_for_unknown_player():
    with pytest.raises(RuntimeError, match="No FPL player"):
        build_player_breakdown(_FakeClient([]), element_id=999, n=3)
