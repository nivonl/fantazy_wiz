"""
Official FPL public API client. Every endpoint used here is unauthenticated — reading an
entry's picks by ID does not require that entry's login, only its numeric ID (findable in the
URL when viewing "Points"/"Transfers" for that team on fantasy.premierleague.com).
"""

from __future__ import annotations

import httpx

BASE = "https://fantasy.premierleague.com/api"

# FPL's element_type id -> our position code
POSITION_BY_ELEMENT_TYPE = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}


class FPLClient:
    def __init__(self, timeout: float = 15.0):
        self._client = httpx.Client(base_url=BASE, timeout=timeout, headers={"User-Agent": "fantasy-app/0.1"})

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "FPLClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def bootstrap(self) -> dict:
        """Teams, players (elements), gameweeks (events), positions (element_types)."""
        r = self._client.get("/bootstrap-static/")
        r.raise_for_status()
        return r.json()

    def fixtures(self, event: int | None = None) -> list[dict]:
        params = {"event": event} if event is not None else {}
        r = self._client.get("/fixtures/", params=params)
        r.raise_for_status()
        return r.json()

    def element_summary(self, element_id: int) -> dict:
        """Per-player history: past seasons + this season's per-gameweek log."""
        r = self._client.get(f"/element-summary/{element_id}/")
        r.raise_for_status()
        return r.json()

    def entry(self, entry_id: int) -> dict:
        r = self._client.get(f"/entry/{entry_id}/")
        r.raise_for_status()
        return r.json()

    def entry_picks(self, entry_id: int, event: int) -> dict:
        r = self._client.get(f"/entry/{entry_id}/event/{event}/picks/")
        r.raise_for_status()
        return r.json()

    def current_event(self, bootstrap: dict | None = None) -> int:
        """The gameweek marked is_current (falls back to the next unstarted one)."""
        data = bootstrap or self.bootstrap()
        for event in data["events"]:
            if event.get("is_current"):
                return event["id"]
        for event in data["events"]:
            if not event.get("finished"):
                return event["id"]
        return data["events"][-1]["id"]
