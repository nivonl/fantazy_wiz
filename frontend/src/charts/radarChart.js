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
export function renderRadarChart(categoryLabels, seriesAll, seriesPosition, options = {}) {
  const n = categoryLabels.length;
  if (!n || (!seriesAll && !seriesPosition)) return "";

  const { width = 320, height = 300, labelAll = "All players", labelPosition = "Position" } = options;
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

  const rings = [0.2, 0.4, 0.6, 0.8, 1.0]
    .map((f) => {
      const pts = Array.from({ length: n }, (_, i) => axisPoint(i, maxRadius * f).map((v) => v.toFixed(1)).join(",")).join(" ");
      return `<polygon points="${pts}" fill="none" stroke="var(--panel-border)" stroke-width="1" />`;
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

  const seriesPolygon = (series, color, dashed) => {
    if (!series) return "";
    const pts = series
      .map((v, i) => {
        const clamped = Math.max(0, Math.min(100, v ?? 0));
        return axisPoint(i, maxRadius * (clamped / 100)).map((p) => p.toFixed(1)).join(",");
      })
      .join(" ");
    const dash = dashed ? ` stroke-dasharray="4,3"` : "";
    return `<polygon points="${pts}" fill="${color}" fill-opacity="${dashed ? 0.08 : 0.18}" stroke="${color}" stroke-width="2"${dash} />`;
  };

  const allPolygon = seriesPolygon(seriesAll, "var(--accent)", false);
  const positionPolygon = seriesPolygon(seriesPosition, "var(--analytics)", true);

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
    ${allPolygon}
    ${positionPolygon}
    ${labels}
    ${legend}
  </svg>`;
}

function escapeXml(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
