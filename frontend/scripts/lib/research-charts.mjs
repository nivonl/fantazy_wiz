// Plain-SVG charts for long-form blog content (Deep Research posts) — same philosophy as
// chart.mjs's player-page charts: no charting library, CSS-variable colors so they respect the
// viewer's theme, and the shared [data-tooltip] hover mechanism every static page already loads
// (see render-page.mjs's CHART_TOOLTIP_SCRIPT). These are more general-purpose than chart.mjs's
// (which are shaped specifically around one player's gameweek history) — a horizontal bar chart,
// a diverging bar chart, and a scatter plot, each taking plain {label, value} / {x, y, label}
// data rather than FPL-shaped rows.

function escapeHtml(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

// Horizontal bar chart — one bar per item, longest bar first unless `sort` is false. Used for
// "median value by league" and the before/after "impact" chart.
export function renderHBarChart(items, { width = 640, height, valueFmt = (v) => String(v), sort = true, color = "var(--analytics)" } = {}) {
  const data = sort ? [...items].sort((a, b) => b.value - a.value) : items;
  const n = data.length;
  const rowH = 40;
  const barGap = 14;
  const labelW = Math.min(180, width * 0.32);
  const plotW = width - labelW - 70; // room for the value label past the bar end
  height = height || n * (rowH + barGap) + barGap;
  const max = Math.max(...data.map((d) => d.value), 1e-9);

  const bars = data
    .map((d, i) => {
      const y = barGap + i * (rowH + barGap);
      const barW = Math.max((d.value / max) * plotW, 2);
      const tooltip = `${escapeHtml(d.label)}: ${escapeHtml(valueFmt(d.value))}`;
      return `
    <text x="${labelW - 10}" y="${(y + rowH / 2 + 4).toFixed(1)}" text-anchor="end" font-size="13" fill="var(--text)">${escapeHtml(d.label)}</text>
    <rect x="${labelW}" y="${y.toFixed(1)}" width="${barW.toFixed(1)}" height="${rowH}" rx="6" fill="${color}" data-tooltip="${tooltip}" pointer-events="all"><title>${tooltip}</title></rect>
    <text x="${(labelW + barW + 8).toFixed(1)}" y="${(y + rowH / 2 + 4).toFixed(1)}" font-size="12.5" font-weight="700" fill="var(--text)">${escapeHtml(valueFmt(d.value))}</text>`;
    })
    .join("");

  return `<svg class="research-chart" viewBox="0 0 ${width} ${height}" width="100%" height="${height}" role="img" aria-label="Bar chart">${bars}
  </svg>`;
}

// Diverging horizontal bar chart, centered on 0 — positive values extend right in --good,
// negative extend left in --bad. Used for the feature-correlation chart.
export function renderDivergingBarChart(items, { width = 640, height, valueFmt = (v) => v.toFixed(2), sort = true } = {}) {
  const data = sort ? [...items].sort((a, b) => b.value - a.value) : items;
  const n = data.length;
  const rowH = 36;
  const barGap = 12;
  const labelW = Math.min(210, width * 0.36);
  const plotW = width - labelW - 20;
  const centerX = labelW + plotW / 2;
  height = height || n * (rowH + barGap) + barGap;
  const max = Math.max(...data.map((d) => Math.abs(d.value)), 1e-9);
  const halfPlot = plotW / 2 - 6;

  const bars = data
    .map((d, i) => {
      const y = barGap + i * (rowH + barGap);
      const w = (Math.abs(d.value) / max) * halfPlot;
      const positive = d.value >= 0;
      const x = positive ? centerX : centerX - w;
      const color = positive ? "var(--good)" : "var(--bad)";
      const tooltip = `${escapeHtml(d.label)}: ${escapeHtml(valueFmt(d.value))}`;
      const valueX = positive ? centerX + w + 8 : centerX - w - 8;
      const anchor = positive ? "start" : "end";
      return `
    <text x="${labelW - 10}" y="${(y + rowH / 2 + 4).toFixed(1)}" text-anchor="end" font-size="13" fill="var(--text)">${escapeHtml(d.label)}</text>
    <rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${w.toFixed(1)}" height="${rowH}" rx="5" fill="${color}" data-tooltip="${tooltip}" pointer-events="all"><title>${tooltip}</title></rect>
    <text x="${valueX.toFixed(1)}" y="${(y + rowH / 2 + 4).toFixed(1)}" text-anchor="${anchor}" font-size="12" font-weight="700" fill="var(--text)">${escapeHtml(valueFmt(d.value))}</text>`;
    })
    .join("");

  return `<svg class="research-chart" viewBox="0 0 ${width} ${height}" width="100%" height="${height}" role="img" aria-label="Diverging bar chart">
    <line x1="${centerX.toFixed(1)}" y1="4" x2="${centerX.toFixed(1)}" y2="${(height - 4).toFixed(1)}" stroke="var(--panel-border)" stroke-width="1.5" />
    ${bars}
  </svg>`;
}

// Scatter plot with per-point hover tooltips (player name + both values) — used for the
// output-vs-fantasy-points chart. `points`: [{x, y, label}]. An optional `trendline` (from a
// simple least-squares fit) is drawn as a dashed reference line.
export function renderScatterChart(points, { width = 640, height = 420, xLabel, yLabel, color = "var(--analytics)", trendline = true } = {}) {
  const margin = { left: 54, right: 20, top: 16, bottom: 46 };
  const plotW = width - margin.left - margin.right;
  const plotH = height - margin.top - margin.bottom;

  const xs = points.map((p) => p.x);
  const ys = points.map((p) => p.y);
  const xMax = Math.max(...xs) * 1.05 || 1;
  const yMax = Math.max(...ys) * 1.08 || 1;

  const px = (x) => margin.left + (x / xMax) * plotW;
  const py = (y) => margin.top + plotH - (y / yMax) * plotH;

  const dots = points
    .map((p) => {
      const cx = px(p.x).toFixed(1);
      const cy = py(p.y).toFixed(1);
      const tooltip = `${escapeHtml(p.label)}: ${p.x.toFixed(2)} / ${p.y.toFixed(1)}`;
      return `<circle cx="${cx}" cy="${cy}" r="7" fill="transparent" pointer-events="all" data-tooltip="${tooltip}"><title>${tooltip}</title></circle>
    <circle cx="${cx}" cy="${cy}" r="3.5" fill="${color}" fill-opacity="0.65" pointer-events="none" />`;
    })
    .join("");

  let trendPath = "";
  if (trendline && points.length > 2) {
    const n = points.length;
    const sumX = xs.reduce((a, b) => a + b, 0);
    const sumY = ys.reduce((a, b) => a + b, 0);
    const sumXY = points.reduce((a, p) => a + p.x * p.y, 0);
    const sumXX = points.reduce((a, p) => a + p.x * p.x, 0);
    const slope = (n * sumXY - sumX * sumY) / (n * sumXX - sumX * sumX || 1);
    const intercept = (sumY - slope * sumX) / n;
    const y0 = Math.max(0, intercept);
    const y1 = intercept + slope * xMax;
    trendPath = `<line x1="${px(0).toFixed(1)}" y1="${py(y0).toFixed(1)}" x2="${px(xMax).toFixed(1)}" y2="${py(Math.min(y1, yMax)).toFixed(1)}" stroke="var(--text-dim)" stroke-width="1.5" stroke-dasharray="5,5" />`;
  }

  // A handful of evenly-spaced axis ticks on each side.
  const xTicks = [0, 0.25, 0.5, 0.75, 1].map((f) => {
    const v = f * xMax;
    return `<text x="${px(v).toFixed(1)}" y="${(height - margin.bottom + 20).toFixed(1)}" text-anchor="middle" font-size="11" fill="var(--text-dim)">${v.toFixed(1)}</text>`;
  });
  const yTicks = [0, 0.25, 0.5, 0.75, 1].map((f) => {
    const v = f * yMax;
    return `
    <line x1="${margin.left}" y1="${py(v).toFixed(1)}" x2="${(width - margin.right).toFixed(1)}" y2="${py(v).toFixed(1)}" stroke="var(--panel-border)" stroke-width="1" stroke-dasharray="2,4" />
    <text x="${(margin.left - 8).toFixed(1)}" y="${(py(v) + 4).toFixed(1)}" text-anchor="end" font-size="11" fill="var(--text-dim)">${v.toFixed(0)}</text>`;
  });

  return `<svg class="research-chart" viewBox="0 0 ${width} ${height}" width="100%" height="${height}" role="img" aria-label="Scatter plot">
    ${yTicks.join("")}
    <line x1="${margin.left}" y1="${(margin.top + plotH).toFixed(1)}" x2="${(width - margin.right).toFixed(1)}" y2="${(margin.top + plotH).toFixed(1)}" stroke="var(--panel-border)" stroke-width="1.5" />
    <line x1="${margin.left}" y1="${margin.top}" x2="${margin.left}" y2="${(margin.top + plotH).toFixed(1)}" stroke="var(--panel-border)" stroke-width="1.5" />
    ${xTicks.join("")}
    ${trendPath}
    ${dots}
    ${xLabel ? `<text x="${(margin.left + plotW / 2).toFixed(1)}" y="${height - 6}" text-anchor="middle" font-size="12.5" fill="var(--text-dim)">${escapeHtml(xLabel)}</text>` : ""}
    ${yLabel ? `<text x="14" y="${(margin.top + plotH / 2).toFixed(1)}" text-anchor="middle" font-size="12.5" fill="var(--text-dim)" transform="rotate(-90, 14, ${(margin.top + plotH / 2).toFixed(1)})">${escapeHtml(yLabel)}</text>` : ""}
  </svg>`;
}

// Multi-series line chart over a shared categorical x-axis (season labels, gameweeks, etc.) --
// used for "how has this metric moved over several seasons" trend charts. `series`:
// [{label, color, points: [{x: <category label>, y: number}]}]. All series share the same x
// categories, evenly spaced. A light dot + hover tooltip marks each data point.
export function renderLineChart(series, { width = 640, height = 320, yLabel, yFmt = (v) => v.toFixed(1), yMin } = {}) {
  const margin = { left: 54, right: 20, top: 16, bottom: series.length > 1 ? 56 : 36 };
  const plotW = width - margin.left - margin.right;
  const plotH = height - margin.top - margin.bottom;

  const categories = series[0]?.points.map((p) => p.x) || [];
  const allY = series.flatMap((s) => s.points.map((p) => p.y));
  const yMax = Math.max(...allY) * 1.08;
  const yLo = yMin !== undefined ? yMin : Math.min(...allY, 0) * (Math.min(...allY, 0) < 0 ? 1.08 : 0.92);

  const px = (i) => margin.left + (categories.length > 1 ? (i / (categories.length - 1)) * plotW : plotW / 2);
  const py = (y) => margin.top + plotH - ((y - yLo) / (yMax - yLo || 1)) * plotH;

  const yTicks = [0, 0.25, 0.5, 0.75, 1].map((f) => {
    const v = yLo + f * (yMax - yLo);
    return `
    <line x1="${margin.left}" y1="${py(v).toFixed(1)}" x2="${(width - margin.right).toFixed(1)}" y2="${py(v).toFixed(1)}" stroke="var(--panel-border)" stroke-width="1" stroke-dasharray="2,4" />
    <text x="${(margin.left - 8).toFixed(1)}" y="${(py(v) + 4).toFixed(1)}" text-anchor="end" font-size="11" fill="var(--text-dim)">${yFmt(v)}</text>`;
  });
  const xTicks = categories.map((c, i) => `<text x="${px(i).toFixed(1)}" y="${(height - margin.bottom + 20).toFixed(1)}" text-anchor="middle" font-size="11.5" fill="var(--text-dim)">${escapeHtml(String(c))}</text>`);

  const seriesSvg = series
    .map((s) => {
      const path = s.points.map((p, i) => `${i === 0 ? "M" : "L"} ${px(i).toFixed(1)} ${py(p.y).toFixed(1)}`).join(" ");
      const dots = s.points
        .map((p, i) => {
          const cx = px(i).toFixed(1);
          const cy = py(p.y).toFixed(1);
          const tooltip = `${escapeHtml(s.label)} — ${escapeHtml(String(p.x))}: ${yFmt(p.y)}`;
          return `<circle cx="${cx}" cy="${cy}" r="8" fill="transparent" pointer-events="all" data-tooltip="${tooltip}"><title>${tooltip}</title></circle>
      <circle cx="${cx}" cy="${cy}" r="3.5" fill="${s.color}" />`;
        })
        .join("");
      return `<path d="${path}" fill="none" stroke="${s.color}" stroke-width="2.5" />${dots}`;
    })
    .join("");

  const legend = series.length > 1
    ? `<g transform="translate(${margin.left}, ${height - 22})">${series
        .map((s, i) => {
          const x = i * 150;
          return `<rect x="${x}" y="-9" width="11" height="11" rx="2" fill="${s.color}" /><text x="${x + 16}" y="0" font-size="12" fill="var(--text)">${escapeHtml(s.label)}</text>`;
        })
        .join("")}</g>`
    : "";

  return `<svg class="research-chart" viewBox="0 0 ${width} ${height}" width="100%" height="${height}" role="img" aria-label="Line chart">
    ${yTicks.join("")}
    <line x1="${margin.left}" y1="${(margin.top + plotH).toFixed(1)}" x2="${(width - margin.right).toFixed(1)}" y2="${(margin.top + plotH).toFixed(1)}" stroke="var(--panel-border)" stroke-width="1.5" />
    ${xTicks.join("")}
    ${seriesSvg}
    ${legend}
    ${yLabel ? `<text x="14" y="${(margin.top + plotH / 2).toFixed(1)}" text-anchor="middle" font-size="12.5" fill="var(--text-dim)" transform="rotate(-90, 14, ${(margin.top + plotH / 2).toFixed(1)})">${escapeHtml(yLabel)}</text>` : ""}
  </svg>`;
}

// Horizontal 100%-stacked bar chart — one bar per row, split into named colored segments that
// sum to 100%. Used as an honest proxy for a pitch-zone "heatmap": we don't have raw x/y event
// coordinates, but we do have defensive-third / middle-third / attacking-third shares, and a
// stacked bar communicates the same "where on the pitch" idea without overclaiming precision.
export function renderStackedHBarChart(items, { width = 640, height, segmentLabels } = {}) {
  const n = items.length;
  const rowH = 40;
  const barGap = 16;
  const labelW = Math.min(150, width * 0.26);
  const plotW = width - labelW - 16;
  height = height || n * (rowH + barGap) + barGap + 30;

  const rows = items
    .map((item, i) => {
      const y = barGap + i * (rowH + barGap);
      const total = item.segments.reduce((a, s) => a + s.value, 0) || 1;
      let x = labelW;
      const segs = item.segments
        .map((s) => {
          const w = (s.value / total) * plotW;
          const tooltip = `${escapeHtml(item.label)} — ${escapeHtml(s.name)}: ${s.value.toFixed(1)}%`;
          const rect = `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${Math.max(w, 0.5).toFixed(1)}" height="${rowH}" fill="${s.color}" data-tooltip="${tooltip}" pointer-events="all"><title>${tooltip}</title></rect>${
            w > 34 ? `<text x="${(x + w / 2).toFixed(1)}" y="${(y + rowH / 2 + 4).toFixed(1)}" text-anchor="middle" font-size="11.5" font-weight="700" fill="#fff">${s.value.toFixed(0)}%</text>` : ""
          }`;
          x += w;
          return rect;
        })
        .join("");
      return `<text x="${labelW - 10}" y="${(y + rowH / 2 + 4).toFixed(1)}" text-anchor="end" font-size="13" fill="var(--text)">${escapeHtml(item.label)}</text>${segs}`;
    })
    .join("");

  const legend = segmentLabels
    ? `<g transform="translate(${labelW}, ${(height - 22).toFixed(1)})">${segmentLabels
        .map((s, i) => {
          const x = i * 170;
          return `<rect x="${x}" y="-9" width="11" height="11" rx="2" fill="${s.color}" /><text x="${x + 16}" y="0" font-size="12" fill="var(--text)">${escapeHtml(s.name)}</text>`;
        })
        .join("")}</g>`
    : "";

  return `<svg class="research-chart" viewBox="0 0 ${width} ${height}" width="100%" height="${height}" role="img" aria-label="Stacked bar chart">${rows}${legend}</svg>`;
}
