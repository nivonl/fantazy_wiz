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
export function renderScatterChart(points, { width = 640, height = 420, xLabel, yLabel, color = "var(--analytics)", trendline = true, allowNegative = false, legend } = {}) {
  const margin = { left: 54, right: 20, top: 16, bottom: legend ? 60 : 46 };
  const plotW = width - margin.left - margin.right;
  const plotH = height - margin.top - margin.bottom;

  const xs = points.map((p) => p.x);
  const ys = points.map((p) => p.y);
  // Default behaviour (allowNegative: false) is unchanged from before: axes start at 0, matching
  // every existing caller (values that are naturally non-negative, like player output stats). A
  // PCA-style chart with negative coordinates on both axes opts into allowNegative instead of
  // forcing every caller to pass explicit min/max.
  const xMax = Math.max(...xs) * 1.05 || 1;
  const yMax = Math.max(...ys) * 1.08 || 1;
  const xMin = allowNegative ? Math.min(...xs) * 1.05 : 0;
  const yMin = allowNegative ? Math.min(...ys) * 1.08 : 0;

  const px = (x) => margin.left + ((x - xMin) / (xMax - xMin || 1)) * plotW;
  const py = (y) => margin.top + plotH - ((y - yMin) / (yMax - yMin || 1)) * plotH;

  const dots = points
    .map((p) => {
      const cx = px(p.x).toFixed(1);
      const cy = py(p.y).toFixed(1);
      const tooltip = `${escapeHtml(p.label)}: ${p.x.toFixed(2)} / ${p.y.toFixed(1)}`;
      const dotColor = p.color || color;
      return `<circle cx="${cx}" cy="${cy}" r="7" fill="transparent" pointer-events="all" data-tooltip="${tooltip}"><title>${tooltip}</title></circle>
    <circle cx="${cx}" cy="${cy}" r="3.5" fill="${dotColor}" fill-opacity="0.75" pointer-events="none" />`;
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
    const y0 = intercept + slope * xMin;
    const y1 = intercept + slope * xMax;
    trendPath = `<line x1="${px(xMin).toFixed(1)}" y1="${py(Math.max(yMin, Math.min(y0, yMax))).toFixed(1)}" x2="${px(xMax).toFixed(1)}" y2="${py(Math.max(yMin, Math.min(y1, yMax))).toFixed(1)}" stroke="var(--text-dim)" stroke-width="1.5" stroke-dasharray="5,5" />`;
  }

  // A handful of evenly-spaced axis ticks on each side.
  const xTicks = [0, 0.25, 0.5, 0.75, 1].map((f) => {
    const v = xMin + f * (xMax - xMin);
    return `<text x="${px(v).toFixed(1)}" y="${(height - margin.bottom + 20).toFixed(1)}" text-anchor="middle" font-size="11" fill="var(--text-dim)">${v.toFixed(1)}</text>`;
  });
  const yTicks = [0, 0.25, 0.5, 0.75, 1].map((f) => {
    const v = yMin + f * (yMax - yMin);
    return `
    <line x1="${margin.left}" y1="${py(v).toFixed(1)}" x2="${(width - margin.right).toFixed(1)}" y2="${py(v).toFixed(1)}" stroke="var(--panel-border)" stroke-width="1" stroke-dasharray="2,4" />
    <text x="${(margin.left - 8).toFixed(1)}" y="${(py(v) + 4).toFixed(1)}" text-anchor="end" font-size="11" fill="var(--text-dim)">${v.toFixed(0)}</text>`;
  });

  const legendSvg = legend
    ? `<g transform="translate(${margin.left}, ${height - 16})">${legend
        .map((s, i) => {
          const x = i * 150;
          return `<circle cx="${x + 5}" cy="-4" r="5" fill="${s.color}" /><text x="${x + 16}" y="0" font-size="12" fill="var(--text)">${escapeHtml(s.label)}</text>`;
        })
        .join("")}</g>`
    : "";

  return `<svg class="research-chart" viewBox="0 0 ${width} ${height}" width="100%" height="${height}" role="img" aria-label="Scatter plot">
    ${yTicks.join("")}
    <line x1="${margin.left}" y1="${(margin.top + plotH).toFixed(1)}" x2="${(width - margin.right).toFixed(1)}" y2="${(margin.top + plotH).toFixed(1)}" stroke="var(--panel-border)" stroke-width="1.5" />
    <line x1="${margin.left}" y1="${margin.top}" x2="${margin.left}" y2="${(margin.top + plotH).toFixed(1)}" stroke="var(--panel-border)" stroke-width="1.5" />
    ${xTicks.join("")}
    ${trendPath}
    ${dots}
    ${legendSvg}
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

// N×N correlation matrix as a colored grid — a genuine statistical heatmap (unlike the pitch-zone
// stacked bars above, which are an honestly-labeled proxy for a positional heatmap we can't build
// without raw x/y event data). `labels`: row/column names in order; `cells`: labels.length square
// array of values in [-1, 1]. Diverging color scale: --bad for negative, --good for positive,
// intensity by magnitude; diagonal (always 1) rendered at full intensity same as any other cell.
export function renderMatrixHeatmap(labels, cells, { width = 640, cellFmt = (v) => v.toFixed(2) } = {}) {
  const n = labels.length;
  const labelW = Math.min(170, width * 0.28);
  const cell = (width - labelW) / n;
  const height = labelW + n * cell + 10;

  function colorFor(v) {
    const t = Math.min(1, Math.abs(v));
    // Blend from the page panel color (near 0) toward --good or --bad (near +/-1) via opacity,
    // rather than mixing hex values server-side -- keeps this correct under both themes for free.
    return v >= 0 ? `color-mix(in srgb, var(--good) ${(t * 85).toFixed(0)}%, var(--panel))` : `color-mix(in srgb, var(--bad) ${(t * 85).toFixed(0)}%, var(--panel))`;
  }

  const colHeaders = labels
    .map((l, j) => {
      const x = labelW + j * cell + cell / 2;
      return `<text x="${x.toFixed(1)}" y="${(labelW - 8).toFixed(1)}" text-anchor="start" font-size="11" fill="var(--text-dim)" transform="rotate(-40, ${x.toFixed(1)}, ${(labelW - 8).toFixed(1)})">${escapeHtml(l)}</text>`;
    })
    .join("");

  const rowHeaders = labels
    .map((l, i) => {
      const y = labelW + i * cell + cell / 2 + 4;
      return `<text x="${(labelW - 10).toFixed(1)}" y="${y.toFixed(1)}" text-anchor="end" font-size="11.5" fill="var(--text)">${escapeHtml(l)}</text>`;
    })
    .join("");

  const rects = [];
  for (let i = 0; i < n; i++) {
    for (let j = 0; j < n; j++) {
      const v = cells[i][j];
      const x = labelW + j * cell;
      const y = labelW + i * cell;
      const tooltip = `${escapeHtml(labels[i])} × ${escapeHtml(labels[j])}: ${cellFmt(v)}`;
      const textColor = Math.abs(v) > 0.55 ? "#fff" : "var(--text)";
      rects.push(`<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${(cell - 1.5).toFixed(1)}" height="${(cell - 1.5).toFixed(1)}" fill="${colorFor(v)}" data-tooltip="${tooltip}" pointer-events="all"><title>${tooltip}</title></rect>
      <text x="${(x + cell / 2).toFixed(1)}" y="${(y + cell / 2 + 4).toFixed(1)}" text-anchor="middle" font-size="${cell > 44 ? 11 : 0}" fill="${textColor}" pointer-events="none">${cellFmt(v)}</text>`);
    }
  }

  return `<svg class="research-chart" viewBox="0 0 ${width} ${height}" width="100%" height="${height}" role="img" aria-label="Correlation matrix heatmap">
    ${colHeaders}
    ${rowHeaders}
    ${rects.join("")}
  </svg>`;
}
