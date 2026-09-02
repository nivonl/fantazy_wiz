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
// still gets a dot, just not every point gets a label.
export function renderPriceLineChart(rows, { width = 640, height = 200 } = {}) {
  const priced = rows.filter((r) => r.price != null);
  if (priced.length < 2) return "";

  const chartHeight = height - 32;
  const n = priced.length;
  const stepX = width / (n - 1);
  const prices = priced.map((r) => r.price);
  const max = Math.max(...prices);
  const min = Math.min(...prices);
  const range = max - min || 1;

  const points = priced.map((r, i) => {
    const x = i * stepX;
    const y = chartHeight - ((r.price - min) / range) * (chartHeight - 24) - 12;
    return { x, y, r };
  });
  const path = points.map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");

  // Roughly one label per 55px of width is the densest that stays legible; always label the
  // most recent point (index n-1) regardless of where that interval would otherwise land.
  const labelEvery = Math.max(1, Math.ceil(n / Math.floor(width / 55)));

  const dots = points
    .map((p, i) => {
      const showLabel = i % labelEvery === 0 || i === n - 1;
      const label = showLabel
        ? `
    <text x="${p.x.toFixed(1)}" y="${(p.y - 8).toFixed(1)}" text-anchor="middle" font-size="11" font-weight="700" fill="var(--text)">${p.r.price.toFixed(1)}m</text>
    <text x="${p.x.toFixed(1)}" y="${(chartHeight + 18).toFixed(1)}" text-anchor="middle" font-size="10" fill="var(--text-dim)">GW${p.r.gameweek}</text>`
        : "";
      return `
    <circle cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="${showLabel ? 3.5 : 2}" fill="var(--accent)" />${label}`;
    })
    .join("");

  return `<svg viewBox="0 0 ${width} ${height}" width="100%" height="${height}" role="img" aria-label="Price by gameweek">
    <path d="${path}" fill="none" stroke="var(--accent)" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" />${dots}
  </svg>`;
}
