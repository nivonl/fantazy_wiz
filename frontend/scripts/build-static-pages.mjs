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
import { renderPointsBarChart, renderPriceLineChart } from "./lib/chart.mjs";
import { renderRadarChart, formatCategoryDetail } from "../src/charts/radarChart.js";
import { teamColor } from "../src/team-colors.js";

// A player's own page gets a subtle background wash of their club's color (see
// team-colors.js) -- deliberately not a dot scattered on every team mention across every
// table/listing, just this one accent on the page that's actually about that one player.
function hexToRgb(hex) {
  const m = /^#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex);
  return m ? [parseInt(m[1], 16), parseInt(m[2], 16), parseInt(m[3], 16)] : [138, 127, 153];
}

function teamAccentStyle(teamName) {
  const [r, g, b] = hexToRgb(teamColor(teamName));
  return `background: linear-gradient(160deg, rgba(${r},${g},${b},0.28), var(--panel) 60%, var(--panel-2));`;
}

const __dirname = dirname(fileURLToPath(import.meta.url));
const FRONTEND_DIR = join(__dirname, "..");
const DIST_DIR = join(FRONTEND_DIR, "dist");
const GAMEWEEKS_DIR = join(FRONTEND_DIR, "data", "gameweeks");
const BLOG_POSTS_PATH = join(FRONTEND_DIR, "data", "blog", "posts.json");
const BREAKDOWN_CONCURRENCY = 6;

const POS_LABEL = { GK: "Goalkeepers", DEF: "Defenders", MID: "Midfielders", FWD: "Forwards" };
const POS_ORDER = ["GK", "DEF", "MID", "FWD"];
const RADAR_WINDOW_LABELS = { last3: "Last 3 GWs", previous_season: "Previous Season", career: "Career" };
const RADAR_WINDOW_ORDER = ["last3", "previous_season", "career"];

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
  const hasPrice = rows.some((r) => r.price != null);
  const extraCols = hasDetail ? "<th>G</th><th>A</th><th>CS</th><th>Bns</th>" : "";
  const priceCol = hasPrice ? "<th>Price</th>" : "";
  return `<div class="table-wrap"><table><thead><tr><th>Season</th><th>GW</th><th>Opponent</th><th>Min</th>${priceCol}${extraCols}<th>Pts</th></tr></thead><tbody>
${rows
  .map((r) => {
    const opp = r.opponent ? (r.was_home ? escapeHtml(r.opponent) : `@ ${escapeHtml(r.opponent)}`) : "&mdash;";
    const price = hasPrice ? `<td>${r.price != null ? `${r.price.toFixed(1)}m` : "&mdash;"}</td>` : "";
    const extra = hasDetail
      ? `<td>${r.goals_scored ?? "&mdash;"}</td><td>${r.assists ?? "&mdash;"}</td><td>${r.clean_sheets ?? "&mdash;"}</td><td>${r.bonus ?? "&mdash;"}</td>`
      : "";
    return `<tr><td>${r.season}</td><td>${r.gameweek}</td><td>${opp}</td><td>${r.minutes}</td>${price}${extra}<td><b>${r.total_points}</b></td></tr>`;
  })
  .join("\n")}
</tbody></table></div>`;
}

// One radar chart per window that actually has data, each showing the "vs all players" and "vs
// position" polygons together (see radarChart.js) -- a goalkeeper's `all` series is always null
// (services/player_radar.py), which renderRadarChart already handles by drawing only the
// position polygon and its own legend entry.
function renderRadarSection(radar, pos) {
  if (!radar?.categoryLabels) return "";
  const keys = Object.keys(radar.categoryLabels);
  const labels = keys.map((k) => radar.categoryLabels[k]);
  const posLabel = `vs ${POS_LABEL[pos] || pos}`;

  const charts = RADAR_WINDOW_ORDER.map((window) => {
    const entry = radar[window];
    if (!entry) return "";
    const allSeries = entry.all ? keys.map((k) => entry.all[k] ?? null) : null;
    const positionSeries = entry.position ? keys.map((k) => entry.position[k] ?? null) : null;
    const categoryDetails = keys.map((k) => formatCategoryDetail(radar.categoryFields?.[k], entry.stats));
    const svg = renderRadarChart(labels, allSeries, positionSeries, {
      labelAll: "vs all players",
      labelPosition: posLabel,
      categoryDetails,
    });
    return svg ? `<figure class="radar-chart"><figcaption>${RADAR_WINDOW_LABELS[window]}</figcaption>${svg}</figure>` : "";
  }).join("");

  return charts ? `<h3>Stat radar</h3><div class="radar-row">${charts}</div>` : "";
}

function renderPlayerBody(player, breakdown, priceHistory, radar) {
  const stats = player.opponent_stats;
  const priceChart = priceHistory?.length ? renderPriceLineChart(priceHistory) : "";
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
    ${breakdown?.recent?.length ? renderPointsBarChart(breakdown.recent) : ""}
    ${renderBreakdownTable(breakdown?.recent ?? [])}
    ${
      priceChart
        ? `<h3>Fantasy price history</h3>
    ${priceChart}`
        : ""
    }
    ${renderRadarSection(radar, player.pos)}
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

// --- Blog ---
// Committed data (frontend/data/blog/posts.json), never re-derived at build time — same
// precedent as the committed gameweek snapshots above: the underlying "actual vs predicted"
// numbers were computed once, offline, against a real gameweek that's already in the past, so
// there's nothing to re-fetch from a live API on every build.

const POS_LABEL_LONG = { GK: "Goalkeeper", DEF: "Defender", MID: "Midfielder", FWD: "Forward" };

function fmtSigned(n) {
  const r = Math.round(n * 100) / 100;
  return `${r >= 0 ? "+" : ""}${r.toFixed(2)}`;
}

function rarityLabel(percentile) {
  if (percentile >= 99.5) return "Rarest of the gameweek";
  if (percentile >= 97) return "Top 1-in-40 surprise";
  if (percentile >= 90) return "Top-decile surprise";
  return "Notable surprise";
}

function renderBlogPlayerCard(p, slugById) {
  // No free-licensed photo on Commons for every player yet -- rather than a blank circle or
  // a "no photo" caption drawing attention to the gap, the fallback is the same brand mark
  // used in the site header (App.jsx's BrandMark / render-page.mjs's inline <svg>), so the
  // circle still reads as a deliberate PitchMetric placeholder, not a missing asset.
  const photoBlock = p.photo
    ? `<img class="blog-player-photo" src="/blog/players/${p.photo}" alt="${escapeHtml(p.name)}" loading="lazy" width="96" height="96" />
       <p class="blog-photo-credit">Photo: ${escapeHtml(p.photo_credit.name)}, <a href="${p.photo_credit.license_url}">${escapeHtml(p.photo_credit.license)}</a>, via <a href="${p.photo_credit.source_url}">Wikimedia Commons</a></p>`
    : `<div class="blog-player-photo-placeholder" role="img" aria-label="${escapeHtml(p.name)} — no photo available">
         <svg width="34" height="34" viewBox="0 0 24 24" fill="none">
           <circle cx="10" cy="10" r="6.5" stroke="#04F5FF" stroke-width="2" />
           <line x1="14.8" y1="14.8" x2="20" y2="20" stroke="#963CFF" stroke-width="2.2" stroke-linecap="round" />
         </svg>
       </div>`;

  const fixtureLine = `${p.was_home ? "vs" : "@"} ${escapeHtml(p.opponent)}`;
  const boxscoreParts = [];
  if (p.goals) boxscoreParts.push(`${p.goals} goal${p.goals > 1 ? "s" : ""}`);
  if (p.assists) boxscoreParts.push(`${p.assists} assist${p.assists > 1 ? "s" : ""}`);
  if (p.clean_sheets) boxscoreParts.push("clean sheet");
  if (p.bonus) boxscoreParts.push(`${p.bonus} bonus`);

  // Links out to the player's real static profile page when the id is still in the current
  // predicted-players pool (it won't be for someone who's since left the league, been sent out
  // on loan, etc.) -- falls back to plain text rather than a broken link.
  const slug = p.element_id != null ? slugById.get(String(p.element_id)) : undefined;
  const nameHtml = slug ? `<a href="/fpl/player/${slug}">${escapeHtml(p.name)}</a>` : escapeHtml(p.name);

  return `
    <div class="blog-player-card">
      <div class="blog-player-photo-wrap">${photoBlock}</div>
      <div class="blog-player-body">
        <div class="blog-player-name-row">
          <span class="blog-player-rank">#${p.rank}</span>
          <span class="blog-player-name">${nameHtml}</span>
          <span class="blog-rarity-tag">${rarityLabel(p.percentile)}</span>
        </div>
        <p class="blog-player-meta">${POS_LABEL_LONG[p.position] || p.position} &middot; ${escapeHtml(p.team)} &middot; ${p.value.toFixed(1)}m &middot; ${fixtureLine} &middot; ${p.minutes}&prime;</p>
        <div class="blog-stat-row">
          <div><div class="blog-stat-label">Predicted</div><div class="blog-stat-value">${p.predicted_xp.toFixed(2)}</div></div>
          <div><div class="blog-stat-label">Actual</div><div class="blog-stat-value">${p.actual_points}</div></div>
          <div><div class="blog-stat-label">Surprise</div><div class="blog-stat-value" style="color:var(--good)">${fmtSigned(p.surprise)}</div></div>
          <div><div class="blog-stat-label">Percentile</div><div class="blog-stat-value">${p.percentile.toFixed(1)}</div></div>
        </div>
        <p class="blog-boxscore"><b>Box score:</b> ${boxscoreParts.length ? escapeHtml(boxscoreParts.join(", ")) : "&mdash;"} &middot; xG ${p.expected_goals.toFixed(2)}, xA ${p.expected_assists.toFixed(2)} &middot; ICT ${p.ict_index.toFixed(1)}</p>
        <p class="blog-player-analysis">${p.analysis}</p>
      </div>
    </div>`;
}

function renderBlogPostBody(post, slugById) {
  const dateLabel = new Date(post.published + "T00:00:00Z").toLocaleDateString("en-GB", {
    year: "numeric", month: "long", day: "numeric", timeZone: "UTC",
  });
  return `
    <p class="blog-post-meta">Gameweek ${post.gameweek} &middot; ${dateLabel}</p>
    <h2>${escapeHtml(post.title)}</h2>
    <p class="blog-dek">${escapeHtml(post.dek)}</p>
    <p class="summary-line">${post.intro}</p>
    <p class="hint">Ranked among ${post.qualifying_player_count} players who played at least ${post.min_minutes} minutes in gameweek ${post.gameweek}, by actual points minus predicted xP. Average surprise across that pool: ${fmtSigned(post.mean_surprise)} (std. dev. ${post.stdev_surprise.toFixed(2)}).</p>
    ${post.players.map((p) => renderBlogPlayerCard(p, slugById)).join("\n")}
    <p class="summary-line">${post.closing}</p>
    ${post.model_notes ? `<div class="blog-callout"><p class="blog-callout-heading">Where the model should improve</p>${post.model_notes}</div>` : ""}
    <p><a href="/blog">&larr; All posts</a> &middot; <a href="/methodology">How predictions work</a></p>
  `;
}

function renderBlogIndexBody(posts) {
  return `
    <h2>PitchMetric Blog</h2>
    <p class="summary-line">Every gameweek, the five biggest gaps between what PitchMetric predicted and what actually happened — for players who played at least 30 minutes — with the underlying stats (xG, xA, ICT and more) behind each one, and how rare a surprise of that size really was.</p>
    <div class="blog-index-grid">
      ${posts
        .map(
          (post) => `
      <a class="blog-index-card" href="/blog/${post.slug}">
        <p class="blog-index-meta">Gameweek ${post.gameweek}</p>
        <h3>${escapeHtml(post.title)}</h3>
        <p>${escapeHtml(post.dek)}</p>
      </a>`
        )
        .join("\n")}
    </div>
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

  console.log("Fetching per-player price histories...");
  const priceHistoryResults = await mapWithConcurrency(players, BREAKDOWN_CONCURRENCY, (p) => fetchJson(`/fpl/player/${p.id}/price-history`));
  const priceHistoryById = new Map();
  let priceHistoryFailures = 0;
  for (const { item, result, error } of priceHistoryResults) {
    if (error) {
      priceHistoryFailures++;
      continue; // degrade gracefully -- the page just omits the price chart
    }
    priceHistoryById.set(item.id, result);
  }
  if (priceHistoryFailures > 0) console.log(`${priceHistoryFailures} player price-history fetch(es) failed -- those pages omit the price chart.`);

  console.log("Fetching player stat-radar table...");
  let radarTable = {};
  try {
    radarTable = await fetchJson("/fpl/players/radar", { timeoutMs: 60000 });
  } catch (err) {
    console.log(`Radar table fetch failed (${err.message}) -- pages will omit the stat radar section.`);
  }

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
      bodyHtml: renderPlayerBody(player, breakdownById.get(player.id), priceHistoryById.get(player.id), radarTable[player.id]),
      cardStyle: teamAccentStyle(player.team),
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

  // Small id -> slug lookup the SPA fetches once, so the interactive player popup (which only
  // knows a numeric player id) can link out to that player's real static page without trying
  // to re-derive the slug client-side (which would need the whole player list anyway, just to
  // detect the same rare name collisions the generator already resolved here).
  const slugManifestPath = join(DIST_DIR, "fpl", "players", "slugs.json");
  writeFileSync(slugManifestPath, JSON.stringify(Object.fromEntries(slugById)), "utf-8");

  // Same "publish a small manifest, fetch it once client-side" precedent as slugs.json above --
  // lets the SPA's player popup render the exact same radar charts without the browser ever
  // hitting the (comparatively heavy, ~650-player) live /fpl/players/radar endpoint itself.
  const radarManifestPath = join(DIST_DIR, "fpl", "players", "radar.json");
  writeFileSync(radarManifestPath, JSON.stringify(radarTable), "utf-8");

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

  // --- Blog: committed posts, rendered as real static pages (same pattern as gameweek
  // snapshots above -- read from disk, never re-derived at build time). ---
  if (existsSync(BLOG_POSTS_PATH)) {
    const posts = JSON.parse(readFileSync(BLOG_POSTS_PATH, "utf-8"));
    console.log(`Found ${posts.length} committed blog post(s).`);

    const blogIndexHtml = renderPage({
      title: "Blog — Fantasy Gameweek Surprises",
      description: "Every gameweek's five biggest gaps between predicted and actual fantasy points, with the underlying stats behind each surprise.",
      path: "/blog",
      cssHref,
      breadcrumbs: [
        { name: "Home", path: "/" },
        { name: "Blog", path: "/blog" },
      ],
      bodyHtml: renderBlogIndexBody(posts),
    });
    generatedPaths.push(writePage("/blog", blogIndexHtml));

    for (const post of posts) {
      const path = `/blog/${post.slug}`;
      const html = renderPage({
        title: post.title,
        description: post.dek,
        path,
        cssHref,
        ogType: "article",
        breadcrumbs: [
          { name: "Home", path: "/" },
          { name: "Blog", path: "/blog" },
          { name: post.title, path },
        ],
        extraJsonLd: [
          {
            "@context": "https://schema.org",
            "@type": "BlogPosting",
            headline: post.title,
            description: post.dek,
            datePublished: post.published,
            url: `${SITE_URL}${path}`,
            author: { "@type": "Organization", name: "PitchMetric" },
          },
        ],
        bodyHtml: renderBlogPostBody(post, slugById),
      });
      generatedPaths.push(writePage(path, html));
    }
  } else {
    console.log("No committed blog posts found at data/blog/posts.json -- skipping /blog.");
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
