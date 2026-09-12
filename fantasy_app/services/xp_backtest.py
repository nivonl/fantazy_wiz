"""
Reusable walk-forward helpers for xP / ratings backtests.

The GW1–2 price-prior work lived in an uncommitted scratchpad; reconstructing it for GW3
silently produced wrong answers when FOOTBALL_DATA_TOKEN was missing. This module is the
committed replacement: cutoff clients, early-season L2 ablation helpers, and MAE summaries
that call the same production `fit_pl_ratings` / `fit_ratings` paths the site uses.

Full season player-xP walk-forward still needs cumulative per-player stats as of each GW
(bootstrap is live-only). Prefer `scripts/backtest_xp_walkforward.py` for live runs; unit
tests cover the ratings-side shrinkage without network.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from fantasy_app.models.predict import predict_fixture
from fantasy_app.models.strength import MatchResult, Ratings, fit_ratings
from fantasy_app.providers.fpl import FPLClient


@dataclass(frozen=True)
class MaeSummary:
    n: int
    mae: float
    label: str = ""


def mean_absolute_error(predicted: list[float], actual: list[float]) -> float:
    if not predicted:
        raise ValueError("mean_absolute_error requires at least one pair")
    if len(predicted) != len(actual):
        raise ValueError("predicted and actual must be the same length")
    return sum(abs(p - a) for p, a in zip(predicted, actual)) / len(predicted)


class CutoffFPLClient:
    """Wraps an FPLClient so `fixtures()` (no event) only returns matches finished before
    `cutoff`. `fixtures(event=N)` is passed through unchanged so we can still score the
    upcoming gameweek's fixtures in a walk-forward step."""

    def __init__(self, inner: FPLClient, cutoff: datetime):
        self._inner = inner
        self.cutoff = cutoff

    def bootstrap(self) -> dict:
        return self._inner.bootstrap()

    def current_event(self, bootstrap: dict | None = None) -> int:
        return self._inner.current_event(bootstrap)

    def element_summary(self, element_id: int) -> dict:
        return self._inner.element_summary(element_id)

    def fixtures(self, event: int | None = None) -> list[dict]:
        rows = self._inner.fixtures(event=event)
        if event is not None:
            return rows
        out = []
        for f in rows:
            if not f.get("finished"):
                continue
            ko = f.get("kickoff_time")
            if not ko:
                continue
            played_at = datetime.fromisoformat(ko.replace("Z", "+00:00"))
            if played_at >= self.cutoff:
                continue
            out.append(f)
        return out


def count_matches_per_team(matches: list[MatchResult]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for m in matches:
        counts[m.home_team_id] = counts.get(m.home_team_id, 0) + 1
        counts[m.away_team_id] = counts.get(m.away_team_id, 0) + 1
    return counts


def fit_ratings_variants(
    matches: list[MatchResult],
    *,
    as_of: datetime,
    current_season_matches: list[MatchResult],
    early_season_l2_boost: float,
    early_season_full_strength_matches: int = 8,
) -> tuple[Ratings, Ratings]:
    """Return (baseline ratings with boost=0, shrunk ratings with the given boost)."""
    current_counts = count_matches_per_team(current_season_matches)
    baseline = fit_ratings(
        matches,
        as_of=as_of,
        team_current_season_matches=current_counts,
        early_season_l2_boost=0.0,
        early_season_full_strength_matches=early_season_full_strength_matches,
    )
    shrunk = fit_ratings(
        matches,
        as_of=as_of,
        team_current_season_matches=current_counts,
        early_season_l2_boost=early_season_l2_boost,
        early_season_full_strength_matches=early_season_full_strength_matches,
    )
    return baseline, shrunk


def fixture_xg_mae(
    ratings: Ratings,
    fixtures: list[tuple[str, str, float, float]],
) -> MaeSummary:
    """`fixtures` rows are (home, away, actual_home_goals, actual_away_goals)."""
    preds: list[float] = []
    acts: list[float] = []
    for home, away, hg, ag in fixtures:
        lam_h, lam_a = ratings.expected_goals(home, away)
        preds.extend([lam_h, lam_a])
        acts.extend([hg, ag])
    return MaeSummary(n=len(fixtures), mae=mean_absolute_error(preds, acts))


def require_football_data_token(fd_client_factory: Callable[[], object | None]) -> object:
    """Fail loudly if historical blend cannot run — silent None caused a bad GW3 reconstruct."""
    client = fd_client_factory()
    if client is None:
        raise RuntimeError(
            "FOOTBALL_DATA_TOKEN is not configured. Early-season ratings backtests require "
            "the historical PL blend; refusing to continue with a silent fallback."
        )
    return client


def predict_fixture_lambdas(ratings: Ratings, home: str, away: str) -> tuple[float, float]:
    pred = predict_fixture(ratings, home, away)
    return pred.lam_home, pred.lam_away


# --- Act A version ladder (player–GW walk-forward) ----------------------------------------

@dataclass(frozen=True)
class ModelVersion:
    """Public ladder names for Medium Act A MAE tables."""

    name: str
    use_price_prior: bool
    use_minutes_rates: bool  # False = starts-only (V0)
    use_squad_depth: bool
    use_momentum: bool
    early_season_l2_boost: float


def model_version_ladder(boost: float = 3.0) -> list[ModelVersion]:
    """V0 → V1 → V1−mom (ablation) → V2 (early-season team L2)."""
    return [
        ModelVersion("V0", False, False, False, False, 0.0),
        ModelVersion("V1", True, True, True, False, 0.0),
        ModelVersion("V1-mom", True, True, True, True, 0.0),
        ModelVersion("V2", True, True, True, False, boost),
    ]


def evidence_bucket(effective_matches: float) -> str:
    if effective_matches <= 0:
        return "0"
    if effective_matches < 3:
        return "1-2"
    if effective_matches < 6:
        return "3-5"
    return "6+"


def momentum_factor_ablation(element: dict) -> float:
    """Rejected form-vs-ppg multiplier (Medium ablation only — not shipped)."""
    try:
        form = float(element.get("form") or 0.0)
        ppg = float(element.get("points_per_game") or 0.0)
    except (TypeError, ValueError):
        return 1.0
    if ppg <= 0.05:
        return 1.0
    return max(0.5, min(1.5, form / ppg))


def player_rates_for_version(
    element: dict,
    price_priors: dict,
    version: ModelVersion,
) -> tuple[float, float, float]:
    """Versioned (goal_rate, assist_rate, start_prob) for the MAE ladder."""
    from fantasy_app.services.fpl_service import _player_rates

    chance = element.get("chance_of_playing_next_round")
    start_prob = 0.9 if chance is None else max(chance, 0) / 100.0

    if version.use_minutes_rates and version.use_price_prior:
        goal_rate, assist_rate, start_prob = _player_rates(element, price_priors)
        return goal_rate, assist_rate, start_prob

    # V0: starts-only observed rates, zero when starts==0 (no price prior).
    starts = element.get("starts", 0) or 0
    if starts <= 0:
        return 0.0, 0.0, start_prob
    goals = element.get("goals_scored", 0) or 0
    assists = element.get("assists", 0) or 0
    return goals / starts, assists / starts, start_prob


def accumulate_element_asof(base: dict, history: list[dict], before_round: int) -> dict:
    """Bootstrap-like cumulative fields from element-summary history before `before_round`."""
    prior = [h for h in history if (h.get("round") or 0) < before_round]
    el = dict(base)
    for key in (
        "minutes",
        "goals_scored",
        "assists",
        "saves",
        "starts",
        "defensive_contribution",
        "yellow_cards",
        "total_points",
    ):
        el[key] = int(sum(h.get(key, 0) or 0 for h in prior))
    if prior and prior[-1].get("value") is not None:
        el["now_cost"] = int(prior[-1]["value"])
    recent = prior[-3:]
    if recent:
        el["form"] = round(sum(h.get("total_points", 0) or 0 for h in recent) / len(recent), 1)
    else:
        el["form"] = 0.0
    starts = el.get("starts", 0) or 0
    el["points_per_game"] = round(el["total_points"] / starts, 1) if starts else 0.0
    el["chance_of_playing_next_round"] = None
    return el


def history_row_for_round(history: list[dict], round_: int) -> dict | None:
    for h in history:
        if h.get("round") == round_:
            return h
    return None


def summarize_mae_by_bucket(rows: list[dict]) -> list[dict]:
    """`rows` need keys: version, abs_err, evidence_bucket, early_season (bool)."""
    from collections import defaultdict

    groups: dict[tuple, list[float]] = defaultdict(list)
    for r in rows:
        groups[(r["version"], "overall", "all")].append(r["abs_err"])
        groups[(r["version"], "evidence", r["evidence_bucket"])].append(r["abs_err"])
        season_split = "early" if r.get("early_season") else "late"
        groups[(r["version"], "season_half", season_split)].append(r["abs_err"])

    out = []
    for (version, facet, key), errs in sorted(groups.items()):
        out.append(
            {
                "version": version,
                "facet": facet,
                "key": key,
                "n": len(errs),
                "mae": sum(errs) / len(errs),
            }
        )
    return out
