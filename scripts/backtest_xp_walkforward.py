"""
Walk-forward / ablation runner for ratings + player-xP version ladder.

Usage (from fantasy_app repo root, with deps installed and FOOTBALL_DATA_TOKEN set):

    # Fixture-λ early-season L2 (GW3 story)
    python scripts/backtest_xp_walkforward.py
    python scripts/backtest_xp_walkforward.py --boost 3.0 --full-strength 8

    # Act A MAE ladder: V0 / V1 / V1-mom / V2 (players with 30+ minutes)
    python scripts/backtest_xp_walkforward.py --mode ladder --min-minutes 30
    python scripts/backtest_xp_walkforward.py --mode ladder --max-players 80  # smoke

Requires FOOTBALL_DATA_TOKEN. Ladder fetches element-summary history once per player
(cached under data/cache/ if --cache-dir is set).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fantasy_app.models.player_points import player_xp
from fantasy_app.models.predict import predict_fixture
from fantasy_app.providers.fpl import POSITION_BY_ELEMENT_TYPE, FPLClient
from fantasy_app.services.fpl_service import (
    EARLY_SEASON_FULL_STRENGTH_MATCHES,
    EARLY_SEASON_L2_BOOST,
    SQUAD_DEPTH_START_PROB_CAP,
    UNPROVEN_PLAYER_START_PROB_CAP,
    BACKUP_GK_START_PROB_CAP,
    _fit_price_rate_priors,
    _fixture_assist_share,
    _expected_defcon_points_if_playing,
    _expected_saves_if_playing,
    _is_backup_goalkeeper,
    _is_priced_like_backup,
    _is_unproven_this_season,
    _max_gk_minutes_by_team,
    _parse_kickoff,
    _squad_depth_price_threshold,
    _try_football_data_client,
    fit_pl_ratings,
)
from fantasy_app.services.team_matching import normalize_team_name
from fantasy_app.services.xp_backtest import (
    CutoffFPLClient,
    accumulate_element_asof,
    evidence_bucket,
    fixture_xg_mae,
    history_row_for_round,
    model_version_ladder,
    momentum_factor_ablation,
    player_rates_for_version,
    require_football_data_token,
    summarize_mae_by_bucket,
)


def _finished_events(fixtures: list[dict]) -> list[int]:
    return sorted({f["event"] for f in fixtures if f.get("finished") and f.get("event")})


def _event_cutoff(fixtures: list[dict], event: int) -> datetime:
    kicks = [
        _parse_kickoff(f.get("kickoff_time"))
        for f in fixtures
        if f.get("event") == event and f.get("kickoff_time")
    ]
    if not kicks:
        raise ValueError(f"No kickoffs found for event {event}")
    return min(kicks)


def _event_results(fixtures: list[dict], event: int, norm_name_by_id: dict[int, str]):
    rows = []
    for f in fixtures:
        if f.get("event") != event or not f.get("finished"):
            continue
        if f.get("team_h_score") is None or f.get("team_a_score") is None:
            continue
        rows.append(
            (
                norm_name_by_id[f["team_h"]],
                norm_name_by_id[f["team_a"]],
                float(f["team_h_score"]),
                float(f["team_a_score"]),
            )
        )
    return rows


def run_fixture_lambda_mode(args) -> int:
    fd = require_football_data_token(_try_football_data_client)
    client = FPLClient()
    bootstrap = client.bootstrap()
    all_fixtures = client.fixtures()
    events = [e for e in _finished_events(all_fixtures) if e >= args.min_event]

    base_maes: list[float] = []
    shrunk_maes: list[float] = []
    print(f"mode=fixture_lambda events={events} boost={args.boost} full_strength={args.full_strength}")

    for event in events:
        cutoff = _event_cutoff(all_fixtures, event)
        cutoff_client = CutoffFPLClient(client, cutoff)
        base_ratings, _, _ = fit_pl_ratings(
            cutoff_client,
            bootstrap,
            fd_client=fd,
            as_of=cutoff,
            early_season_l2_boost=0.0,
            early_season_full_strength_matches=args.full_strength,
        )
        shrunk_ratings, _, _ = fit_pl_ratings(
            cutoff_client,
            bootstrap,
            fd_client=fd,
            as_of=cutoff,
            early_season_l2_boost=args.boost,
            early_season_full_strength_matches=args.full_strength,
        )
        norm_name_by_id = {t["id"]: normalize_team_name(t["name"]) for t in bootstrap["teams"]}
        scored = _event_results(all_fixtures, event, norm_name_by_id)
        if not scored:
            continue
        base = fixture_xg_mae(base_ratings, scored)
        shrunk = fixture_xg_mae(shrunk_ratings, scored)
        base_maes.append(base.mae)
        shrunk_maes.append(shrunk.mae)
        print(f"GW{event}: n={base.n} mae_base={base.mae:.3f} mae_shrunk={shrunk.mae:.3f}")

    if not base_maes:
        print("No scored events — nothing to summarize.")
        return 1
    mean_base = sum(base_maes) / len(base_maes)
    mean_shrunk = sum(shrunk_maes) / len(shrunk_maes)
    delta = mean_base - mean_shrunk
    print(
        f"MEAN mae_base={mean_base:.3f} mae_shrunk={mean_shrunk:.3f} "
        f"delta={delta:+.3f} ({'better' if delta > 0 else 'worse'} with boost)"
    )
    return 0


def _load_histories(
    client: FPLClient,
    elements: list[dict],
    cache_dir: Path | None,
    max_players: int | None,
) -> dict[int, list[dict]]:
    if max_players is not None:
        elements = elements[:max_players]
    histories: dict[int, list[dict]] = {}
    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
    for i, el in enumerate(elements):
        eid = int(el["id"])
        cache_path = cache_dir / f"{eid}.json" if cache_dir else None
        if cache_path and cache_path.exists():
            histories[eid] = json.loads(cache_path.read_text(encoding="utf-8"))
            continue
        summary = client.element_summary(eid)
        hist = summary.get("history") or []
        histories[eid] = hist
        if cache_path:
            cache_path.write_text(json.dumps(hist), encoding="utf-8")
        if (i + 1) % 50 == 0:
            print(f"  cached element summaries {i + 1}/{len(elements)}")
    return histories


def _team_games_asof(fixtures: list[dict], before_event: int) -> dict[int, int]:
    games: dict[int, int] = {}
    for f in fixtures:
        ev = f.get("event")
        if not f.get("finished") or ev is None or ev >= before_event:
            continue
        games[f["team_h"]] = games.get(f["team_h"], 0) + 1
        games[f["team_a"]] = games.get(f["team_a"], 0) + 1
    return games


def _predict_one(
    element: dict,
    *,
    fixture: dict,
    ratings,
    goal_avgs: dict[str, float],
    norm_name_by_id: dict[int, str],
    price_priors: dict,
    price_thresholds: dict,
    team_games_played: dict[int, int],
    max_gk_minutes: dict[int, int],
    version,
) -> float:
    team_id = element["team"]
    is_home = fixture["team_h"] == team_id
    home_name = norm_name_by_id[fixture["team_h"]]
    away_name = norm_name_by_id[fixture["team_a"]]
    pred = predict_fixture(ratings, home_name, away_name)
    lam_team = pred.lam_home if is_home else pred.lam_away
    lam_opponent = pred.lam_away if is_home else pred.lam_home
    p_cs = pred.p_home_clean_sheet if is_home else pred.p_away_clean_sheet
    pos = POSITION_BY_ELEMENT_TYPE[element["element_type"]]
    goal_rate, assist_rate, start_prob = player_rates_for_version(element, price_priors, version)

    if version.use_squad_depth:
        if _is_unproven_this_season(element, team_games_played):
            start_prob = min(start_prob, UNPROVEN_PLAYER_START_PROB_CAP)
        if _is_backup_goalkeeper(element, max_gk_minutes):
            start_prob = min(start_prob, BACKUP_GK_START_PROB_CAP)
        if _is_priced_like_backup(element, price_thresholds, team_games_played):
            start_prob = min(start_prob, SQUAD_DEPTH_START_PROB_CAP)

    team_avg_goals = max(goal_avgs.get(norm_name_by_id[team_id], 1.0), 0.1)
    goal_share = min(goal_rate / team_avg_goals, 1.0)
    assist_share = _fixture_assist_share(assist_rate, lam_team, team_avg_goals)
    xp = player_xp(
        name=element["web_name"],
        pos=pos,
        price=element["now_cost"] / 10.0,
        lam_team=lam_team,
        lam_opponent=lam_opponent,
        p_cs=p_cs,
        goal_share=goal_share,
        assist_share=assist_share,
        save_rate=_expected_saves_if_playing(element, pos),
        defensive_contribution=_expected_defcon_points_if_playing(element),
        start_prob=start_prob,
    ).xp
    if version.use_momentum:
        xp *= momentum_factor_ablation(element)
    return float(xp)


def run_ladder_mode(args) -> int:
    fd = require_football_data_token(_try_football_data_client)
    client = FPLClient()
    bootstrap = client.bootstrap()
    all_fixtures = client.fixtures()
    events = [e for e in _finished_events(all_fixtures) if e >= args.min_event]
    versions = model_version_ladder(boost=args.boost)
    elements = list(bootstrap["elements"])
    cache_dir = Path(args.cache_dir) if args.cache_dir else ROOT / "data" / "cache" / "element_history"
    print(
        f"mode=ladder events={events} versions={[v.name for v in versions]} "
        f"min_minutes={args.min_minutes} max_players={args.max_players}"
    )
    print("Fetching element summaries (slow once; then cached)…")
    histories = _load_histories(client, elements, cache_dir, args.max_players)
    element_by_id = {int(e["id"]): e for e in elements if int(e["id"]) in histories}

    detail_rows: list[dict] = []
    for event in events:
        cutoff = _event_cutoff(all_fixtures, event)
        cutoff_client = CutoffFPLClient(client, cutoff)
        team_games = _team_games_asof(all_fixtures, event)
        fixture_by_team: dict[int, dict] = {}
        for f in all_fixtures:
            if f.get("event") != event:
                continue
            fixture_by_team.setdefault(f["team_h"], f)
            fixture_by_team.setdefault(f["team_a"], f)

        # Build as-of bootstrap elements for this deadline
        asof_elements = []
        for eid, base in element_by_id.items():
            asof_elements.append(accumulate_element_asof(base, histories[eid], event))
        asof_bootstrap = {"elements": asof_elements, "teams": bootstrap["teams"]}
        price_priors = _fit_price_rate_priors(asof_bootstrap)
        price_thresholds = _squad_depth_price_threshold(asof_bootstrap)
        max_gk = _max_gk_minutes_by_team(asof_bootstrap)

        ratings_by_version = {}
        goal_avgs_by_version = {}
        norm_by_version = {}
        for version in versions:
            ratings, goal_avgs, norm = fit_pl_ratings(
                cutoff_client,
                bootstrap,
                fd_client=fd,
                as_of=cutoff,
                early_season_l2_boost=version.early_season_l2_boost,
                early_season_full_strength_matches=args.full_strength,
            )
            ratings_by_version[version.name] = ratings
            goal_avgs_by_version[version.name] = goal_avgs
            norm_by_version[version.name] = norm

        n_scored = 0
        for el in asof_elements:
            eid = int(el["id"])
            row = history_row_for_round(histories[eid], event)
            if row is None:
                continue
            minutes = row.get("minutes", 0) or 0
            if minutes < args.min_minutes:
                continue
            fixture = fixture_by_team.get(el["team"])
            if fixture is None or not fixture.get("finished"):
                continue
            actual = float(row.get("total_points", 0) or 0)
            minutes_before = el.get("minutes", 0) or 0
            eff = minutes_before / 90.0
            early = event <= args.early_season_last_gw
            for version in versions:
                pred = _predict_one(
                    el,
                    fixture=fixture,
                    ratings=ratings_by_version[version.name],
                    goal_avgs=goal_avgs_by_version[version.name],
                    norm_name_by_id=norm_by_version[version.name],
                    price_priors=price_priors,
                    price_thresholds=price_thresholds,
                    team_games_played=team_games,
                    max_gk_minutes=max_gk,
                    version=version,
                )
                detail_rows.append(
                    {
                        "event": event,
                        "element_id": eid,
                        "version": version.name,
                        "pred": pred,
                        "actual": actual,
                        "abs_err": abs(pred - actual),
                        "evidence_bucket": evidence_bucket(eff),
                        "early_season": early,
                    }
                )
                n_scored += 1
        print(f"GW{event}: scored_rows={n_scored} (all versions × players)")

    if not detail_rows:
        print("No player–GW pairs scored.")
        return 1

    summary = summarize_mae_by_bucket(detail_rows)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_path = out_dir / "mae_version_ladder_summary.csv"
    detail_path = out_dir / "mae_version_ladder_detail.jsonl"
    with summary_path.open("w", encoding="utf-8") as f:
        f.write("version,facet,key,n,mae\n")
        for r in summary:
            f.write(f"{r['version']},{r['facet']},{r['key']},{r['n']},{r['mae']:.6f}\n")
    with detail_path.open("w", encoding="utf-8") as f:
        for r in detail_rows:
            f.write(json.dumps(r) + "\n")

    print("\nOverall MAE by version:")
    for r in summary:
        if r["facet"] == "overall":
            print(f"  {r['version']}: mae={r['mae']:.3f} n={r['n']}")
    print("\nMAE by evidence bucket:")
    for r in summary:
        if r["facet"] == "evidence":
            print(f"  {r['version']} [{r['key']}]: mae={r['mae']:.3f} n={r['n']}")
    print(f"wrote {summary_path}")
    print(f"wrote {detail_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("fixture_lambda", "ladder"), default="fixture_lambda")
    parser.add_argument("--boost", type=float, default=EARLY_SEASON_L2_BOOST)
    parser.add_argument("--full-strength", type=int, default=EARLY_SEASON_FULL_STRENGTH_MATCHES)
    parser.add_argument("--min-event", type=int, default=2, help="First event to score (need prior results)")
    parser.add_argument("--min-minutes", type=int, default=30, help="Ladder: only score appearances with ≥N minutes")
    parser.add_argument("--early-season-last-gw", type=int, default=8, help="Ladder: early vs late split")
    parser.add_argument("--max-players", type=int, default=None, help="Ladder smoke: cap element summaries")
    parser.add_argument("--cache-dir", type=str, default=None)
    parser.add_argument("--out-dir", type=str, default=str(ROOT / "data" / "backtests"))
    args = parser.parse_args()

    if args.mode == "fixture_lambda":
        return run_fixture_lambda_mode(args)
    return run_ladder_mode(args)


if __name__ == "__main__":
    raise SystemExit(main())
