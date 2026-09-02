// Plain-SVG bar chart for a player's real points-by-gameweek history -- no charting library,
// same "small inline SVG, no dependency" philosophy as src/components/Sparkline.jsx, just
// bigger and labeled since this is a standalone page section, not an inline table cell. Uses
// CSS custom properties for color so it automatically respects the viewer's light/dark theme,
// same as every other themed element on the site.
export function renderPointsBarChart(rows, { width = 640, height = 200 } = {}) {
  if (!rows.length) return "";

  const barGap = 10;
  const chartHeight = height - 32; // room for the GW/season label under each bar
  const n = rows.length;
  const barWidth = (width - barGap * (n - 1)) / n;
  const max = Math.max(...rows.map((r) => r.total_points), 1);

  const bars = rows
    .map((r, i) => {
      const x = i * (barWidth + barGap);
      const h = r.total_points > 0 ? Math.max((r.total_points / max) * (chartHeight - 20), 3) : 2;
      const y = chartHeight - h;
      return `
    <rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${barWidth.toFixed(1)}" height="${h.toFixed(1)}" rx="4" fill="var(--analytics)" />
    <text x="${(x + barWidth / 2).toFixed(1)}" y="${(y - 6).toFixed(1)}" text-anchor="middle" font-size="12" font-weight="700" fill="var(--text)">${r.total_points}</text>
    <text x="${(x + barWidth / 2).toFixed(1)}" y="${(chartHeight + 18).toFixed(1)}" text-anchor="middle" font-size="10" fill="var(--text-dim)">GW${r.gameweek}</text>`;
    })
    .join("");

  return `<svg viewBox="0 0 ${width} ${height}" width="100%" height="${height}" role="img" aria-label="Points by gameweek">${bars}
  </svg>`;
}

// Price is a much smoother, slower-moving series than points, so a line reads better than
// bars here -- same theme-aware CSS-variable-color approach as the bar chart above. A season+
// of price history is a lot more points than the 3-4-bar points chart ever has, so text labels
// are thinned out to whatever the width can actually fit without overlapping -- every point
// still gets a dot, just not every point gets a label. Since this is a fixed-viewBox SVG scaled
// to whatever width the viewer's screen gives it (via width="100%"), font size and label
// spacing are picked generously here specifically so they hold up when the whole chart is
// rendered small on a phone, not just at desktop width.
export function renderPriceLineChart(rows, { width = 640, height = 230 } = {}) {
  const priced = rows.filter((r) => r.price != null);
  if (priced.length < 2) return "";

  const margin = 30; // left/right -- keeps the first/last point's label from clipping past the edge
  const plotWidth = width - margin * 2;
  const bottomAxisHeight = 48; // room for two label rows: GW number, then season
  const chartHeight = height - bottomAxisHeight;

  const n = priced.length;
  const stepX = n > 1 ? plotWidth / (n - 1) : 0;
  const prices = priced.map((r) => r.price);
  const max = Math.max(...prices);
  const min = Math.min(...prices);
  const range = max - min || 1;

  const points = priced.map((r, i) => {
    const x = margin + i * stepX;
    const y = chartHeight - ((r.price - min) / range) * (chartHeight - 30) - 16;
    return { x, y, r };
  });
  const path = points.map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");

  // Roughly one label per 85px of width is the densest that stays legible at the font size
  // below; always label the most recent point (index n-1) regardless of where that interval
  // would otherwise land, and anchor the first/last labels inward so they can't clip.
  const labelEvery = Math.max(1, Math.ceil(n / Math.floor(plotWidth / 85)));
  const shown = new Set();
  for (let i = 0; i < n; i += labelEvery) shown.add(i);
  shown.add(n - 1);
  // The forced-last-point rule above can land a label much closer to its neighbor than
  // `labelEvery` intends (e.g. the interval's last regular mark is 2 points before the final
  // one) -- drop whichever regular mark is too close to the final point rather than let the
  // two collide.
  const minGap = Math.max(1, Math.floor(labelEvery / 2));
  for (const i of [...shown].sort((a, b) => a - b)) {
    if (i !== n - 1 && n - 1 - i < minGap) shown.delete(i);
  }

  const dots = points
    .map((p, i) => {
      const showLabel = shown.has(i);
      const anchor = i === 0 ? "start" : i === n - 1 ? "end" : "middle";
      const label = showLabel
        ? `
    <text x="${p.x.toFixed(1)}" y="${(p.y - 10).toFixed(1)}" text-anchor="${anchor}" font-size="13" font-weight="700" fill="var(--text)">${p.r.price.toFixed(1)}m</text>
    <text x="${p.x.toFixed(1)}" y="${(chartHeight + 20).toFixed(1)}" text-anchor="${anchor}" font-size="12" fill="var(--text-dim)">GW${p.r.gameweek}</text>`
        : "";
      return `
    <circle cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="${showLabel ? 3.5 : 2}" fill="var(--accent)" />${label}`;
    })
    .join("");

  // Season markers: a dashed divider at each boundary, plus one label centered under each
  // season's own span of points -- otherwise "GW1, GW2, ..." repeating twice (once per season)
  // reads as one contiguous run with no indication the season actually rolled over.
  const segments = [];
  for (let i = 0; i < priced.length; i++) {
    const last = segments[segments.length - 1];
    if (last && last.season === priced[i].season) {
      last.endIndex = i;
    } else {
      segments.push({ season: priced[i].season, startIndex: i, endIndex: i });
    }
  }
  const seasonMarkup = segments
    .map((seg, segIdx) => {
      const startX = points[seg.startIndex].x;
      const endX = points[seg.endIndex].x;
      const centerX = (startX + endX) / 2;
      const divider =
        segIdx > 0
          ? `<line x1="${startX.toFixed(1)}" y1="4" x2="${startX.toFixed(1)}" y2="${chartHeight.toFixed(1)}" stroke="var(--panel-border)" stroke-width="1.5" stroke-dasharray="3,4" />`
          : "";
      return `
    ${divider}
    <text x="${centerX.toFixed(1)}" y="${(chartHeight + 40).toFixed(1)}" text-anchor="middle" font-size="12" font-weight="700" fill="var(--analytics)">${seg.season}</text>`;
    })
    .join("");

  return `<svg viewBox="0 0 ${width} ${height}" width="100%" height="${height}" role="img" aria-label="Price by gameweek">
    ${seasonMarkup}
    <path d="${path}" fill="none" stroke="var(--accent)" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" />${dots}
  </svg>`;
}
