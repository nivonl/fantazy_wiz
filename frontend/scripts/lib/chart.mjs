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
