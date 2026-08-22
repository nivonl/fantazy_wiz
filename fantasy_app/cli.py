"""
Local-use CLI — the fast day-to-day entry point. Calls the same service functions as
api/main.py, just without the HTTP hop.

Usage:
  py -m fantasy_app.cli predict-fpl [--event N]
  py -m fantasy_app.cli predict-laliga [--matchday N]
  py -m fantasy_app.cli build-fpl-squad [--event N]
  py -m fantasy_app.cli recommend-fpl --entry-id 1234567 [--free-transfers N]
  py -m fantasy_app.cli recommend-fpl --players "Raya, Gabriel, Saka, ..." [--bank N]
  py -m fantasy_app.cli team-builder-fpl [--favorite-team Arsenal] [--favorite-players "Saka, Haaland"]
  py -m fantasy_app.cli recommend-laliga --squad path/to/squad.json
"""

from __future__ import annotations

from pathlib import Path

import click
from dotenv import load_dotenv

from fantasy_app.providers.cat9 import load_manual_squad
from fantasy_app.providers.fpl import FPLClient
from fantasy_app.providers.football_data import FootballDataClient
from fantasy_app.recommend.fpl import optimize_squad
from fantasy_app.recommend.laliga import recommend_laliga
from fantasy_app.services import fpl_service, laliga_service

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")


@click.group()
def cli() -> None:
    pass


@cli.command("predict-fpl")
@click.option("--event", type=int, default=None, help="Gameweek number; defaults to the current one.")
def predict_fpl(event: int | None) -> None:
    with FPLClient() as client:
        preds = fpl_service.predict_gameweek(client, event=event)
    for np_ in preds:
        p = np_.prediction
        click.echo(
            f"{np_.home_team} vs {np_.away_team}: "
            f"lam=({p.lam_home:.2f}, {p.lam_away:.2f})  "
            f"1X2=({p.p_home_win:.0%}, {p.p_draw:.0%}, {p.p_away_win:.0%})  "
            f"likely {p.most_likely_score[0]}-{p.most_likely_score[1]} ({p.most_likely_score_prob:.0%})  "
            f"CS=({p.p_home_clean_sheet:.0%}, {p.p_away_clean_sheet:.0%})  "
            f"BTTS={p.p_btts:.0%}  O2.5={p.p_over_2_5:.0%}"
        )


@cli.command("predict-laliga")
@click.option("--matchday", type=int, default=None)
def predict_laliga(matchday: int | None) -> None:
    with FootballDataClient() as client:
        preds = laliga_service.predict_matchday(client, matchday=matchday)
    for np_ in preds:
        p = np_.prediction
        click.echo(
            f"{np_.home_team} vs {np_.away_team}: "
            f"lam=({p.lam_home:.2f}, {p.lam_away:.2f})  "
            f"1X2=({p.p_home_win:.0%}, {p.p_draw:.0%}, {p.p_away_win:.0%})  "
            f"likely {p.most_likely_score[0]}-{p.most_likely_score[1]} ({p.most_likely_score_prob:.0%})  "
            f"CS=({p.p_home_clean_sheet:.0%}, {p.p_away_clean_sheet:.0%})  "
            f"BTTS={p.p_btts:.0%}  O2.5={p.p_over_2_5:.0%}"
        )


@cli.command("build-fpl-squad")
@click.option("--event", type=int, default=None)
def build_fpl_squad(event: int | None) -> None:
    with FPLClient() as client:
        pool = fpl_service.build_candidate_pool(client, event=event)
    result = optimize_squad(pool)
    click.echo(f"Squad total: {result.total_price}m  |  Starting XI xP: {result.starting_xp}")
    click.echo("\nStarting XI:")
    for p in sorted(result.starters, key=lambda p: p.xp, reverse=True):
        tag = " (C)" if p.id == result.captain.id else " (VC)" if p.id == result.vice_captain.id else ""
        click.echo(f"  {p.pos:<4}{p.name:<20}{p.team:<20}{p.price:>5.1f}m  xP={p.xp:.2f}{tag}")
    click.echo("\nBench (best-first):")
    for p in result.bench:
        click.echo(f"  {p.pos:<4}{p.name:<20}{p.team:<20}{p.price:>5.1f}m  xP={p.xp:.2f}")


@cli.command("recommend-fpl")
@click.option("--entry-id", type=int, default=None, help="Use this after the gameweek deadline (FPL won't expose picks before it).")
@click.option("--players", default=None, help="Comma-separated names of your current 15 — use this before the deadline.")
@click.option("--bank", type=float, default=0.0)
@click.option("--free-transfers", type=int, default=1)
@click.option("--event", type=int, default=None)
@click.option("--transfer-horizon", type=int, default=fpl_service.DEFAULT_TRANSFER_HORIZON)
@click.option("--wildcard-horizon", type=int, default=fpl_service.DEFAULT_WILDCARD_HORIZON)
def recommend_fpl(
    entry_id: int | None, players: str | None, bank: float, free_transfers: int, event: int | None,
    transfer_horizon: int, wildcard_horizon: int,
) -> None:
    """Risk flags, captain/bench, the best transfer (multi-gameweek horizon), and chip lifts.
    Pass exactly one of --entry-id or --players."""
    if (entry_id is None) == (players is None):
        raise click.UsageError("Pass exactly one of --entry-id or --players.")

    with FPLClient() as client:
        pool = fpl_service.build_candidate_pool(client, event=event)
        actual_starter_ids = None
        if entry_id is not None:
            current_squad, actual_starter_ids = fpl_service.entry_squad_and_starters(client, entry_id, pool)
            entry = client.entry(entry_id)
            bank = entry.get("last_deadline_bank", 0) / 10.0
        else:
            names = [n.strip() for n in players.split(",") if n.strip()]
            current_squad, unmatched = fpl_service.match_player_names(names, pool)
            if unmatched:
                click.echo(f"Couldn't match: {', '.join(unmatched)}")
            if len(current_squad) < 11:
                raise click.ClickException(f"Only matched {len(current_squad)} of {len(names)} names — need at least 11.")
        rec = fpl_service.full_recommendation(
            client, current_squad, pool, bank=bank, free_transfers=free_transfers, event=event,
            transfer_horizon=transfer_horizon, wildcard_horizon=wildcard_horizon,
            actual_starter_ids=actual_starter_ids,
        )

    if rec.risk_flags:
        click.echo("Risk flags (check before deadline):")
        for f in rec.risk_flags:
            repl = f" -> consider {f.suggested_replacement.name}" if f.suggested_replacement else ""
            click.echo(f"  {f.player.name} [{f.status}] {f.news}{repl}")

    click.echo(f"\nCaptain: {rec.captain.name}  |  Vice: {rec.vice_captain.name}")
    for change in rec.lineup_changes:
        click.echo(f"  * {change}")

    click.echo(f"\nBest transfer (next {rec.transfer_horizon_gameweeks} GWs):")
    if rec.best_transfer is None:
        click.echo("  None worth making.")
    else:
        t = rec.best_transfer
        hit = " (HIT -4)" if t.is_hit else ""
        click.echo(f"  OUT {t.player_out.name:<20} -> IN {t.player_in.name:<20} xP+{t.xp_gain:.2f}{hit}")

    click.echo("\nChip lifts:")
    for c in rec.chip_lifts:
        click.echo(f"  {c.chip:<15} (next {c.horizon_gameweeks} GW{'s' if c.horizon_gameweeks > 1 else ''}): {c.lift:+.2f} — {c.note}")


@cli.command("team-builder-fpl")
@click.option("--event", type=int, default=None)
@click.option("--favorite-team", default=None, help="Require at least N players from this club.")
@click.option("--min-favorite-team-count", type=int, default=3)
@click.option("--favorite-players", default="", help="Comma-separated player names to force into the squad.")
def team_builder_fpl(
    event: int | None, favorite_team: str | None, min_favorite_team_count: int, favorite_players: str
) -> None:
    names = [n.strip() for n in favorite_players.split(",") if n.strip()]
    with FPLClient() as client:
        result = fpl_service.build_team_builder(
            client,
            event=event,
            favorite_team=favorite_team,
            favorite_player_names=names,
            min_favorite_team_count=min_favorite_team_count,
        )
    r = result.squad
    click.echo(f"Shortlisted {result.shortlisted_count} candidates (base xP + favorites) before optimizing.")
    if result.favorite_players_unmatched:
        click.echo(f"Couldn't match: {', '.join(result.favorite_players_unmatched)}")
    click.echo(f"Squad total: {r.total_price}m  |  Starting XI xP: {r.starting_xp}\n")
    for p in sorted(r.starters, key=lambda p: p.xp, reverse=True):
        tag = " (C)" if p.id == r.captain.id else " (VC)" if p.id == r.vice_captain.id else ""
        note = result.injury_notes.get(p.id)
        flag = f"  [{note['status']}: {note['news']}]" if note else ""
        click.echo(f"  {p.pos:<4}{p.name:<20}{p.team:<20}{p.price:>5.1f}m  xP={p.xp:.2f}{tag}{flag}")
    click.echo("\nBench:")
    for p in r.bench:
        note = result.injury_notes.get(p.id)
        flag = f"  [{note['status']}: {note['news']}]" if note else ""
        click.echo(f"  {p.pos:<4}{p.name:<20}{p.team:<20}{p.price:>5.1f}m  xP={p.xp:.2f}{flag}")


@cli.command("recommend-laliga")
@click.option("--squad", "squad_path", type=click.Path(exists=True), required=True)
def recommend_laliga_cmd(squad_path: str) -> None:
    manual_squad = load_manual_squad(squad_path)
    with FootballDataClient() as client:
        squad_candidates, pool = laliga_service.build_squad_and_watchlist_pool(client, manual_squad)
    rec = recommend_laliga(squad_candidates, pool)

    click.echo(f"Captain: {rec.captain.name} (xP={rec.captain.xp:.2f})")
    if not rec.transfer_flags:
        click.echo("No transfer flagged.")
    for f in rec.transfer_flags:
        click.echo(
            f"  Consider OUT {f.player_out.name:<20} -> IN {f.player_in.name:<20} "
            f"xP+{f.xp_gain:.2f}  price {f.price_delta:+.1f}"
        )


if __name__ == "__main__":
    cli()
