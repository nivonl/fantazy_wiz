"""
Per-player percentile "stat radar": how a player's rate stats compare to their peers, across
three time windows (last 3 gameweeks, previous season, career) and, for outfield players, two
comparison pools (every outfield PL player, or just their own position). Sourced entirely from
providers/fpl_history.py's cached multi-season archive -- including the "last 3 GWs" window,
which relies on that module never trusting a stale on-disk copy of the season still in progress.

Category composition is position-specific. FPL's raw data has no direct possession/passing
stat, so those axes are mapped onto FPL's own named ICT sub-indices instead -- creativity
(chance creation) and influence (overall match impact) -- the closest honest signal the data
actually supports; a Defending category built from the newer defensive-actions fields covers
the rest. A forward's Defending doesn't count clean sheets/goals conceded (a team outcome, not
an individual one) the way a defender's or midfielder's does. Goalkeepers get an entirely
different 4-category set (Scoring/Creativity are meaningless for a keeper) and skip the "all
players" pool entirely, since GK-only stats like saves would leave every outfield player pinned
near zero and vice versa.
"""

from __future__ import annotations

from dataclasses import dataclass

from scipy import stats as scipy_stats

from fantasy_app.providers import fpl_history
from fantasy_app.providers.fpl import POSITION_BY_ELEMENT_TYPE
from fantasy_app.providers.fpl_history import HistoryRow

QUALIFYING_MINUTES = 25  # a game only counts toward a player's rate stats past this threshold
MIN_SAMPLE_MINUTES = 180  # minimum qualifying minutes to enter a previous_season/career pool
LAST_N_ROUNDS = 3

WINDOW_LAST3 = "last3"
WINDOW_PREVIOUS_SEASON = "previous_season"
WINDOW_CAREER = "career"
WINDOWS = (WINDOW_LAST3, WINDOW_PREVIOUS_SEASON, WINDOW_CAREER)

GROUP_ALL = "all"
GROUP_POSITION = "position"

# category_key -> (label, [(field, higher_is_better), ...])
_SCORING = ("Scoring", [("goals_scored", True), ("expected_goals", True), ("threat", True)])
_CREATIVITY = ("Creativity", [("assists", True), ("expected_assists", True), ("creativity", True)])
_INVOLVEMENT = ("Involvement", [("influence", True), ("bps", True)])

# Individual defensive actions apply to every outfield position; clean sheets/goals conceded are
# a TEAM outcome, only meaningful for the positions actually judged on them.
_DEFENDING_CORE = [
    ("tackles", True),
    ("clearances_blocks_interceptions", True),
    ("recoveries", True),
    ("defensive_contribution", True),
]
_DEFENDING_TEAM = [("clean_sheets", True), ("goals_conceded", False)]

Category = tuple[str, list[tuple[str, bool]]]  # (label, [(field, higher_is_better), ...])


def _outfield_categories(pos: str) -> dict[str, Category]:
    defending_fields = _DEFENDING_CORE + (_DEFENDING_TEAM if pos in ("DEF", "MID") else [])
    return {
        "scoring": _SCORING,
        "creativity": _CREATIVITY,
        "involvement": _INVOLVEMENT,
        "defending": ("Defending", defending_fields),
    }


GK_CATEGORIES: dict[str, Category] = {
    "shot_stopping": ("Shot Stopping", [("saves", True)]),
    "clean_sheets": ("Clean Sheets", [("clean_sheets", True)]),
    "goals_prevented": ("Goals Prevented", [("goals_conceded", False)]),
    "involvement": ("Involvement", [("influence", True), ("bps", True)]),
}

_ALL_FIELDS = {f for _, fields in GK_CATEGORIES.values() for f, _ in fields}
_ALL_FIELDS |= {f for _, fields in (_SCORING, _CREATIVITY, _INVOLVEMENT) for f, _ in fields}
_ALL_FIELDS |= {f for f, _ in _DEFENDING_CORE + _DEFENDING_TEAM}


def _qualifying_rows(
    rows: list[HistoryRow], *, season: str | None = None, last_n_rounds: int | None = None
) -> list[HistoryRow]:
    filtered = [r for r in rows if r.minutes >= QUALIFYING_MINUTES]
    if season is not None:
        filtered = [r for r in filtered if r.season == season]
    if last_n_rounds is not None:
        filtered = sorted(filtered, key=lambda r: r.round)[-last_n_rounds:]
    return filtered


def _per90_rate(rows: list[HistoryRow], field: str) -> float | None:
    """sum(field over rows where field isn't None) / sum(those rows' minutes) * 90. Skipping
    None rows (rather than treating them as 0) is what makes a career rate for a stat that only
    exists in recent seasons (xG, defensive_contribution, ...) cover just those seasons, not get
    diluted by seasons that never recorded it at all."""
    total = 0.0
    minutes = 0
    for r in rows:
        v = getattr(r, field)
        if v is None:
            continue
        total += v
        minutes += r.minutes
    if minutes == 0:
        return None
    return total / minutes * 90.0


@dataclass(frozen=True)
class _PlayerWindowRates:
    element_id: str
    pos: str
    qualifying_minutes: int
    rates: dict[str, float]  # field -> per-90 rate, only present when there was data for it


def _collect_window_rates(
    elements: list[dict], history_index: dict[str, list[HistoryRow]], select_rows
) -> list[_PlayerWindowRates]:
    out: list[_PlayerWindowRates] = []
    for element in elements:
        pos = POSITION_BY_ELEMENT_TYPE[element["element_type"]]
        full_name = fpl_history.normalize_person_name(f"{element['first_name']} {element['second_name']}")
        rows = select_rows(history_index.get(full_name, []))
        if not rows:
            continue
        rates = {f: rate for f in _ALL_FIELDS if (rate := _per90_rate(rows, f)) is not None}
        if not rates:
            continue
        out.append(
            _PlayerWindowRates(
                element_id=str(element["id"]),
                pos=pos,
                qualifying_minutes=sum(r.minutes for r in rows),
                rates=rates,
            )
        )
    return out


def _percentile_pools(rates_list: list[_PlayerWindowRates], *, min_minutes: int) -> dict[str, dict[str, float]]:
    """field -> {element_id: value}, for players with enough of a sample to count toward the
    comparison pool at all (a two-substitute-appearance sample shouldn't set the bar for what
    "90th percentile" means)."""
    pools: dict[str, dict[str, float]] = {}
    for pw in rates_list:
        if pw.qualifying_minutes < min_minutes:
            continue
        for field, value in pw.rates.items():
            pools.setdefault(field, {})[pw.element_id] = value
    return pools


def _percentile(pool: dict[str, float], element_id: str, higher_is_better: bool) -> float | None:
    if element_id not in pool or len(pool) < 2:
        return None
    pct = scipy_stats.percentileofscore(list(pool.values()), pool[element_id], kind="mean")
    return float(pct) if higher_is_better else 100.0 - float(pct)


def _category_scores(categories: dict[str, Category], pools: dict[str, dict[str, float]], element_id: str) -> dict[str, float] | None:
    scores: dict[str, float] = {}
    for key, (_, fields) in categories.items():
        pcts = [p for field, higher in fields if (p := _percentile(pools.get(field, {}), element_id, higher)) is not None]
        if pcts:
            scores[key] = round(sum(pcts) / len(pcts), 1)
    return scores or None


def build_player_radar_table(bootstrap: dict) -> dict[str, dict]:
    elements = bootstrap["elements"]
    history_index = fpl_history.index_by_player()
    current_season = fpl_history.current_season_label()
    prev_start = int(current_season.split("-")[0]) - 1
    previous_season = f"{prev_start}-{str(prev_start + 1)[2:]}"

    selectors = {
        WINDOW_LAST3: lambda rows: _qualifying_rows(rows, season=current_season, last_n_rounds=LAST_N_ROUNDS),
        WINDOW_PREVIOUS_SEASON: lambda rows: _qualifying_rows(rows, season=previous_season),
        WINDOW_CAREER: lambda rows: _qualifying_rows(rows),
    }
    min_minutes_by_window = {WINDOW_LAST3: 1, WINDOW_PREVIOUS_SEASON: MIN_SAMPLE_MINUTES, WINDOW_CAREER: MIN_SAMPLE_MINUTES}

    result: dict[str, dict] = {}

    for window in WINDOWS:
        rates_list = _collect_window_rates(elements, history_index, selectors[window])
        min_minutes = min_minutes_by_window[window]

        outfield_rates = [pw for pw in rates_list if pw.pos != "GK"]
        gk_rates = [pw for pw in rates_list if pw.pos == "GK"]

        outfield_all_pool = _percentile_pools(outfield_rates, min_minutes=min_minutes)
        gk_pool = _percentile_pools(gk_rates, min_minutes=min_minutes)

        outfield_by_pos: dict[str, list[_PlayerWindowRates]] = {}
        for pw in outfield_rates:
            outfield_by_pos.setdefault(pw.pos, []).append(pw)
        outfield_pos_pools = {pos: _percentile_pools(rows, min_minutes=min_minutes) for pos, rows in outfield_by_pos.items()}

        for pw in rates_list:
            if pw.pos == "GK":
                categories = GK_CATEGORIES
                all_score = None
                position_score = _category_scores(categories, gk_pool, pw.element_id)
            else:
                categories = _outfield_categories(pw.pos)
                all_score = _category_scores(categories, outfield_all_pool, pw.element_id)
                position_score = _category_scores(categories, outfield_pos_pools.get(pw.pos, {}), pw.element_id)

            if all_score is None and position_score is None:
                continue  # no field had enough data at all for this window -- omit, don't show nulls

            entry = result.setdefault(
                pw.element_id,
                {
                    "categoryLabels": {k: v[0] for k, v in categories.items()},
                    # Which raw fields feed each category -- fixed by position, same shape as
                    # categoryLabels -- so the frontend tooltip can show "what this percentile is
                    # based on" without duplicating the category definitions client-side.
                    "categoryFields": {k: [f for f, _ in fields] for k, (_, fields) in categories.items()},
                },
            )
            # The player's own per-90 rates, independent of which pool they're being compared
            # against (that only changes the *percentile*, not the underlying number) -- exposed
            # so a tooltip can show e.g. "Goals: 0.85/90" alongside "92.6th percentile".
            entry[window] = {
                GROUP_ALL: all_score,
                GROUP_POSITION: position_score,
                "stats": {k: round(v, 2) for k, v in pw.rates.items()},
            }

    return result
