// Pure layout and folding logic for the graph plate. No DOM, no d3 selections: testable on its own.

// Radial tree layout. The crawl is a tree (every page has the one page it was found on),
// so each page gets a ring by depth and an angular sector inside its parent's sector.
// Sector widths use a damped weight (leaves^0.85), so a subtree that keeps growing
// nudges its neighbours instead of shoving them around the circle while you watch.
// Returns id -> {x, y} around (0, 0).
export function radialTreeTargets(nodes, aspect = 1.5) {
  const kids = new Map();
  const roots = [];
  for (const n of nodes.values()) {
    const p = n.parent_id && n.parent_id !== n.node_id && nodes.has(n.parent_id) ? n.parent_id : null;
    if (p) { if (!kids.has(p)) kids.set(p, []); kids.get(p).push(n.node_id); } else roots.push(n.node_id);
  }
  const leavesOf = new Map();
  const depthOf = new Map();
  let maxDepth = 1;
  // Iterative post-order, so a deep crawl cannot overflow the call stack.
  const order = [];
  const stack = roots.map((r) => [r, 0]);
  const seen = new Set();
  while (stack.length) {
    const [id, d] = stack.pop();
    if (seen.has(id)) continue;
    seen.add(id);
    depthOf.set(id, d);
    if (d > maxDepth) maxDepth = d;
    order.push(id);
    for (const c of kids.get(id) || []) stack.push([c, d + 1]);
  }
  for (let i = order.length - 1; i >= 0; i--) {
    const id = order[i];
    const cs = (kids.get(id) || []).filter((c) => seen.has(c));
    leavesOf.set(id, cs.length === 0 ? 1 : cs.reduce((sum, c) => sum + leavesOf.get(c), 0));
  }
  // Each ring is as far out as it needs to be for the pages on it to keep their distance: the
  // radius at depth d grows with how many pages sit at depth d, and never less than a step
  // beyond the ring inside it. A dense level spreads outward instead of piling up.
  // With several seeds the first ring is theirs, so every depth sits one ring further out.
  const shift = roots.length === 1 ? 0 : 1;
  const rings = maxDepth + shift;
  const perRing = new Array(rings + 1).fill(0);
  for (const id of order) perRing[depthOf.get(id) + shift] += 1;
  const radiusAt = [0];
  for (let i = 1; i <= rings; i++) {
    radiusAt[i] = Math.max(radiusAt[i - 1] + 72, (perRing[i] * PITCH_PX) / (2 * Math.PI));
  }
  const weight = (id) => Math.pow(leavesOf.get(id) || 1, 0.95);
  const out = new Map();
  const place = (id, a0, a1) => {
    const d = depthOf.get(id) ?? 0;
    const mid = (a0 + a1) / 2 - Math.PI / 2;
    // A lone seed sits at the centre; with several seeds the first ring is their ring.
    const r = radiusAt[d + shift];
    out.set(id, { x: Math.cos(mid) * r * aspect, y: Math.sin(mid) * r });
    const cs = (kids.get(id) || []).filter((c) => depthOf.get(c) === d + 1);
    const total = cs.reduce((sum, c) => sum + weight(c), 0) || 1;
    let a = a0;
    for (const c of cs) { const w = ((a1 - a0) * weight(c)) / total; place(c, a, a + w); a += w; }
  };
  const rootTotal = roots.reduce((sum, r) => sum + weight(r), 0) || 1;
  let a = 0;
  for (const r of roots) { const w = (2 * Math.PI * weight(r)) / rootTotal; place(r, a, a + w); a += w; }
  return out;
}

// ── What a screen can show ──────────────────────────────────────────────────
//
// Everything that decides how much of the plate is drawn comes from three physical facts, named
// once here, instead of a thicket of thresholds:
//   PITCH_PX      the layout keeps neighbouring pages this far apart (container px at zoom 1)
//   MIN_PITCH_PX  a page disc is 10 to 22px across; closer than 20px apart and neighbours touch
//   LABEL         a label's typical box on screen (px), and how much of the screen labels may fill
// A plate is *legible* when its whole-plate zoom keeps pages MIN_PITCH_PX apart. When it is not,
// the least important pages fold into counted nodes until it is.
// The aspect the layout is stretched to: the canvas is wider than tall, and labels need horizontal room.
export function aspectOf(w, h) { return Math.min(2.2, Math.max(1.2, (w || 1) / Math.max(h || 1, 1))); }

export const PITCH_PX = 30;
export const MIN_PITCH_PX = 20;
export const LABEL = { w: 84, h: 14, fill: 0.25, size: 11 };
export const FIT = { padX: 48, padTop: 64, padBottom: 56, marginX: 70, marginTop: 34, marginBottom: 40, maxK: 1.6, minK: 0.02 };

// How many labels the viewport can carry before they stop being readable.
export function labelCapacity(w, h) {
  return Math.max(8, Math.floor((w * h * LABEL.fill) / (LABEL.w * LABEL.h)));
}

// The zoom and offset that show every point (with room for labels) inside the viewport.
export function fitTransform(points, w, h) {
  if (!points.length) return { k: 1, tx: w / 2, ty: h / 2 };
  let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
  for (const p of points) { if (p.x < x0) x0 = p.x; if (p.x > x1) x1 = p.x; if (p.y < y0) y0 = p.y; if (p.y > y1) y1 = p.y; }
  x0 -= FIT.marginX; x1 += FIT.marginX; y0 -= FIT.marginTop; y1 += FIT.marginBottom;
  const availH = h - FIT.padTop - FIT.padBottom;
  const k = Math.min(FIT.maxK, Math.max(FIT.minK, Math.min((w - FIT.padX * 2) / (x1 - x0), availH / (y1 - y0))));
  return { k, tx: w / 2 - (k * (x0 + x1)) / 2, ty: FIT.padTop + availH / 2 - (k * (y0 + y1)) / 2 };
}

// One number for "how much does this page matter": the crawler's rating, how far it got, how
// close to the seed it is. Pages the viewer has pointed at are pinned above everything.
const STAGE_WEIGHT = { EXPANDED: 1, SCORED: 0.6, FILTERED: 0.4, FETCHED: 0.25, CREATED: 0.1 };
export function importanceOf(node, depth, maxPriority) {
  const rel = relevanceOf(node, maxPriority) ?? 0.15;
  return 0.55 * rel + 0.2 * (STAGE_WEIGHT[node.state] ?? 0.1) + 0.25 / (1 + depth);
}

// Fold a crawl down to `keep` (a set of page ids): kept pages stay, every other page is counted
// into one "+N pages" node under its nearest kept ancestor.
export function foldTo(nodes, edges, keep, parentOf) {
  const hiddenUnder = new Map();
  let hidden = 0;
  for (const n of nodes.values()) {
    if (keep.has(n.node_id)) continue;
    hidden += 1;
    let cur = parentOf(n);
    while (cur != null && !keep.has(cur)) cur = parentOf(nodes.get(cur));
    if (cur != null) hiddenUnder.set(cur, (hiddenUnder.get(cur) || 0) + 1);
  }
  const vNodes = new Map();
  for (const n of nodes.values()) if (keep.has(n.node_id)) vNodes.set(n.node_id, n);
  const vEdges = new Set();
  for (const e of edges) {
    const [src, tgt] = e.split("→");
    if (keep.has(src) && keep.has(tgt)) vEdges.add(e);
  }
  for (const [parent, count] of hiddenUnder) {
    const id = `agg:${parent}`;
    vNodes.set(id, { node_id: id, parent_id: parent, state: "AGGREGATE", isAggregate: true, count, url: `+${count} pages` });
    vEdges.add(`${parent}→${id}`);
  }
  return { nodes: vNodes, edges: vEdges, hidden };
}

// Distance from the seed for every page, by walking parent links (cycle- and orphan-safe).
export function depthsOf(nodes) {
  const depth = new Map();
  for (const start of nodes.keys()) {
    const chain = [];
    let cur = start;
    while (cur != null && !depth.has(cur) && chain.length < 10000) {
      chain.push(cur);
      const n = nodes.get(cur);
      cur = n && n.parent_id && nodes.has(n.parent_id) && n.parent_id !== cur ? n.parent_id : null;
    }
    let d = cur == null ? -1 : depth.get(cur);
    for (let i = chain.length - 1; i >= 0; i--) depth.set(chain[i], ++d);
  }
  return depth;
}

/**
 * Choose what to draw. If the whole crawl is legible at the zoom that fits it on screen, draw
 * all of it. If not, keep the pages the viewer pinned (selection, its neighbourhood, search hits,
 * branches they opened, the seeds) plus as many of the most important others as still leave the
 * plate legible, found by bisection. Kept pages keep their path to the seed.
 */
export function chooseView(nodes, edges, { showAll, expanded, selectedId, neighborhood, search, maxPriority, viewport, aspect = 1.5 }) {
  const pitchOf = (view) => {
    const t = radialTreeTargets(view.nodes, aspect);
    return fitTransform(Array.from(t.values()), viewport.w, viewport.h).k * PITCH_PX;
  };
  const whole = { nodes, edges, hidden: 0, folded: false };
  if (showAll || nodes.size < 2) return { ...whole, pitchPx: pitchOf(whole) };

  const parentOf = (n) => (n.parent_id && nodes.has(n.parent_id) && n.parent_id !== n.node_id ? n.parent_id : null);
  const depth = depthsOf(nodes);

  const legible = (view) => pitchOf(view) >= MIN_PITCH_PX;
  if (legible(whole)) return { ...whole, pitchPx: pitchOf(whole) };

  const pinned = new Set();
  const ranked = [];
  for (const n of nodes.values()) {
    const id = n.node_id;
    const d = depth.get(id) ?? 0;
    if (
      d === 0 || id === selectedId || (neighborhood && neighborhood.has(id)) ||
      (n.parent_id && expanded.has(n.parent_id)) || (search && (n.url || "").toLowerCase().includes(search))
    ) pinned.add(id);
    else ranked.push([importanceOf(n, d, maxPriority), id]);
  }
  ranked.sort((a, b) => b[0] - a[0]);

  const viewWith = (m) => {
    const keep = new Set(pinned);
    for (let i = 0; i < m; i++) keep.add(ranked[i][1]);
    for (const id of Array.from(keep)) {          // a kept page keeps its path to the seed
      let cur = parentOf(nodes.get(id));
      while (cur != null && !keep.has(cur)) { keep.add(cur); cur = parentOf(nodes.get(cur)); }
    }
    return { ...foldTo(nodes, edges, keep, parentOf), folded: true };
  };

  // Largest m that is still legible. Legibility only gets worse as m grows, so bisect.
  let lo = 0, hi = ranked.length;
  while (lo < hi) {
    const mid = Math.ceil((lo + hi) / 2);
    if (legible(viewWith(mid))) lo = mid; else hi = mid - 1;
  }
  const chosen = viewWith(lo);
  return { ...chosen, pitchPx: pitchOf(chosen) };
}

// Relevance in [0,1], or null when the crawler has not judged the node.
// Prefers the LLM score (0-100), falls back to priority scaled by the
// highest priority seen so far.
export function relevanceOf(d, maxPriority) {
  if (typeof d.llm_score === "number") return Math.max(0, Math.min(1, d.llm_score / 100));
  if (typeof d.priority === "number" && maxPriority > 0) return Math.max(0, Math.min(1, d.priority / maxPriority));
  return null;
}


// A link drawn the way a radial tree is drawn: out along the parent's spoke, across at the middle
// ring, in along the child's spoke. Siblings share the start of their path and then fan out, so
// edges read as branches instead of piling up as near-parallel straight lines. The spokes are read
// from where the two pages are *now* (around the centre cx, cy, with the layout's `aspect`
// stretch undone), so a link is always consistent with its endpoints, including while pages are
// moving. Returns [x0, y0, cx1, cy1, cx2, cy2, x1, y1] in container coordinates.
export function edgeCurve(s, g, cx, cy, aspect) {
  const sr = Math.hypot((s.x - cx) / aspect, s.y - cy), gr = Math.hypot((g.x - cx) / aspect, g.y - cy);
  const gA = Math.atan2(g.y - cy, (g.x - cx) / aspect);
  const sA = sr < 1 ? gA : Math.atan2(s.y - cy, (s.x - cx) / aspect);
  const rm = (sr + gr) / 2;
  return [
    s.x, s.y,
    cx + Math.cos(sA) * rm * aspect, cy + Math.sin(sA) * rm,
    cx + Math.cos(gA) * rm * aspect, cy + Math.sin(gA) * rm,
    g.x, g.y,
  ];
}

export function bezierPoint(c, t) {
  const u = 1 - t;
  const a = u * u * u, b = 3 * u * u * t, d = 3 * u * t * t, e = t * t * t;
  return [a * c[0] + b * c[2] + d * c[4] + e * c[6], a * c[1] + b * c[3] + d * c[5] + e * c[7]];
}
