from datetime import datetime, timezone


def current_season_start_year(today: datetime | None = None) -> int:
    """European domestic football seasons run roughly Aug-May; treat Jul as the rollover so
    `season - 1` and `season - 2` (used for historical-data fallback) mean what a fan expects."""
    today = today or datetime.now(timezone.utc)
    return today.year if today.month >= 7 else today.year - 1
