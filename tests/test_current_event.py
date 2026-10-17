from fantasy_app.providers.fpl import FPLClient


def _bootstrap(*flags: tuple[bool, bool, bool]) -> dict:
    """One event per (is_current, finished, is_next) tuple, ids starting at 1."""
    return {
        "events": [
            {"id": i, "is_current": cur, "finished": fin, "is_next": nxt}
            for i, (cur, fin, nxt) in enumerate(flags, start=1)
        ]
    }


def _current_event(bootstrap: dict) -> int:
    with FPLClient() as client:
        return client.current_event(bootstrap)


def test_mid_gameweek_returns_the_gameweek_being_played():
    b = _bootstrap((False, True, False), (True, False, False), (False, False, True))
    assert _current_event(b) == 2


def test_finished_current_gameweek_returns_the_next_one():
    # FPL leaves is_current on a finished gameweek until the NEXT deadline passes (e.g. all of
    # an international break) -- predicting it then means predicting matches already played.
    b = _bootstrap((False, True, False), (True, True, False), (False, False, True), (False, False, False))
    assert _current_event(b) == 3


def test_finished_current_skips_to_next_unfinished_not_just_id_plus_one():
    b = _bootstrap((True, True, False), (False, True, False), (False, False, True))
    assert _current_event(b) == 3


def test_no_current_flag_falls_back_to_first_unfinished():
    b = _bootstrap((False, True, False), (False, False, True), (False, False, False))
    assert _current_event(b) == 2


def test_season_over_returns_last_gameweek():
    b = _bootstrap((False, True, False), (True, True, False))
    assert _current_event(b) == 2
