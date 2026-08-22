"""
football-data.org client — used only for La Liga (competition code PD) historical
fixtures/results, to fit strength.py's attack/defense ratings. Free tier, requires a
personal token (FOOTBALL_DATA_TOKEN) from https://www.football-data.org/client/register.

Not used for Premier League: FPL's own /fixtures/ endpoint already gives us PL results
without a second data source.
"""

from __future__ import annotations

import os

import httpx

BASE = "https://api.football-data.org/v4"
LA_LIGA_CODE = "PD"


class FootballDataClient:
    def __init__(self, token: str | None = None, timeout: float = 15.0):
        token = token or os.environ.get("FOOTBALL_DATA_TOKEN")
        if not token:
            raise RuntimeError(
                "FOOTBALL_DATA_TOKEN is not set. Sign up for a free token at "
                "https://www.football-data.org/client/register and put it in .env."
            )
        self._client = httpx.Client(
            base_url=BASE, timeout=timeout, headers={"X-Auth-Token": token}
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "FootballDataClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def teams(self, competition: str = LA_LIGA_CODE) -> list[dict]:
        r = self._client.get(f"/competitions/{competition}/teams")
        r.raise_for_status()
        return r.json()["teams"]

    def matches(
        self, competition: str = LA_LIGA_CODE, season: int | None = None, status: str | None = None
    ) -> list[dict]:
        """
        season: the year the season started (e.g. 2025 for 2025-26). Omit for the current one.
        status: e.g. "FINISHED" or "SCHEDULED"; omit for all.
        """
        params = {}
        if season is not None:
            params["season"] = season
        if status is not None:
            params["status"] = status
        r = self._client.get(f"/competitions/{competition}/matches", params=params)
        r.raise_for_status()
        return r.json()["matches"]
