// Vanilla JS, no build step — talks to the same-origin JSON API defined in api/main.py.

function $(id) { return document.getElementById(id); }

function showTab(name) {
  document.querySelectorAll("nav.tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  document.querySelectorAll("section.panel").forEach((s) => s.classList.toggle("active", s.id === `panel-${name}`));
}

async function apiGet(path) {
  const res = await fetch(path);
  const body = await res.json();
  if (!res.ok) throw new Error(body.detail || `Request failed (${res.status})`);
  return body;
}

async function apiPost(path, payload) {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const body = await res.json();
  if (!res.ok) throw new Error(body.detail ? JSON.stringify(body.detail) : `Request failed (${res.status})`);
  return body;
}

function setLoading(container) {
  container.innerHTML = `<p class="loading">Loading…</p>`;
}

function setError(container, err) {
  container.innerHTML = `<div class="error">${err.message || err}</div>`;
}

function pct(x) { return `${(x * 100).toFixed(0)}%`; }

// Neon-green-for-gain / red-for-loss on any signed xP number — small but consistent touch.
function signedValue(x, decimals = 2) {
  const cls = x >= 0 ? "value-positive" : "value-negative";
  const sign = x >= 0 ? "+" : "";
  return `<span class="${cls}">${sign}${x.toFixed(decimals)}</span>`;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// Wraps a player's name with a hover/focus tooltip showing their history (last 5 PL seasons)
// against this week's opponent, when the API included opponent_stats for them.
function playerTipHtml(p) {
  const name = escapeHtml(p.name);
  const os = p.opponent_stats;
  if (!os) return name;
  let body;
  if (os.games_overall === 0) {
    body = `No PL history vs ${escapeHtml(os.opponent)} in the last 5 seasons.`;
  } else {
    const overall = `Overall: ${os.games_overall} apps, avg ${os.avg_points_overall} pts, ${os.goals_overall}G/${os.assists_overall}A`;
    const current = os.games_current_team
      ? `At current club: ${os.games_current_team} apps, avg ${os.avg_points_current_team} pts`
      : `No appearances vs ${escapeHtml(os.opponent)} yet at their current club.`;
    body = `vs ${escapeHtml(os.opponent)} — last 5 PL seasons<br>${overall}<br>${current}`;
  }
  return `<span class="tip-wrap" tabindex="0">${name}<span class="tip-bubble">${body}</span></span>`;
}

// ---- Score predictions (shared shape for both leagues) ----

function renderPredictions(container, predictions) {
  if (!predictions.length) {
    container.innerHTML = `<p class="empty">No fixtures found.</p>`;
    return;
  }
  const rows = predictions
    .map(
      (p) => `<tr>
        <td>${p.home_team}</td><td>${p.away_team}</td>
        <td>${p.lam_home.toFixed(2)} – ${p.lam_away.toFixed(2)}</td>
        <td>${p.most_likely_score[0]}-${p.most_likely_score[1]} (${pct(p.most_likely_score_prob)})</td>
        <td>${pct(p.p_home_win)} / ${pct(p.p_draw)} / ${pct(p.p_away_win)}</td>
        <td>${pct(p.p_home_clean_sheet)} / ${pct(p.p_away_clean_sheet)}</td>
        <td>${pct(p.p_btts)}</td>
        <td>${pct(p.p_over_2_5)}</td>
      </tr>`
    )
    .join("");
  container.innerHTML = `<div class="overflow-x"><table>
    <thead><tr>
      <th>Home</th><th>Away</th><th>Exp. goals</th><th>Likely score</th>
      <th>Home / draw / away</th><th>Clean sheet (H/A)</th><th>BTTS</th><th>O2.5</th>
    </tr></thead>
    <tbody>${rows}</tbody>
  </table></div>`;
}

async function loadFplPredictions() {
  const out = $("fpl-predictions-output");
  setLoading(out);
  try {
    const event = $("fpl-event").value;
    const qs = event ? `?event=${encodeURIComponent(event)}` : "";
    const predictions = await apiGet(`/predict/fpl${qs}`);
    renderPredictions(out, predictions);
  } catch (err) {
    setError(out, err);
  }
}

async function loadLaligaPredictions() {
  const out = $("laliga-predictions-output");
  setLoading(out);
  try {
    const matchday = $("laliga-matchday").value;
    const qs = matchday ? `?matchday=${encodeURIComponent(matchday)}` : "";
    const predictions = await apiGet(`/predict/laliga${qs}`);
    renderPredictions(out, predictions);
  } catch (err) {
    setError(out, err);
  }
}

// ---- FPL squad build ----

function playerRow(p, tags) {
  const tagHtml = (tags || [])
    .map((t) => `<span class="tag ${t.cls}">${t.label}</span>`)
    .join("");
  return `<tr><td>${p.pos}</td><td>${playerTipHtml(p)}${tagHtml}</td><td>${escapeHtml(p.team)}</td>
    <td>${p.price.toFixed(1)}m</td><td>${p.xp.toFixed(2)}</td></tr>`;
}

function renderSquad(container, result) {
  const tagsFor = (p) => {
    const tags = [];
    if (p.id === result.captain.id) tags.push({ cls: "captain", label: "C" });
    if (p.id === result.vice_captain.id) tags.push({ cls: "vice", label: "VC" });
    return tags;
  };
  const starterRows = [...result.starters]
    .sort((a, b) => b.xp - a.xp)
    .map((p) => playerRow(p, tagsFor(p)))
    .join("");
  const benchRows = result.bench.map((p) => playerRow(p)).join("");

  container.innerHTML = `
    <p class="summary-line">Squad total <b>${result.total_price}m</b> · Starting XI xP <b>${result.starting_xp}</b></p>
    <h3 style="font-size:0.9rem;margin:14px 0 6px;">Starting XI</h3>
    <div class="overflow-x"><table><thead><tr><th>Pos</th><th>Name</th><th>Team</th><th>Price</th><th>xP</th></tr></thead>
    <tbody>${starterRows}</tbody></table></div>
    <h3 style="font-size:0.9rem;margin:14px 0 6px;">Bench</h3>
    <div class="overflow-x"><table><thead><tr><th>Pos</th><th>Name</th><th>Team</th><th>Price</th><th>xP</th></tr></thead>
    <tbody>${benchRows}</tbody></table></div>
  `;
}

async function buildFplSquad() {
  const out = $("fpl-build-output");
  setLoading(out);
  try {
    const result = await apiGet("/recommend/fpl/build");
    renderSquad(out, result);
  } catch (err) {
    setError(out, err);
  }
}

// ---- Team builder ----

async function populateTeamBuilderLists() {
  try {
    const teams = await apiGet("/fpl/teams");
    $("tb-team-list").innerHTML = teams.map((t) => `<option value="${escapeHtml(t.name)}">`).join("");
  } catch (err) {
    // non-fatal — the free-text input still works without autocomplete
  }
  try {
    const players = await apiGet("/fpl/players");
    $("tb-player-list").innerHTML = players
      .map((p) => `<option value="${escapeHtml(p.name)}">${escapeHtml(p.name)} — ${escapeHtml(p.team)} (${p.pos})</option>`)
      .join("");
  } catch (err) {
    // non-fatal
  }
}

function renderTeamBuilder(container, result) {
  const tagsFor = (p) => {
    const tags = [];
    if (p.id === result.captain.id) tags.push({ cls: "captain", label: "C" });
    if (p.id === result.vice_captain.id) tags.push({ cls: "vice", label: "VC" });
    const note = result.injury_notes[p.id];
    if (note) tags.push({ cls: "hit", label: note.status.toUpperCase() });
    return tags;
  };
  const rowWithNote = (p) => {
    const note = result.injury_notes[p.id];
    const row = playerRow(p, tagsFor(p));
    if (!note || !note.news) return row;
    return row.replace(
      "</tr>",
      `</tr><tr><td></td><td colspan="4" style="color:var(--warn);font-size:0.78rem;padding-top:0;">${escapeHtml(note.news)}</td></tr>`
    );
  };

  const starterRows = [...result.starters].sort((a, b) => b.xp - a.xp).map(rowWithNote).join("");
  const benchRows = result.bench.map(rowWithNote).join("");

  const matched = result.favorite_players_matched.length
    ? `Locked in: <b>${result.favorite_players_matched.map(escapeHtml).join(", ")}</b>. `
    : "";
  const unmatched = result.favorite_players_unmatched.length
    ? `<span style="color:var(--bad)">Couldn't match: ${result.favorite_players_unmatched.map(escapeHtml).join(", ")}.</span> `
    : "";
  const favTeam = result.favorite_team
    ? `At least ${$("tb-min-count").value || 3} from <b>${escapeHtml(result.favorite_team)}</b>. `
    : "";

  container.innerHTML = `
    <p class="summary-line">${favTeam}${matched}${unmatched}Considered ${result.shortlisted_count} shortlisted candidates.</p>
    <p class="summary-line">Squad total <b>${result.total_price}m</b> · Starting XI xP <b>${result.starting_xp}</b></p>
    <h3 style="font-size:0.9rem;margin:14px 0 6px;">Starting XI</h3>
    <div class="overflow-x"><table><thead><tr><th>Pos</th><th>Name</th><th>Team</th><th>Price</th><th>xP</th></tr></thead>
    <tbody>${starterRows}</tbody></table></div>
    <h3 style="font-size:0.9rem;margin:14px 0 6px;">Bench</h3>
    <div class="overflow-x"><table><thead><tr><th>Pos</th><th>Name</th><th>Team</th><th>Price</th><th>xP</th></tr></thead>
    <tbody>${benchRows}</tbody></table></div>
  `;
}

async function buildTeamBuilder() {
  const out = $("tb-output");
  setLoading(out);
  try {
    const params = new URLSearchParams();
    const event = $("tb-event").value;
    const favTeam = $("tb-favorite-team").value.trim();
    const favPlayers = $("tb-favorite-players").value.trim();
    const minCount = $("tb-min-count").value;
    if (event) params.set("event", event);
    if (favTeam) params.set("favorite_team", favTeam);
    if (favPlayers) params.set("favorite_players", favPlayers);
    if (minCount) params.set("min_favorite_team_count", minCount);
    const result = await apiGet(`/recommend/fpl/team-builder?${params.toString()}`);
    renderTeamBuilder(out, result);
  } catch (err) {
    setError(out, err);
  }
}

// ---- Current team & top recommendations (FPL entry ID, or manual entry pre-deadline) ----

function toggleCurrentTeamMode() {
  const mode = document.querySelector('input[name="ct-mode"]:checked').value;
  $("ct-entry-mode").hidden = mode !== "entry";
  $("ct-manual-mode").hidden = mode !== "manual";
}

const CHIP_LABELS = {
  bench_boost: "Bench Boost",
  triple_captain: "Triple Captain",
  free_hit: "Free Hit",
  wildcard: "Wildcard",
};

function renderFullRecommendation(container, rec) {
  const unmatched = (rec.unmatched_names || []).length
    ? `<p class="summary-line" style="color:var(--bad)">Couldn't match: ${rec.unmatched_names.map(escapeHtml).join(", ")}.</p>`
    : "";

  const riskSection = rec.risk_flags.length
    ? `<h3 style="font-size:0.9rem;margin:14px 0 6px;">Check before deadline</h3>
       <ul class="flags">${rec.risk_flags
         .map((f) => {
           const repl = f.suggested_replacement
             ? ` &rarr; consider ${playerTipHtml(f.suggested_replacement)}`
             : "";
           return `<li>${playerTipHtml(f.player)} <span class="tag hit">${escapeHtml(f.status)}</span> ${escapeHtml(f.news)}${repl}</li>`;
         })
         .join("")}</ul>`
    : `<p class="summary-line">No live status concerns on your squad right now.</p>`;

  const lineupSection = rec.lineup_changes.length
    ? `<ul class="flags">${rec.lineup_changes.map((c) => `<li>${escapeHtml(c)}</li>`).join("")}</ul>`
    : "";

  const transferSection = rec.best_transfer
    ? `<p class="summary-line">
         OUT ${playerTipHtml(rec.best_transfer.out)} &rarr; IN ${playerTipHtml(rec.best_transfer.in)}
         &nbsp;${signedValue(rec.best_transfer.xp_gain)} xP
         over the next ${rec.transfer_horizon_gameweeks} gameweeks
         ${rec.best_transfer.is_hit ? '<span class="tag hit">-4 hit</span>' : ""}
       </p>`
    : `<p class="empty">No transfer worth making over the next ${rec.transfer_horizon_gameweeks} gameweeks.</p>`;

  const chipRows = rec.chip_lifts
    .map(
      (c) => `<tr>
        <td>${CHIP_LABELS[c.chip] || escapeHtml(c.chip)}</td>
        <td>${c.horizon_gameweeks} GW${c.horizon_gameweeks > 1 ? "s" : ""}</td>
        <td>${signedValue(c.lift)}</td>
        <td>${escapeHtml(c.note)}</td>
      </tr>`
    )
    .join("");

  container.innerHTML = `
    ${unmatched}
    ${riskSection}
    <h3 style="font-size:0.9rem;margin:14px 0 6px;">This gameweek</h3>
    <p class="summary-line">Captain <b>${playerTipHtml(rec.captain)}</b> · Vice <b>${playerTipHtml(rec.vice_captain)}</b></p>
    ${lineupSection}
    <h3 style="font-size:0.9rem;margin:14px 0 6px;">Best transfer</h3>
    ${transferSection}
    <h3 style="font-size:0.9rem;margin:14px 0 6px;">Chip lifts</h3>
    <div class="overflow-x"><table><thead><tr><th>Chip</th><th>Horizon</th><th>Lift</th><th>Note</th></tr></thead>
    <tbody>${chipRows}</tbody></table></div>
  `;
}

async function getCurrentTeamRecommendation() {
  const out = $("ct-output");
  const mode = document.querySelector('input[name="ct-mode"]:checked').value;
  setLoading(out);
  try {
    const params = new URLSearchParams();
    if (mode === "entry") {
      const entryId = $("ct-entry-id").value;
      if (!entryId) throw new Error("Enter your FPL entry ID first.");
      params.set("entry_id", entryId);
      params.set("free_transfers", $("ct-entry-free-transfers").value || 1);
    } else {
      const players = $("ct-players").value.trim();
      if (!players) throw new Error("Enter your current 15 players first.");
      params.set("players", players);
      params.set("bank", $("ct-bank").value || 0);
      params.set("free_transfers", $("ct-manual-free-transfers").value || 1);
    }
    const rec = await apiGet(`/recommend/fpl/full?${params.toString()}`);
    renderFullRecommendation(out, rec);
  } catch (err) {
    setError(out, err);
  }
}

// ---- La Liga recommendation ----

function renderLaligaRec(container, rec) {
  const flagRows = rec.transfer_flags
    .map(
      (f) => `<tr>
      <td>${escapeHtml(f.out.name)} (${f.out.pos})</td>
      <td>${escapeHtml(f.in.name)} (${f.in.pos})</td>
      <td>${signedValue(f.xp_gain)}</td>
      <td>${f.price_delta >= 0 ? "+" : ""}${f.price_delta}</td>
    </tr>`
    )
    .join("");
  container.innerHTML = `
    <p class="summary-line">Captain <b>${escapeHtml(rec.captain.name)}</b> (xP ${rec.captain.xp.toFixed(2)})</p>
    ${
      rec.transfer_flags.length
        ? `<div class="overflow-x"><table><thead><tr><th>Consider out</th><th>Consider in</th><th>xP gain</th><th>Price delta</th></tr></thead>
           <tbody>${flagRows}</tbody></table></div>`
        : `<p class="empty">No transfer flagged.</p>`
    }
  `;
}

async function recommendLaliga() {
  const out = $("laliga-output");
  setLoading(out);
  try {
    const raw = $("laliga-squad-json").value;
    let squad;
    try {
      squad = JSON.parse(raw);
    } catch {
      throw new Error("Squad JSON doesn't parse — check for a stray comma or quote.");
    }
    const rec = await apiPost("/recommend/laliga", squad);
    renderLaligaRec(out, rec);
  } catch (err) {
    setError(out, err);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("nav.tabs button").forEach((b) => {
    b.addEventListener("click", () => showTab(b.dataset.tab));
  });
  populateTeamBuilderLists();
});
