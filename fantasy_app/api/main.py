"""
Thin FastAPI layer over the service functions — exists so a future frontend (or multi-user
deployment) is an additive layer on top of this, not a rewrite. For solo local use, the CLI
(cli.py) calls the same service functions directly and is the faster day-to-day entry point.
The React app in frontend/ (dev: Vite on localhost:5173; prod: Netlify) is the primary UI now;
static/index.html is kept as a dependency-free fallback, still served by the StaticFiles mount
at the bottom. Run with `uvicorn fantasy_app.api.main:app --reload`.
"""

from __future__ import annotations

import os

import httpx
from dataclasses import asdict
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from fantasy_app.providers.cat9 import ManualSquad
from fantasy_app.providers.fpl import POSITION_BY_ELEMENT_TYPE, FPLClient
from fantasy_app.providers.football_data import FootballDataClient
from fantasy_app.recommend.fpl import optimize_squad
from fantasy_app.recommend.laliga import recommend_laliga
from fantasy_app.services import fpl_service, laliga_service, overview, player_breakdown

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

# Explicit path, not a bare load_dotenv(): the process's cwd depends on how uvicorn was
# launched (e.g. --app-dir), and relying on that guess silently no-ops the token loading.
load_dotenv(dotenv_path=STATIC_DIR.parent.parent / ".env")

app = FastAPI(title="PitchMetric", version="0.1.0")

# The frontend is hosted separately (Netlify) from this backend (Railway/Render/etc.), so
# browser requests are cross-origin. Nothing behind this API is secret or user-specific in a
# way that requires locking the origin down (no auth, no write endpoints, no per-user data —
# FOOTBALL_DATA_TOKEN never leaves the server), so a permissive default is fine; set
# ALLOWED_ORIGINS (comma-separated) in production if you want to restrict it to your actual
# Netlify domain instead.
_allowed_origins = os.environ.get("ALLOWED_ORIGINS", "*")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if _allowed_origins == "*" else [o.strip() for o in _allowed_origins.split(",")],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.exception_handler(RuntimeError)
def handle_runtime_error(request: Request, exc: RuntimeError) -> JSONResponse:
    # Raised deliberately by the service layer for known, explainable gaps (e.g. "the season
    # hasn't started yet, there's nothing to fit ratings from") — surface the message as-is
    # rather than a stack trace.
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(httpx.HTTPStatusError)
def handle_upstream_error(request: Request, exc: httpx.HTTPStatusError) -> JSONResponse:
    return JSONResponse(
        status_code=502,
        content={"detail": f"Upstream API error ({exc.response.status_code}): {exc.request.url}"},
    )


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/predict/fpl")
def predict_fpl(event: int | None = None) -> list[dict]:
    with FPLClient() as client:
        predictions = fpl_service.predict_gameweek(client, event=event)
    return [
        {"home_team": p.home_team, "away_team": p.away_team, **asdict(p.prediction)} for p in predictions
    ]


@app.get("/predict/laliga")
def predict_laliga(matchday: int | None = None) -> list[dict]:
    with FootballDataClient() as client:
        predictions = laliga_service.predict_matchday(client, matchday=matchday)
    return [
        {"home_team": p.home_team, "away_team": p.away_team, **asdict(p.prediction)} for p in predictions
    ]


def _squad_result_dict(result) -> dict:
    return {
        "squad": [asdict(p) for p in result.squad],
        "starters": [asdict(p) for p in result.starters],
        "bench": [asdict(p) for p in result.bench],
        "captain": asdict(result.captain),
        "vice_captain": asdict(result.vice_captain),
        "total_price": result.total_price,
        "starting_xp": result.starting_xp,
    }


@app.get("/recommend/fpl/build")
def recommend_fpl_build(event: int | None = None) -> dict:
    with FPLClient() as client:
        pool = fpl_service.build_candidate_pool(client, event=event)
    result = optimize_squad(pool)
    return _squad_result_dict(result)


@app.get("/fpl/teams")
def fpl_teams() -> list[dict]:
    with FPLClient() as client:
        bootstrap = client.bootstrap()
    return [{"id": t["id"], "name": t["name"]} for t in bootstrap["teams"]]


@app.get("/fpl/players")
def fpl_players() -> list[dict]:
    with FPLClient() as client:
        bootstrap = client.bootstrap()
    team_name_by_id = {t["id"]: t["name"] for t in bootstrap["teams"]}
    return [
        {
            "id": e["id"],
            "name": e["web_name"],
            "team": team_name_by_id[e["team"]],
            "pos": POSITION_BY_ELEMENT_TYPE[e["element_type"]],
        }
        for e in bootstrap["elements"]
    ]


@app.get("/recommend/fpl/team-builder")
def recommend_fpl_team_builder(
    event: int | None = None,
    favorite_team: str | None = None,
    favorite_players: str = "",
    min_favorite_team_count: int = 3,
) -> dict:
    names = [n.strip() for n in favorite_players.split(",") if n.strip()]
    with FPLClient() as client:
        result = fpl_service.build_team_builder(
            client,
            event=event,
            favorite_team=favorite_team or None,
            favorite_player_names=names,
            min_favorite_team_count=min_favorite_team_count,
        )
    out = _squad_result_dict(result.squad)
    out["injury_notes"] = {
        pid: note for pid, note in result.injury_notes.items() if pid in {p["id"] for p in out["squad"]}
    }
    out["shortlisted_count"] = result.shortlisted_count
    out["favorite_team"] = result.favorite_team
    out["favorite_players_matched"] = result.favorite_players_matched
    out["favorite_players_unmatched"] = result.favorite_players_unmatched
    return out


def _full_recommendation_dict(rec, unmatched_names: list[str] | None = None) -> dict:
    return {
        "risk_flags": [
            {
                "player": asdict(f.player),
                "status": f.status,
                "news": f.news,
                "suggested_replacement": asdict(f.suggested_replacement) if f.suggested_replacement else None,
            }
            for f in rec.risk_flags
        ],
        "captain": asdict(rec.captain),
        "vice_captain": asdict(rec.vice_captain),
        "starters": [asdict(p) for p in rec.starters],
        "bench": [asdict(p) for p in rec.bench],
        "lineup_changes": rec.lineup_changes,
        "best_transfer": (
            {
                "out": asdict(rec.best_transfer.player_out),
                "in": asdict(rec.best_transfer.player_in),
                "xp_gain": rec.best_transfer.xp_gain,
                "is_hit": rec.best_transfer.is_hit,
            }
            if rec.best_transfer
            else None
        ),
        "transfer_horizon_gameweeks": rec.transfer_horizon_gameweeks,
        "chip_lifts": [asdict(c) for c in rec.chip_lifts],
        "free_hit_squad": _squad_result_dict(rec.free_hit_squad),
        "wildcard_squad": _squad_result_dict(rec.wildcard_squad),
        "unmatched_names": unmatched_names or [],
    }


def _resolve_current_squad(client: FPLClient, pool: list, entry_id: int | None, players: str, bank: float):
    """Shared by /recommend/fpl/full and /fpl/overview: entry_id (post-deadline) or a
    comma-separated `players` string (pre-deadline) -> (current_squad, actual_starter_ids,
    bank, entry_dict_or_None, unmatched_names)."""
    if entry_id is not None:
        current_squad, actual_starter_ids = fpl_service.entry_squad_and_starters(client, entry_id, pool)
        entry = client.entry(entry_id)
        bank = entry.get("last_deadline_bank", 0) / 10.0
        return current_squad, actual_starter_ids, bank, entry, []

    names = [n.strip() for n in players.split(",") if n.strip()]
    current_squad, unmatched = fpl_service.match_player_names(names, pool)
    if len(current_squad) < 11:
        raise RuntimeError(
            f"Only matched {len(current_squad)} of {len(names)} names to real FPL players — "
            f"need at least 11 to pick a starting XI. "
            f"{'Unmatched: ' + ', '.join(unmatched) if unmatched else ''}"
        )
    return current_squad, None, bank, None, unmatched


@app.get("/recommend/fpl/full")
def recommend_fpl_full(
    entry_id: int | None = None,
    players: str = "",
    bank: float = 0.0,
    free_transfers: int = 1,
    event: int | None = None,
    transfer_horizon: int = fpl_service.DEFAULT_TRANSFER_HORIZON,
    wildcard_horizon: int = fpl_service.DEFAULT_WILDCARD_HORIZON,
) -> dict:
    """
    The main "what should I do" endpoint: risk flags on your current squad, optimal
    captain/vice/bench for this gameweek, the single best transfer (evaluated over
    `transfer_horizon` gameweeks, since it sticks around), and quantified lift for each chip
    (bench boost / triple captain / free hit / wildcard), each over its own proper horizon.
    Pass `entry_id` if this gameweek's deadline has passed (FPL 404s picks before that), or
    `players` (comma-separated names) to enter your current 15 manually otherwise.
    """
    with FPLClient() as client:
        pool = fpl_service.build_candidate_pool(client, event=event)
        current_squad, actual_starter_ids, bank, _entry, unmatched = _resolve_current_squad(
            client, pool, entry_id, players, bank
        )
        rec = fpl_service.full_recommendation(
            client,
            current_squad,
            pool,
            bank=bank,
            free_transfers=free_transfers,
            event=event,
            transfer_horizon=transfer_horizon,
            wildcard_horizon=wildcard_horizon,
            actual_starter_ids=actual_starter_ids,
        )
    return _full_recommendation_dict(rec, unmatched_names=unmatched)


@app.get("/recommend/fpl/targets")
def recommend_fpl_targets(
    budget: float,
    entry_id: int | None = None,
    players: str = "",
    bank: float = 0.0,
    event: int | None = None,
    horizon: int = fpl_service.DEFAULT_TARGET_HORIZON,
) -> dict:
    """
    Per-position best affordable transfer target (not already in your squad), ranked by
    predicted points summed over `horizon` gameweeks (default 5). Pass `budget` as the most
    you'd spend on a single incoming player (e.g. bank + an outgoing player's sale price) —
    this doesn't assume any particular player is leaving, it's a standalone "who's best in
    each position at this price" lookup.
    """
    with FPLClient() as client:
        pool_1gw = fpl_service.build_candidate_pool(client, event=event)
        current_squad, _starters, _bank, _entry, unmatched = _resolve_current_squad(
            client, pool_1gw, entry_id, players, bank
        )
        targets = fpl_service.build_transfer_targets(client, current_squad, budget, event=event, horizon=horizon)
    return {
        "horizon_gameweeks": horizon,
        "targets": {pos: (asdict(p) if p else None) for pos, p in targets.items()},
        "unmatched_names": unmatched,
    }


@app.get("/fpl/player/{element_id}/breakdown")
def fpl_player_breakdown(element_id: int, n: int = player_breakdown.RECENT_GAMEWEEKS) -> dict:
    """
    Gameweek-by-gameweek points breakdown for one player — the last `n` gameweeks this season
    (goals, assists, clean sheets, bonus, cards, etc.), falling back to previous-season
    gameweeks from the historical archive when this season doesn't have `n` played yet.
    Always a live fetch from FPL — nothing here is cached, so it's never stale.
    """
    with FPLClient() as client:
        result = player_breakdown.build_player_breakdown(client, element_id, n=n)
    return {"recent": [asdict(r) for r in result.recent], "note": result.note}


@app.get("/recommend/fpl/trade-for")
def recommend_fpl_trade_for(
    target: str,
    entry_id: int | None = None,
    players: str = "",
    bank: float = 0.0,
    free_transfers: int = 1,
    event: int | None = None,
    horizon: int = fpl_service.DEFAULT_TRADE_HORIZON,
) -> dict:
    """
    "I want THIS player" — the top-3 legal ways (no chip) to reshuffle your squad to afford
    and fit `target` in, ranked by projected points over `horizon` gameweeks net of any
    transfer hits. The first result is the recommended one.
    """
    with FPLClient() as client:
        pool_1gw = fpl_service.build_candidate_pool(client, event=event)
        current_squad, _starters, bank, _entry, unmatched = _resolve_current_squad(
            client, pool_1gw, entry_id, players, bank
        )
        combos = fpl_service.build_trade_combos(
            client, current_squad, target, bank=bank, free_transfers=free_transfers, event=event, horizon=horizon
        )
    return {
        "horizon_gameweeks": horizon,
        "combos": [
            {
                "players_out": [asdict(p) for p in c.players_out],
                "players_in": [asdict(p) for p in c.players_in],
                "hits": c.hits,
                "hit_cost": c.hit_cost,
                "xp_gain": c.xp_gain,
                "new_bank": c.new_bank,
                "recommended": i == 0,
            }
            for i, c in enumerate(combos)
        ],
        "unmatched_names": unmatched,
    }


@app.get("/fpl/overview")
def fpl_overview(
    entry_id: int | None = None,
    players: str = "",
    bank: float = 0.0,
    event: int | None = None,
) -> dict:
    """
    Quick-glance dashboard: season totals (entry_id mode only), the single best transfer at a
    one-gameweek horizon, top candidates with a recent-points sparkline, and a fixture-
    difficulty ticker for your captain's club. Deeper multi-horizon analysis (chips, the
    multi-gameweek best transfer) lives in /recommend/fpl/full instead.
    """
    with FPLClient() as client:
        pool = fpl_service.build_candidate_pool(client, event=event)
        current_squad, _starters, bank, entry, unmatched = _resolve_current_squad(
            client, pool, entry_id, players, bank
        ) if (entry_id is not None or players.strip()) else ([], None, bank, None, [])
        result = overview.build_overview(client, current_squad, pool, bank=bank, entry_totals=entry, event=event)

    return {
        "team_totals": asdict(result.team_totals) if result.team_totals else None,
        "recommended_move": (
            {
                "out": asdict(result.recommended_move.player_out),
                "in": asdict(result.recommended_move.player_in),
                "xp_gain": result.recommended_move.xp_gain,
                "is_hit": result.recommended_move.is_hit,
            }
            if result.recommended_move
            else None
        ),
        "top_players": [
            {"player": asdict(tp.player), "recent_points": tp.recent_points} for tp in result.top_players
        ],
        "fixture_run": [asdict(f) for f in result.fixture_run],
        "fixture_run_team": result.fixture_run_team,
        "unmatched_names": unmatched,
    }


@app.post("/recommend/laliga")
def recommend_laliga_endpoint(squad: ManualSquad) -> dict:
    with FootballDataClient() as client:
        squad_candidates, pool = laliga_service.build_squad_and_watchlist_pool(client, squad)
    rec = recommend_laliga(squad_candidates, pool)
    return {
        "captain": asdict(rec.captain),
        "transfer_flags": [
            {
                "out": asdict(f.player_out),
                "in": asdict(f.player_in),
                "xp_gain": f.xp_gain,
                "price_delta": f.price_delta,
            }
            for f in rec.transfer_flags
        ],
    }


# Registered last so it only catches paths none of the routes above matched (the browser UI).
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
