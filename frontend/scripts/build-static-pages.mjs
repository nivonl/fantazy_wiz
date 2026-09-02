// Post-build static-page generator: run via `npm run build` (vite build && node
// scripts/build-static-pages.mjs). Writes real, self-contained HTML files directly into
// dist/ for the pages that actually drive organic search -- per-player pages and per-
// gameweek prediction pages -- plus dist/sitemap.xml and dist/robots.txt. No JS/hydration
// needed to see any of this content.
//
// SPA tool routes (/, /fpl-team-analyzer, etc.) are never written here -- Vite's own build
// only emits dist/index.html + dist/assets/*, so there's no real collision risk today, but
// every write below still checks the target path is free first and fails loudly if not,
// rather than silently letting Netlify's "real file wins" precedence pick a winner.

import { existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { warmUpBackend, fetchJson, mapWithConcurrency } from "./lib/fetch-api.mjs";
import { buildSlugMap } from "./lib/slugify.mjs";
import { renderPage, SITE_URL } from "./lib/render-page.mjs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const FRONTEND_DIR = join(__dirname, "..");
const DIST_DIR = join(FRONTEND_DIR, "dist");
const GAMEWEEKS_DIR = join(FRONTEND_DIR, "data", "gameweeks");
const BREAKDOWN_CONCURRENCY = 6;

const POS_LABEL = { GK: "Goalkeepers", DEF: "Defenders", MID: "Midfielders", FWD: "Forwards" };
const POS_ORDER = ["GK", "DEF", "MID", "FWD"];

function escapeHtml(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function getCssHref() {
  const indexHtml = readFileSync(join(DIST_DIR, "index.html"), "utf-8");
  const match = indexHtml.match(/<link rel="stylesheet"[^>]*href="([^"]+)"/);
  if (!match) throw new Error("Could not find the built CSS href in dist/index.html");
  return match[1];
}

function writePage(relativePath, html) {
  const outPath = join(DIST_DIR, relativePath, "index.html");
  if (existsSync(outPath)) {
    throw new Error(`Refusing to overwrite an existing file at dist${relativePath}/index.html -- a route collision?`);
  }
  mkdirSync(dirname(outPath), { recursive: true });
  writeFileSync(outPath, html, "utf-8");
  return `${relativePath}/`;
}

function renderPlayerTable(players) {
  return `<div class="table-wrap"><table><thead><tr><th>Player</th><th>Team</th><th>Pos</th><th>Price</th><th>Predicted pts</th></tr></thead><tbody>
${players
  .map(
    (p) =>
      `<tr><td>${escapeHtml(p.name)}</td><td>${escapeHtml(p.team)}</td><td>${p.pos}</td><td>${p.price.toFixed(1)}m</td><td>${p.xp.toFixed(2)}</td></tr>`
  )
  .join("\n")}
</tbody></table></div>`;
}

function renderBreakdownTable(rows) {
  if (!rows.length) return `<p class="empty">No gameweek history available yet.</p>`;
  const hasDetail = rows.some((r) => r.clean_sheets !== null || r.bonus !== null);
  const extraCols = hasDetail ? "<th>G</th><th>A</th><th>CS</th><th>Bns</th>" : "";
  return `<div class="table-wrap"><table><thead><tr><th>Season</th><th>GW</th><th>Opponent</th><th>Min</th>${extraCols}<th>Pts</th></tr></thead><tbody>
${rows
  .map((r) => {
    const opp = r.opponent ? (r.was_home ? escapeHtml(r.opponent) : `@ ${escapeHtml(r.opponent)}`) : "&mdash;";
    const extra = hasDetail
      ? `<td>${r.goals_scored ?? "&mdash;"}</td><td>${r.assists ?? "&mdash;"}</td><td>${r.clean_sheets ?? "&mdash;"}</td><td>${r.bonus ?? "&mdash;"}</td>`
      : "";
    return `<tr><td>${r.season}</td><td>${r.gameweek}</td><td>${opp}</td><td>${r.minutes}</td>${extra}<td><b>${r.total_points}</b></td></tr>`;
  })
  .join("\n")}
</tbody></table></div>`;
}

function renderPlayerBody(player, breakdown) {
  const stats = player.opponent_stats;
  return `
    <h2>${escapeHtml(player.name)} — FPL Price, Predicted Points &amp; Fixtures</h2>
    <p class="summary-line">${player.pos} &middot; ${escapeHtml(player.team)} &middot; ${player.price.toFixed(1)}m</p>
    <p class="summary-line">Predicted <b>${player.xp.toFixed(2)}</b> points this gameweek${stats ? ` vs ${escapeHtml(stats.opponent)}` : ""}.</p>
    ${
      stats && stats.games_overall > 0
        ? `<p>Over the last 5 Premier League seasons vs this opponent: ${stats.games_overall} apps, avg ${stats.avg_points_overall} pts, ${stats.goals_overall}G/${stats.assists_overall}A.</p>`
        : ""
    }
    <h3>Recent gameweeks</h3>
    ${breakdown?.note ? `<p class="hint">${escapeHtml(breakdown.note)}</p>` : ""}
    ${renderBreakdownTable(breakdown?.recent ?? [])}
    <p class="hint">Predicted points are from a statistical model (Poisson-fit team ratings + the official FPL scoring
    table) -- see the <a href="/methodology">methodology</a> for exactly how. Want to trade for
    ${escapeHtml(player.name)}? Try the <a href="/fpl-transfer-finder">Transfer Finder</a>.</p>
    <p><a href="/fpl/players">&larr; All players</a></p>
  `;
}

function renderPlayersIndexBody(players, slugById) {
  const byPos = Object.fromEntries(POS_ORDER.map((pos) => [pos, players.filter((p) => p.pos === pos).sort((a, b) => b.xp - a.xp)]));
  return `
    <h2>FPL Players — Predicted Points &amp; Prices</h2>
    <p>Every Premier League player with a fixture this gameweek, with PitchMetric's predicted points. See a player's
    recent gameweek-by-gameweek breakdown by clicking through.</p>
    ${POS_ORDER.map(
      (pos) => `
    <h3>${POS_LABEL[pos]}</h3>
    <ul>${byPos[pos]
      .map(
        (p) =>
          `<li><a href="/fpl/player/${slugById.get(p.id)}">${escapeHtml(p.name)}</a> &mdash; ${escapeHtml(p.team)}, ${p.price.toFixed(1)}m, predicted ${p.xp.toFixed(2)} pts</li>`
      )
      .join("")}</ul>`
    ).join("\n")}
  `;
}

function renderGameweekBody(event, players, { isCurrent }) {
  const byPos = Object.fromEntries(POS_ORDER.map((pos) => [pos, players.filter((p) => p.pos === pos).sort((a, b) => b.xp - a.xp)]));
  const top10 = [...players].sort((a, b) => b.xp - a.xp).slice(0, 10);
  return `
    <h2>Best Predicted FPL Players — Gameweek ${event}</h2>
    <p>PitchMetric's predicted points for every Premier League player with a fixture in gameweek ${event}${
    isCurrent ? "" : " (a historical record -- this reflects what was predicted before that gameweek was played, not a re-run with hindsight)"
  }, from a Poisson attack/defense model fit on real results. See the <a href="/methodology">methodology</a> for how these are calculated.</p>
    <h3>Top 10 overall</h3>
    ${renderPlayerTable(top10)}
    ${POS_ORDER.map((pos) => `<h3>Best ${POS_LABEL[pos]}</h3>${renderPlayerTable(byPos[pos].slice(0, 10))}`).join("\n")}
    <p><a href="/fpl-predictions">&larr; Current gameweek</a> &middot; <a href="/fpl/players">All players</a></p>
  `;
}

async function main() {
  console.log(`Generating static pages against ${process.env.VITE_API_BASE_URL || "(default backend URL)"}...`);
  await warmUpBackend();
  const cssHref = getCssHref();

  const generatedPaths = [];

  // --- Players ---
  const { event: currentEvent, players } = await fetchJson("/fpl/players/predicted");
  const slugById = buildSlugMap(players);
  console.log(`Fetched ${players.length} players for gameweek ${currentEvent}. Fetching per-player breakdowns...`);

  const breakdownResults = await mapWithConcurrency(players, BREAKDOWN_CONCURRENCY, (p) => fetchJson(`/fpl/player/${p.id}/breakdown`));
  const breakdownById = new Map();
  let breakdownFailures = 0;
  for (const { item, result, error } of breakdownResults) {
    if (error) {
      breakdownFailures++;
      continue; // degrade gracefully -- the page just renders without the recent-form table
    }
    breakdownById.set(item.id, result);
  }
  if (breakdownFailures > 0) console.log(`${breakdownFailures} player breakdown(s) failed to fetch -- those pages omit that section.`);

  for (const player of players) {
    const slug = slugById.get(player.id);
    const path = `/fpl/player/${slug}`;
    const html = renderPage({
      title: `${player.name} FPL Prediction, Price & Expected Points`,
      description: `${player.name} (${player.team}, ${player.pos}): FPL price ${player.price.toFixed(1)}m, predicted ${player.xp.toFixed(2)} points this gameweek, and recent gameweek-by-gameweek form.`,
      path,
      cssHref,
      breadcrumbs: [
        { name: "Home", path: "/" },
        { name: "Players", path: "/fpl/players" },
        { name: player.name, path },
      ],
      bodyHtml: renderPlayerBody(player, breakdownById.get(player.id)),
    });
    generatedPaths.push(writePage(path, html));
  }

  const playersIndexHtml = renderPage({
    title: "FPL Players — Predicted Points & Prices",
    description: "Every Premier League player with PitchMetric's predicted points for the current gameweek, browsable by position.",
    path: "/fpl/players",
    cssHref,
    breadcrumbs: [
      { name: "Home", path: "/" },
      { name: "Players", path: "/fpl/players" },
    ],
    bodyHtml: renderPlayersIndexBody(players, slugById),
  });
  generatedPaths.push(writePage("/fpl/players", playersIndexHtml));

  // --- Gameweek pages: committed history (never re-derived) + the live current one ---
  let pastGameweeks = [];
  if (existsSync(GAMEWEEKS_DIR)) {
    pastGameweeks = readdirSync(GAMEWEEKS_DIR)
      .filter((f) => f.endsWith(".json"))
      .map((f) => JSON.parse(readFileSync(join(GAMEWEEKS_DIR, f), "utf-8")))
      // The current gameweek may already have a same-day snapshot (captured early in its own
      // cycle, per the daily Action) -- the live fetch above always wins for "today's" page,
      // a committed snapshot is only meaningful once a gameweek is genuinely in the past.
      .filter((snap) => snap.event !== currentEvent);
  }
  console.log(`Found ${pastGameweeks.length} committed past-gameweek snapshot(s) (excluding the current one).`);

  const gameweekDatasets = [
    ...pastGameweeks.map((snap) => ({ event: snap.event, players: snap.players, isCurrent: false })),
    { event: currentEvent, players, isCurrent: true },
  ];

  for (const gw of gameweekDatasets) {
    const path = `/fpl-predictions/gameweek-${gw.event}`;
    const html = renderPage({
      title: `Best FPL Players & Predictions for Gameweek ${gw.event}`,
      description: `PitchMetric's predicted points for gameweek ${gw.event}: top goalkeepers, defenders, midfielders and forwards, from a Poisson model fit on real Premier League results.`,
      path,
      cssHref,
      breadcrumbs: [
        { name: "Home", path: "/" },
        { name: "Predictions", path: "/fpl-predictions" },
        { name: `Gameweek ${gw.event}`, path },
      ],
      bodyHtml: renderGameweekBody(gw.event, gw.players, { isCurrent: gw.isCurrent }),
    });
    generatedPaths.push(writePage(path, html));
  }

  // --- sitemap.xml + robots.txt ---
  const staticRoutes = ["/", "/fpl-team-analyzer", "/fpl-transfer-finder", "/fpl-squad-builder", "/fpl-predictions", "/methodology"];
  const allUrls = [...staticRoutes, ...generatedPaths.map((p) => `/${p}`.replace(/\/+/g, "/"))];
  const sitemap = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${allUrls.map((u) => `  <url><loc>${SITE_URL}${u}</loc></url>`).join("\n")}
</urlset>
`;
  writeFileSync(join(DIST_DIR, "sitemap.xml"), sitemap, "utf-8");

  const robots = `User-agent: *
Allow: /

Sitemap: ${SITE_URL}/sitemap.xml
`;
  writeFileSync(join(DIST_DIR, "robots.txt"), robots, "utf-8");

  console.log(`Done. Generated ${generatedPaths.length} static pages, sitemap.xml, and robots.txt.`);
}

main().catch((err) => {
  console.error("Static page generation failed:", err);
  process.exit(1);
});
