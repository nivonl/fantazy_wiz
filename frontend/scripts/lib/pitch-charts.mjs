// Pitch-relative SVG charts for match-level event data (passing networks, single-play sequence
// maps) -- a different family from research-charts.mjs's generic bar/line/scatter/matrix charts,
// since these need an actual pitch outline and real x/y event coordinates rather than abstract
// axes. Coordinates in are StatsBomb's own convention: a 120 (length) x 80 (width) pitch, each
// team's own events oriented with them attacking toward x=120 for the whole match regardless of
// which physical end they defended in either half (confirmed against this match's own shot
// locations before relying on it) -- so no home/away or first/second-half flip is needed here.

function escapeHtml(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

// Pitch markings in StatsBomb's own 120x80 units (standard proportions: 18-yard box, 6-yard box,
// penalty spot, center circle) -- reused by both chart types below via the two orientation helpers.
const PITCH_MARKS = {
  length: 120, width: 80, penaltyBoxDepth: 18, penaltyBoxWidth: 44, sixBoxDepth: 6, sixBoxWidth: 20,
  penaltySpotDist: 12, centerCircleR: 10, cornerR: 1,
};

// Vertical pitch (own goal at bottom, attacking up) -- matches the convention every reference
// passing-network graphic uses. Returns {toSvg(sbX, sbY), outlineSvg, width, height}.
function verticalPitch({ width = 420, margin = 6 } = {}) {
  const { length, width: pw } = PITCH_MARKS;
  const plotW = width - margin * 2;
  const plotH = plotW * (length / pw);
  const height = plotH + margin * 2;
  const toSvg = (sbX, sbY) => [margin + (sbY / pw) * plotW, margin + plotH * (1 - sbX / length)];

  const m = PITCH_MARKS;
  const [boxTLx, boxTLy] = toSvg(0, (pw - m.penaltyBoxWidth) / 2);
  const [boxBRx, boxBRy] = toSvg(m.penaltyBoxDepth, (pw + m.penaltyBoxWidth) / 2);
  const [obTLx, obTLy] = toSvg(length - m.penaltyBoxDepth, (pw - m.penaltyBoxWidth) / 2);
  const [obBRx, obBRy] = toSvg(length, (pw + m.penaltyBoxWidth) / 2);
  const [sixTLx, sixTLy] = toSvg(0, (pw - m.sixBoxWidth) / 2);
  const [sixBRx, sixBRy] = toSvg(m.sixBoxDepth, (pw + m.sixBoxWidth) / 2);
  const [osixTLx, osixTLy] = toSvg(length - m.sixBoxDepth, (pw - m.sixBoxWidth) / 2);
  const [osixBRx, osixBRy] = toSvg(length, (pw + m.sixBoxWidth) / 2);
  const [cx, cy] = toSvg(length / 2, pw / 2);
  const [, halfwayY] = toSvg(length / 2, 0);
  const circleRpx = (m.centerCircleR / pw) * plotW;

  const outlineSvg = `
    <rect x="${margin}" y="${margin}" width="${plotW}" height="${plotH}" fill="none" stroke="var(--panel-border)" stroke-width="1.5" />
    <line x1="${margin}" y1="${halfwayY.toFixed(1)}" x2="${(margin + plotW).toFixed(1)}" y2="${halfwayY.toFixed(1)}" stroke="var(--panel-border)" stroke-width="1" />
    <circle cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" r="${circleRpx.toFixed(1)}" fill="none" stroke="var(--panel-border)" stroke-width="1" />
    <rect x="${boxTLx.toFixed(1)}" y="${boxBRy.toFixed(1)}" width="${(boxBRx - boxTLx).toFixed(1)}" height="${(boxTLy - boxBRy).toFixed(1)}" fill="none" stroke="var(--panel-border)" stroke-width="1" />
    <rect x="${obTLx.toFixed(1)}" y="${obBRy.toFixed(1)}" width="${(obBRx - obTLx).toFixed(1)}" height="${(obTLy - obBRy).toFixed(1)}" fill="none" stroke="var(--panel-border)" stroke-width="1" />
    <rect x="${sixTLx.toFixed(1)}" y="${sixBRy.toFixed(1)}" width="${(sixBRx - sixTLx).toFixed(1)}" height="${(sixTLy - sixBRy).toFixed(1)}" fill="none" stroke="var(--panel-border)" stroke-width="1" />
    <rect x="${osixTLx.toFixed(1)}" y="${osixBRy.toFixed(1)}" width="${(osixBRx - osixTLx).toFixed(1)}" height="${(osixTLy - osixBRy).toFixed(1)}" fill="none" stroke="var(--panel-border)" stroke-width="1" />
  `;
  return { toSvg, outlineSvg, width, height, margin, plotW, plotH };
}

// Horizontal pitch (attacking left-to-right) -- used for the single-play sequence map, matching
// the convention of that style of graphic (Opta/StatsBomb "goal buildup" diagrams).
function horizontalPitch({ width = 640, margin = 6 } = {}) {
  const { length, width: pw } = PITCH_MARKS;
  const plotW = width - margin * 2;
  const plotH = plotW * (pw / length);
  const height = plotH + margin * 2;
  const toSvg = (sbX, sbY) => [margin + (sbX / length) * plotW, margin + (sbY / pw) * plotH];

  const m = PITCH_MARKS;
  const [boxTLx, boxTLy] = toSvg(length - m.penaltyBoxDepth, (pw - m.penaltyBoxWidth) / 2);
  const [boxBRx, boxBRy] = toSvg(length, (pw + m.penaltyBoxWidth) / 2);
  const [obTLx, obTLy] = toSvg(0, (pw - m.penaltyBoxWidth) / 2);
  const [obBRx, obBRy] = toSvg(m.penaltyBoxDepth, (pw + m.penaltyBoxWidth) / 2);
  const [cx, cy] = toSvg(length / 2, pw / 2);
  const circleRpx = (m.centerCircleR / length) * plotW;
  const [halfwayX] = toSvg(length / 2, 0);

  const outlineSvg = `
    <rect x="${margin}" y="${margin}" width="${plotW}" height="${plotH}" fill="none" stroke="var(--panel-border)" stroke-width="1.5" />
    <line x1="${halfwayX.toFixed(1)}" y1="${margin}" x2="${halfwayX.toFixed(1)}" y2="${(margin + plotH).toFixed(1)}" stroke="var(--panel-border)" stroke-width="1" />
    <circle cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" r="${circleRpx.toFixed(1)}" fill="none" stroke="var(--panel-border)" stroke-width="1" />
    <rect x="${boxTLx.toFixed(1)}" y="${boxTLy.toFixed(1)}" width="${(boxBRx - boxTLx).toFixed(1)}" height="${(boxBRy - boxTLy).toFixed(1)}" fill="none" stroke="var(--panel-border)" stroke-width="1" />
    <rect x="${obTLx.toFixed(1)}" y="${obTLy.toFixed(1)}" width="${(obBRx - obTLx).toFixed(1)}" height="${(obBRy - obTLy).toFixed(1)}" fill="none" stroke="var(--panel-border)" stroke-width="1" />
  `;
  return { toSvg, outlineSvg, width, height, margin };
}

// A team's passing network: nodes at each player's average pass-origin location (sized by pass
// volume, colored by a graph-theory centrality metric), edges between players who exchanged at
// least `minEdgeCount` passes (weighted by pass count). `nodes`: [{short, x, y, passes,
// betweenness_centrality, ...}], `edges`: [{from, to, count}] (from/to = full player names
// matching nodes' `player` field).
export function renderPassingNetwork(nodes, edges, { width = 420, minEdgeCount = 2, colorMetric = "betweenness_centrality" } = {}) {
  const { toSvg, outlineSvg, height, margin } = verticalPitch({ width });
  const byName = Object.fromEntries(nodes.map((n) => [n.player, n]));

  const maxPasses = Math.max(...nodes.map((n) => n.passes), 1);
  const maxEdge = Math.max(...edges.map((e) => e.count), 1);
  const maxMetric = Math.max(...nodes.map((n) => n[colorMetric] || 0), 1e-6);

  function colorFor(node) {
    const t = Math.min(1, (node[colorMetric] || 0) / maxMetric);
    return `color-mix(in srgb, var(--accent) ${(t * 90).toFixed(0)}%, var(--analytics))`;
  }

  const edgeSvg = edges
    .filter((e) => e.count >= minEdgeCount && byName[e.from] && byName[e.to])
    .map((e) => {
      const a = byName[e.from];
      const b = byName[e.to];
      const [x1, y1] = toSvg(a.x, a.y);
      const [x2, y2] = toSvg(b.x, b.y);
      const w = 1 + (e.count / maxEdge) * 7;
      const tooltip = `${escapeHtml(a.short)} → ${escapeHtml(b.short)}: ${e.count} passes`;
      return `<line x1="${x1.toFixed(1)}" y1="${y1.toFixed(1)}" x2="${x2.toFixed(1)}" y2="${y2.toFixed(1)}" stroke="var(--text-dim)" stroke-opacity="0.55" stroke-width="${w.toFixed(1)}" data-tooltip="${tooltip}" pointer-events="all"><title>${tooltip}</title></line>`;
    })
    .join("");

  const nodeSvg = nodes
    .map((n) => {
      const [x, y] = toSvg(n.x, n.y);
      const r = 10 + (n.passes / maxPasses) * 16;
      const tooltip = `${escapeHtml(n.short)}: ${n.passes} passes · betweenness ${(n.betweenness_centrality || 0).toFixed(2)}`;
      return `
      <circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${r.toFixed(1)}" fill="${colorFor(n)}" stroke="var(--panel)" stroke-width="2" data-tooltip="${tooltip}" pointer-events="all"><title>${tooltip}</title></circle>
      <text x="${x.toFixed(1)}" y="${(y - r - 5).toFixed(1)}" text-anchor="middle" font-size="11" font-weight="700" fill="var(--text)">${escapeHtml(n.short)}</text>`;
    })
    .join("");

  return `<svg class="research-chart pitch-chart" viewBox="0 0 ${width} ${height.toFixed(1)}" width="100%" height="${height.toFixed(1)}" role="img" aria-label="Passing network">
    ${outlineSvg}
    ${edgeSvg}
    ${nodeSvg}
    <text x="${margin + 4}" y="${(height - 4).toFixed(1)}" font-size="10" fill="var(--text-dim)">↑ attacking direction</text>
  </svg>`;
}

// A single passage of play (e.g. the buildup to one goal) as a numbered sequence of pass/carry
// arrows on a horizontal pitch -- `steps`: [{type: "pass"|"carry", x1, y1, x2, y2, player}] in
// order. Solid arrows for passes, dashed for carries (on-the-ball dribbles between two touches),
// matching the Opta-style convention. The final step is highlighted as the shot/goal.
export function renderSequenceMap(steps, { width = 640 } = {}) {
  const { toSvg, outlineSvg, height } = horizontalPitch({ width });

  const marker = `
    <marker id="seq-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
      <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--text)" />
    </marker>
    <marker id="seq-arrow-final" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--good)" />
    </marker>`;

  const stepsSvg = steps
    .map((s, i) => {
      const [x1, y1] = toSvg(s.x1, s.y1);
      const [x2, y2] = toSvg(s.x2, s.y2);
      const isLast = i === steps.length - 1;
      const dash = s.type === "carry" ? ` stroke-dasharray="4,4"` : "";
      const color = isLast ? "var(--good)" : "var(--text)";
      const arrowId = isLast ? "seq-arrow-final" : "seq-arrow";
      const tooltip = `${escapeHtml(s.player || "")}${s.type === "carry" ? " (carry)" : ""}`;
      return `
      <line x1="${x1.toFixed(1)}" y1="${y1.toFixed(1)}" x2="${x2.toFixed(1)}" y2="${y2.toFixed(1)}" stroke="${color}" stroke-width="${isLast ? 2.5 : 1.6}"${dash} marker-end="url(#${arrowId})" data-tooltip="${tooltip}" pointer-events="all"><title>${tooltip}</title></line>
      <circle cx="${x1.toFixed(1)}" cy="${y1.toFixed(1)}" r="9" fill="var(--panel)" stroke="${color}" stroke-width="1.5" />
      <text x="${x1.toFixed(1)}" y="${(y1 + 3.5).toFixed(1)}" text-anchor="middle" font-size="9.5" font-weight="700" fill="var(--text)">${i + 1}</text>`;
    })
    .join("");

  return `<svg class="research-chart pitch-chart" viewBox="0 0 ${width} ${height.toFixed(1)}" width="100%" height="${height.toFixed(1)}" role="img" aria-label="Sequence map">
    <defs>${marker}</defs>
    ${outlineSvg}
    ${stepsSvg}
  </svg>`;
}
