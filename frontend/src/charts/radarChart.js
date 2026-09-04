// Plain-SVG percentile radar -- same "small inline SVG string, CSS-variable colors, no charting
// library" approach as scripts/lib/chart.mjs, but living under src/ (not scripts/) since this one
// is genuinely shared: the Node static-page generator imports it directly (same convention as
// src/team-colors.js), and the React popup modal renders the exact same SVG string via
// dangerouslySetInnerHTML, so the radar drawn in the SPA is never a second implementation that
// could drift from the one baked into the static pages.
//
// `categoryLabels` is an ordered array of axis labels (e.g. ["Scoring", "Creativity",
// "Involvement", "Defending"], or the goalkeeper-specific set). `seriesAll`/`seriesPosition` are
// parallel arrays of 0-100 percentile scores in that same order -- either may be `null` (a
// goalkeeper has no "all players" series at all, see services/player_radar.py), and a category
// with no underlying data for this window renders as `null`/`undefined` at that index, which
// this function draws as the center point (0) rather than omitting the axis entirely -- an SVG
// polygon can't skip a vertex without a hole, and "unknown" reading as "nothing to show" is a
// more honest reading, than *inventing* a spot, of a chart the viewer already knows is
// percentile-based (0 being the bottom, not a real "worst in the league" claim, is implicit
// context here).
// Short display names for the raw per-90 rate fields a category is built from (see
// services/player_radar.py's RADAR_CATEGORIES_OUTFIELD/GK) -- kept here rather than shipped in
// every player's JSON entry, since it's a fixed ~15-entry lookup table, not per-player data.
export const RADAR_FIELD_LABELS = {
  goals_scored: "Goals",
  expected_goals: "xG",
  threat: "Threat",
  assists: "Assists",
  expected_assists: "xA",
  creativity: "Creativity",
  influence: "Influence",
  bps: "BPS",
  tackles: "Tackles",
  clearances_blocks_interceptions: "CBI",
  recoveries: "Recoveries",
  defensive_contribution: "Def. actions",
  clean_sheets: "Clean sheets",
  goals_conceded: "Goals conceded",
  saves: "Saves",
};

// "what this percentile is based on" -- the actual per-90 numbers behind one category, e.g.
// "Goals: 0.85/90, xG: 0.72/90, Threat: 45.2/90". A field with no data for this player/window
// (see fpl_history.py -- a stat that didn't exist yet in an older season) is simply omitted
// rather than shown as a misleading 0.
export function formatCategoryDetail(fieldKeys, stats) {
  if (!fieldKeys || !stats) return "";
  return fieldKeys
    .filter((f) => stats[f] != null)
    .map((f) => `${RADAR_FIELD_LABELS[f] || f}: ${stats[f].toFixed(2)}/90`)
    .join(", ");
}

export function renderRadarChart(categoryLabels, seriesAll, seriesPosition, options = {}) {
  const n = categoryLabels.length;
  if (!n || (!seriesAll && !seriesPosition)) return "";

  const { width = 320, height = 300, labelAll = "All players", labelPosition = "Position", categoryDetails = [] } = options;
  const cx = width / 2;
  const cy = 130;
  // maxRadius + the label offset below must leave enough horizontal room on both sides for the
  // longest side-axis label ("Clean Sheets", ~68px at 10px font) without clipping past the
  // viewBox edge -- verified visually (a first pass at maxRadius=92/width=260 clipped
  // "Defending" and "Creativity" at the left/right edges).
  const maxRadius = 76;

  const angleFor = (i) => -Math.PI / 2 + i * ((2 * Math.PI) / n);
  const axisPoint = (i, r) => {
    const a = angleFor(i);
    return [cx + r * Math.cos(a), cy + r * Math.sin(a)];
  };

  const ringFractions = [0.2, 0.4, 0.6, 0.8, 1.0];
  const rings = ringFractions
    .map((f) => {
      const pts = Array.from({ length: n }, (_, i) => axisPoint(i, maxRadius * f).map((v) => v.toFixed(1)).join(",")).join(" ");
      return `<polygon points="${pts}" fill="none" stroke="var(--panel-border)" stroke-width="1" />`;
    })
    .join("");

  // Every ring is a fixed percentile value (20/40/60/80/100), the SAME across every window and
  // every player -- this scale never auto-fits to a single chart's own data (unlike some radar
  // libraries), so a mark drawn further out always means a genuinely higher percentile, comparable
  // chart to chart. These small numbers along the top spoke make that fixed scale visible rather
  // than just true-but-invisible; offset off the spoke line itself so they don't sit under the
  // vertex dot/line drawn on that same axis.
  const scaleTicks = ringFractions
    .map((f) => {
      const y = cy - maxRadius * f;
      return `<text x="${(cx + 5).toFixed(1)}" y="${(y + 3).toFixed(1)}" font-size="8" fill="var(--text-dim)" fill-opacity="0.75">${Math.round(f * 100)}</text>`;
    })
    .join("");

  const spokes = Array.from({ length: n }, (_, i) => {
    const [x, y] = axisPoint(i, maxRadius);
    return `<line x1="${cx}" y1="${cy}" x2="${x.toFixed(1)}" y2="${y.toFixed(1)}" stroke="var(--panel-border)" stroke-width="1" />`;
  }).join("");

  const labels = categoryLabels
    .map((label, i) => {
      const [x, y] = axisPoint(i, maxRadius + 14);
      const anchor = x < cx - 4 ? "end" : x > cx + 4 ? "start" : "middle";
      const dy = y < cy - maxRadius * 0.5 ? -2 : y > cy + maxRadius * 0.5 ? 10 : 4;
      return `<text x="${x.toFixed(1)}" y="${(y + dy).toFixed(1)}" text-anchor="${anchor}" font-size="10" fill="var(--text-dim)">${escapeXml(label)}</text>`;
    })
    .join("");

  // Native <title> on each vertex -- the browser's own hover tooltip, not a custom one -- is the
  // right call for this "model" specifically: these SVGs are static markup with no JS runtime of
  // their own (the static player pages need to work with zero JS, and the React popup renders
  // this exact same string via dangerouslySetInnerHTML rather than a parallel implementation), so
  // a real interactive tooltip component isn't an option here without duplicating the chart in
  // JSX. A titled dot per data point needs none of that and behaves identically in both places.
  //
  // Two circles per vertex: the small one (r=3) is the visible dot; a second, invisible one
  // (r=9, fill="transparent") sits on top purely as a bigger hover/tap target and carries the
  // actual <title> -- the visible dot alone renders at ~5px on screen once the chart is scaled
  // down to its CSS width, which is too small to reliably hover (confirmed: real-world reports
  // of "hover isn't working" traced to exactly this).
  const seriesMarkup = (series, color, dashed, groupLabel) => {
    if (!series) return { polygon: "", markers: "" };
    const pts = series
      .map((v, i) => {
        const clamped = Math.max(0, Math.min(100, v ?? 0));
        return axisPoint(i, maxRadius * (clamped / 100)).map((p) => p.toFixed(1)).join(",");
      })
      .join(" ");
    const dash = dashed ? ` stroke-dasharray="4,3"` : "";
    const polygon = `<polygon points="${pts}" fill="${color}" fill-opacity="${dashed ? 0.08 : 0.18}" stroke="${color}" stroke-width="2"${dash} />`;

    const markers = series
      .map((v, i) => {
        const hasValue = v != null;
        const clamped = Math.max(0, Math.min(100, v ?? 0));
        const [x, y] = axisPoint(i, maxRadius * (clamped / 100));
        const detail = categoryDetails[i];
        const tooltip = hasValue
          ? `${escapeXml(categoryLabels[i])}: ${v.toFixed(1)}th percentile (${escapeXml(groupLabel)})${detail ? ` — ${escapeXml(detail)}` : ""}`
          : `${escapeXml(categoryLabels[i])}: no data (${escapeXml(groupLabel)})`;
        const cx2 = x.toFixed(1);
        const cy2 = y.toFixed(1);
        return (
          // pointer-events="all" is load-bearing here -- a zero-alpha fill isn't reliably
          // hit-tested under the default `pointer-events: visiblePainted` in every browser
          // (some treat "painted with alpha 0" as "not painted" for hit-testing purposes), which
          // silently made this whole invisible hit-circle un-hoverable despite the correct
          // <title> content sitting right there in the DOM. Forcing "all" makes the geometry
          // itself the hit target regardless of paint/fill state.
          `<circle cx="${cx2}" cy="${cy2}" r="9" fill="transparent" pointer-events="all"><title>${tooltip}</title></circle>` +
          `<circle cx="${cx2}" cy="${cy2}" r="3" fill="${color}" fill-opacity="${hasValue ? 1 : 0.35}" pointer-events="none" />`
        );
      })
      .join("");

    return { polygon, markers };
  };

  const all = seriesMarkup(seriesAll, "var(--accent)", false, labelAll);
  const position = seriesMarkup(seriesPosition, "var(--analytics)", true, labelPosition);

  const legendY = height - 22;
  let legend = "";
  if (seriesAll) {
    legend += `<circle cx="14" cy="${legendY}" r="4" fill="var(--accent)" /><text x="24" y="${legendY + 4}" font-size="11" fill="var(--text-dim)">${escapeXml(labelAll)}</text>`;
  }
  if (seriesPosition) {
    const lx = seriesAll ? width / 2 + 6 : 14;
    legend += `<circle cx="${lx}" cy="${legendY}" r="4" fill="var(--analytics)" /><text x="${lx + 10}" y="${legendY + 4}" font-size="11" fill="var(--text-dim)">${escapeXml(labelPosition)}</text>`;
  }

  return `<svg viewBox="0 0 ${width} ${height}" width="100%" height="${height}" role="img" aria-label="Stat radar">
    ${rings}
    ${spokes}
    ${scaleTicks}
    ${all.polygon}
    ${position.polygon}
    ${all.markers}
    ${position.markers}
    ${labels}
    ${legend}
  </svg>`;
}

function escapeXml(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
