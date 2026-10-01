import { useRef, useEffect, useMemo, useState, useDeferredValue } from "react";
import * as d3 from "d3";
import { getTheme } from "../../theme";
import { createComponentStyles } from "../../theme/components";
import Legend from "./Legend";
import {
  radialTreeTargets, chooseView, depthsOf, importanceOf, relevanceOf, edgeCurve, aspectOf, fitTransform,
  labelCapacity, LABEL, MIN_PITCH_PX,
} from "./layout";

const theme  = getTheme();
const styles = createComponentStyles(theme);


// How many pages the eye can follow gliding to new places; beyond it they are placed directly.
const MAX_ANIMATED = 300;
// A link needs this many screen pixels to carry a readable arrowhead.
const ARROW_MIN_PX = 40;
// The lowest rating that earns a printed score (the plate prints the ones that matter).
const SCORE_MIN = 0.5;
// Folded "+N pages" nodes rank just above unremarkable pages, so they usually get a label.
const AGGREGATE_IMPORTANCE = 0.3;
// Zoom limits and the step a button or key takes (each press is one multiplicative step).
const ZOOM_MIN = 0.02, ZOOM_MAX = 4, ZOOM_STEP = 1.4;
const STAGE_ORDER = ["CREATED", "FETCHED", "FILTERED", "SCORED", "EXPANDED"];
const REL = theme.colors.relevance;

function safeDecode(t) { try { return decodeURIComponent(t); } catch { return t; } }

function ghostKey(c) { return `${c.parent_id}::${c.url}`; }

// ── Filter bar: URL search + excluded-candidate toggle + fold control ──────
function GraphControls({ showCandidates, onToggleCandidates, candidateCount, search, onSearch, fold }) {
  return (
    <div style={{
      position: "absolute", top: 16, left: 16, zIndex: 5,
      display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap", maxWidth: "calc(100% - 32px)",
      background: theme.colors.background.panel, border: `1px solid ${theme.colors.background.border}`,
      borderRadius: theme.radii.lg, padding: "8px 12px", fontFamily: theme.typography.fontMono,
    }}>
      <input
        value={search}
        onChange={e => onSearch(e.target.value)}
        placeholder="Find a URL…"
        aria-label="Find a node by URL" className="find-input"
        style={{
          background: "transparent", borderTop: "none", borderLeft: "none", borderRight: "none", borderBottom: `1px solid ${theme.colors.text.muted}`,
          padding: "3px 2px", fontSize: 13, color: theme.colors.text.primary, width: 180,
        }}
      />
      {candidateCount > 0 && (
        <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, color: theme.colors.text.secondary, cursor: "pointer" }}>
          <input type="checkbox" checked={showCandidates} onChange={e => onToggleCandidates(e.target.checked)} />
          Show {candidateCount} links the crawler skipped
        </label>
      )}
      {fold && (
        <span style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 13, color: theme.colors.text.secondary }}>
          {fold.folded
            ? <>Showing the {fold.shown.toLocaleString()} most important of {fold.total.toLocaleString()} pages, so each stays legible.</>
            : <>Showing all {fold.total.toLocaleString()} pages.</>}
          <button type="button" onClick={fold.onToggle} style={{
            height: 26, padding: "0 10px", borderRadius: theme.radii.md, fontSize: 12, fontWeight: 600,
            background: "transparent", color: theme.colors.text.primary, border: `1px solid ${theme.colors.text.primary}`,
          }}>
            {fold.folded ? "Show all" : "Fold to important"}
          </button>
        </span>
      )}
    </div>
  );
}


// ── Zoom utility: step in and out, fit everything, centre on the selection ──
const ZOOM_ICONS = {
  in: <><path d="M3 8h10" /><path d="M8 3v10" /></>,
  out: <path d="M3 8h10" />,
  fit: <><path d="M2.5 6V2.5H6" /><path d="M10 2.5h3.5V6" /><path d="M13.5 10v3.5H10" /><path d="M6 13.5H2.5V10" /></>,
  focus: <><circle cx="8" cy="8" r="2.2" /><path d="M8 1.5v3" /><path d="M8 11.5v3" /><path d="M1.5 8h3" /><path d="M11.5 8h3" /></>,
};

function ZoomButton({ label, icon, onClick, disabled, shortcut }) {
  return (
    <button
      type="button" onClick={onClick} disabled={disabled} aria-label={label} title={shortcut ? `${label} (${shortcut})` : label}
      style={{
        width: 30, height: 30, display: "inline-flex", alignItems: "center", justifyContent: "center", padding: 0,
        borderRadius: theme.radii.md, background: "transparent",
        border: `1px solid ${disabled ? theme.colors.background.border : theme.colors.text.primary}`,
        color: disabled ? theme.colors.text.muted : theme.colors.text.primary,
      }}
    >
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        {ZOOM_ICONS[icon]}
      </svg>
    </button>
  );
}

function ZoomControls({ k, canFocus, onIn, onOut, onFit, onFocus }) {
  return (
    <div role="group" aria-label="Zoom" style={{
      position: "absolute", right: 16, bottom: 16, zIndex: 5, display: "flex", flexDirection: "column", alignItems: "stretch", gap: 4,
      background: theme.colors.background.panel, border: `1px solid ${theme.colors.background.border}`,
      borderRadius: theme.radii.lg, padding: 6, fontFamily: theme.typography.fontMono,
    }}>
      <output className="num" aria-label="Zoom level" style={{ fontSize: 12, textAlign: "center", color: theme.colors.text.secondary, padding: "2px 0 4px" }}>
        {Math.round(k * 100)}%
      </output>
      <ZoomButton label="Zoom in" icon="in" shortcut="+" onClick={onIn} disabled={k >= ZOOM_MAX * 0.99} />
      <ZoomButton label="Zoom out" icon="out" shortcut="-" onClick={onOut} disabled={k <= ZOOM_MIN * 1.01} />
      <ZoomButton label="Fit the whole plate" icon="fit" shortcut="0" onClick={onFit} />
      <ZoomButton label="Centre on the selected page" icon="focus" shortcut="F" onClick={onFocus} disabled={!canFocus} />
    </div>
  );
}

// Page geometry, in container units at zoom 1.
function radiusOf(d) {
  if (d.isAggregate) return 6 + Math.min(8, Math.log2(Math.max(d.count, 1)));
  if (d.depth === 0) return 11;
  const i = STAGE_ORDER.indexOf(d.state);
  return 5 + Math.max(i, 0) * 1.5;
}

function labelText(d) {
  if (d.isAggregate) return d.url;
  const url   = d.url || d.id;
  const parts = url.split("/").filter(Boolean);
  const last  = safeDecode(parts[parts.length - 1] || url).replace(/_/g, " ");
  return last.length > 22 ? last.slice(0, 21) + "…" : last;
}

// Annotation text lives in screen space: a fixed size on screen at every zoom, placed by arithmetic on
// screen boxes. Its width is measured once per string.
let measureCtx;
function measurer() {
  if (measureCtx === undefined) {
    // jsdom has no canvas; there the estimate below stands in.
    const real = typeof navigator !== "undefined" && !/jsdom/i.test(navigator.userAgent);
    try { measureCtx = real ? document.createElement("canvas").getContext("2d") : null; } catch { measureCtx = null; }
  }
  return measureCtx;
}
const widthCache = new Map();
function textWidth(str, bold) {
  const key = (bold ? "b" : "n") + str;
  let w = widthCache.get(key);
  if (w == null) {
    const ctx = measurer();
    if (ctx) {
      ctx.font = `${bold ? 600 : 400} ${LABEL.size}px ${bold ? theme.typography.fontData : theme.typography.fontMono}`;
      w = ctx.measureText(str).width;
    } else w = 0;
    if (!w) w = str.length * LABEL.size * 0.6;
    widthCache.set(key, w);
  }
  return w;
}

export default function GraphView({ nodes, edges, candidates = [], replayIndex, onNodeClick, onBackgroundClick, selectedNodeId }) {
  const svgRef     = useRef(null);
  const canvasRef  = useRef(null);
  const engineRef  = useRef(null);
  const nodeMapRef = useRef(new Map());
  const zoomRef    = useRef(null);
  const userZoomed = useRef(false);
  const cleanupRef = useRef(null);
  const ghostsByParentRef = useRef(new Map());
  const linksRef   = useRef([]);
  const dimRef     = useRef(() => 1);
  const transformRef = useRef(d3.zoomIdentity);
  const drawRef    = useRef(() => {});
  const cullRef    = useRef(() => {});
  const annotateRef = useRef(() => {});
  const centerRef  = useRef({ x: 0, y: 0, aspect: 1.5 });
  const selectedRef = useRef(null);

  const [showCandidates, setShowCandidates] = useState(true);
  const [search, setSearch] = useState("");
  const [showAll, setShowAll] = useState(false);
  const [expanded, setExpanded] = useState(() => new Set());
  const [size, setSize] = useState({ w: 1200, h: 600 });
  const [zoomK, setZoomK] = useState(1);

  // The viewport decides how much of a big crawl can be legible, so the view needs its size.
  useEffect(() => {
    const el = svgRef.current;
    if (!el || typeof ResizeObserver === "undefined") return undefined;
    const ro = new ResizeObserver(() => {
      const w = el.clientWidth, h = el.clientHeight;
      if (w && h) setSize(prev => (prev.w === w && prev.h === h ? prev : { w, h }));
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const maxPriority = useMemo(() => {
    let max = 0;
    for (const n of nodes.values()) if (typeof n.priority === "number" && n.priority > max) max = n.priority;
    return max;
  }, [nodes]);

  const fillFor = (d) => d.isAggregate ? theme.colors.background.primary : (theme.colors.state[d.state] || theme.colors.state.CREATED);

  // Neighborhood of the selected node: itself, its ancestor chain to root,
  // and its direct children -- everything else dims.
  const neighborhood = useMemo(() => {
    if (!selectedNodeId) return null;
    const ids = new Set([selectedNodeId]);
    let cur = nodes.get(selectedNodeId);
    while (cur?.parent_id) { ids.add(cur.parent_id); cur = nodes.get(cur.parent_id); }
    for (const n of nodes.values()) if (n.parent_id === selectedNodeId) ids.add(n.node_id);
    return ids;
  }, [selectedNodeId, nodes]);

  const searchLower = search.trim().toLowerCase();
  selectedRef.current = selectedNodeId;

  // What to draw. The whole crawl if it stays legible at the zoom that fits it on screen; otherwise
  // the pinned pages plus as many of the most important others as still leave it legible. The heavy
  // part runs at lower priority, so streaming stays responsive.
  const dNodes = useDeferredValue(nodes);
  const dEdges = useDeferredValue(edges);
  const auto = useMemo(
    () => chooseView(dNodes, dEdges, {
      showAll: false, expanded, selectedId: selectedNodeId, neighborhood, search: searchLower, maxPriority,
      viewport: size, aspect: aspectOf(size.w, size.h),
    }),
    [dNodes, dEdges, expanded, selectedNodeId, neighborhood, searchLower, maxPriority, size],
  );
  const folding = auto.folded && !showAll;
  const view = showAll ? { nodes: dNodes, edges: dEdges, hidden: 0, folded: false, pitchPx: 0 } : auto;
  const vNodes = view.nodes;
  const vEdges = view.edges;
  const animate = vNodes.size <= MAX_ANIMATED;

  // Candidates whose URL hasn't (yet) been promoted to a real node --
  // avoids drawing a ghost and a real node for the same link once a
  // "trusted" candidate's NODE_ADDED arrives a moment later.
  const liveCandidates = useMemo(() => {
    if (!showCandidates) return [];
    const existingUrls = new Set(Array.from(nodes.values()).map(n => n.url));
    // Skipped-link marks are fine detail: show them only where there is room (pages well apart on
    // screen), or around the page you are looking at.
    const roomy = !view.folded && view.pitchPx >= 2 * MIN_PITCH_PX;
    return candidates.filter(c => !existingUrls.has(c.url) && nodes.has(c.parent_id) && (roomy || neighborhood?.has(c.parent_id)));
  }, [candidates, nodes, showCandidates, view.folded, view.pitchPx, neighborhood]);

  useEffect(() => {
    const byParent = new Map();
    liveCandidates.forEach(c => {
      if (!byParent.has(c.parent_id)) byParent.set(c.parent_id, []);
      byParent.get(c.parent_id).push(c);
    });
    ghostsByParentRef.current = byParent;
  }, [liveCandidates]);

  // ── Initialize simulation (once) ──────────────────────────────────────────
  useEffect(() => {
    const svg = d3.select(svgRef.current);
    const W   = svgRef.current.clientWidth  || 800;
    const H   = svgRef.current.clientHeight || 500;

    svg.selectAll("*").remove();
    centerRef.current = { ...centerRef.current, x: W / 2, y: H / 2 };

    const container = svg.append("g").attr("class", "container");
    container.append("g").attr("class", "ghosts");
    container.append("g").attr("class", "nodes");

    // ── Edges live on a canvas under the SVG: thousands of <line>s are the most
    // expensive thing the plate can draw, and a canvas redraws them in one pass.
    // A rule is a hairline: one screen pixel at every zoom. More links, fainter each.
    let drawQueued = false;
    const drawEdges = () => {
      drawQueued = false;
      const cv = canvasRef.current;
      if (!cv) return;
      const dpr = window.devicePixelRatio || 1;
      const w = cv.clientWidth, h = cv.clientHeight;
      if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) {
        cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr);
      }
      const ctx = cv.getContext("2d");
      if (!ctx) return;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);
      const t = transformRef.current;
      const dim = dimRef.current;
      const links = linksRef.current;
      ctx.strokeStyle = theme.colors.edge;
      ctx.fillStyle = theme.colors.arrow;
      ctx.lineWidth = 1;
      const base = Math.min(0.7, Math.max(0.25, 1.25 - 0.3 * Math.log10(links.length + 1)));
      for (const pass of [1, 0]) {
        ctx.globalAlpha = pass === 1 ? base : base * 0.12;
        ctx.beginPath();
        const heads = [];
        const { x: ccx, y: ccy, aspect: asp } = centerRef.current;
        for (const l of links) {
          const s = l.source, g = l.target;
          if (!s || !g || !Number.isFinite(s.x) || !Number.isFinite(g.x)) continue;
          const c = edgeCurve(s, g, ccx, ccy, asp);
          const X = (i) => c[i] * t.k + t.x, Y = (i) => c[i] * t.k + t.y;
          const xs = [X(0), X(2), X(4), X(6)], ys = [Y(1), Y(3), Y(5), Y(7)];
          if (xs.every(v => v < 0) || xs.every(v => v > w) || ys.every(v => v < 0) || ys.every(v => v > h)) continue;
          const full = Math.min(dim(s.id), dim(g.id)) === 1;
          if (full !== (pass === 1)) continue;
          ctx.moveTo(xs[0], ys[0]);
          ctx.bezierCurveTo(xs[1], ys[1], xs[2], ys[2], xs[3], ys[3]);
          // An arrowhead needs room to be read: only on links long enough on screen to carry one.
          if (pass === 1 && Math.hypot(xs[3] - xs[0], ys[3] - ys[0]) >= ARROW_MIN_PX) heads.push(xs[2], ys[2], xs[3], ys[3]);
        }
        ctx.stroke();
        if (heads.length) {
          ctx.beginPath();
          for (let i = 0; i < heads.length; i += 4) {
            const dx = heads[i + 2] - heads[i], dy = heads[i + 3] - heads[i + 1];
            const len = Math.hypot(dx, dy) || 1;
            const ux = dx / len, uy = dy / len;
            const tipX = heads[i + 2] - ux * 14 * t.k, tipY = heads[i + 3] - uy * 14 * t.k;
            const size = 7 * Math.min(t.k, 1.2);
            ctx.moveTo(tipX, tipY);
            ctx.lineTo(tipX - ux * size + uy * size * 0.5, tipY - uy * size - ux * size * 0.5);
            ctx.lineTo(tipX - ux * size - uy * size * 0.5, tipY - uy * size + ux * size * 0.5);
            ctx.closePath();
          }
          ctx.fill();
        }
      }
      ctx.globalAlpha = 1;
    };
    const scheduleDraw = () => { if (!drawQueued) { drawQueued = true; requestAnimationFrame(drawEdges); } };
    drawRef.current = scheduleDraw;

    // ── Viewport culling: pages outside the window are not laid out or painted.
    let cullQueued = false;
    const cull = () => {
      cullQueued = false;
      const all = nodeMapRef.current.size;
      const t = transformRef.current;
      const w = svgRef.current?.clientWidth || W, h = svgRef.current?.clientHeight || H;
      const m = 80;
      const x0 = (-t.x - m) / t.k, x1 = (w - t.x + m) / t.k, y0 = (-t.y - m) / t.k, y1 = (h - t.y + m) / t.k;
      svg.selectAll("g.node-group").each(function (d) {
        const off = all > MAX_ANIMATED && Number.isFinite(d.x) && (d.x < x0 || d.x > x1 || d.y < y0 || d.y > y1);
        if (off !== !!d._culled) { d._culled = off; this.style.display = off ? "none" : null; }
      });
    };
    const scheduleCull = () => { if (!cullQueued) { cullQueued = true; requestAnimationFrame(cull); } };
    cullRef.current = scheduleCull;

    // ── Annotations: scores and labels ──────────────────────────────────────────
    // Placed in one pass, in screen space, once the plate is at rest. The viewport can carry only so
    // many labels (labelCapacity), so the most important pages in view compete for that room. Each
    // annotation tries a few positions around its page and takes the first that is clear of other
    // annotations and of every page; among clear ones it prefers the one crossing the fewest edges.
    // Nothing clear, no annotation: that is the whole rule. Scores go first (they carry the red
    // encoding), the selection is always labelled.
    const shown = new Set();
    let annotateTimer;
    const annotate = () => {
      const el = svgRef.current;
      if (!el) return;
      const w = el.clientWidth, h = el.clientHeight;
      const t = transformRef.current, k = t.k;
      const sel = selectedRef.current;
      const cap = labelCapacity(w, h);
      const CELL = 64;
      const grid = new Map();
      const put = (x, y, w0, h0, item) => {
        for (let i = Math.floor(x / CELL); i <= Math.floor((x + w0) / CELL); i++) {
          for (let j = Math.floor(y / CELL); j <= Math.floor((y + h0) / CELL); j++) {
            const key = i + "," + j;
            (grid.get(key) ?? grid.set(key, []).get(key)).push(item);
          }
        }
      };
      const near = (box) => {
        const out = new Set();
        for (let i = Math.floor(box.l / CELL); i <= Math.floor(box.r / CELL); i++) {
          for (let j = Math.floor(box.t / CELL); j <= Math.floor(box.b / CELL); j++) for (const it of grid.get(i + "," + j) ?? []) out.add(it);
        }
        return out;
      };

      const pages = [];
      for (const d of nodeMapRef.current.values()) {
        if (!Number.isFinite(d.x) || !d.__t) continue;
        const X = d.x * k + t.x, Y = d.y * k + t.y;
        if (X < -30 || X > w + 30 || Y < -30 || Y > h + 30) continue;
        const R = Math.max(2.5, (radiusOf(d) + 3.5) * k);
        pages.push({ d, X, Y, R });
        put(X - R - 2, Y - R - 2, 2 * R + 4, 2 * R + 4, { disc: true, id: d.id, X, Y, r: R + 1.5 });
      }
      const { x: ccx, y: ccy, aspect: asp } = centerRef.current;
      for (const l of linksRef.current) {
        if (!l.source || !l.target || !Number.isFinite(l.source.x) || !Number.isFinite(l.target.x)) continue;
        const c = edgeCurve(l.source, l.target, ccx, ccy, asp);
        for (const u of [0.2, 0.4, 0.6, 0.8]) {
          const v = 1 - u;
          const px = (v * v * v * c[0] + 3 * v * v * u * c[2] + 3 * v * u * u * c[4] + u * u * u * c[6]) * k + t.x;
          const py = (v * v * v * c[1] + 3 * v * v * u * c[3] + 3 * v * u * u * c[5] + u * u * u * c[7]) * k + t.y;
          if (px > -30 && px < w + 30 && py > -30 && py < h + 30) put(px, py, 0, 0, { pt: true, x: px, y: py, a: l.source.id, b: l.target.id });
        }
      }

      const placed = [];
      const free = (box, own) => {
        const pad = 3;
        for (const q of placed) if (!(box.r + pad < q.l || box.l - pad > q.r || box.b + pad < q.t || box.t - pad > q.b)) return -1;
        let edgeHits = 0;
        for (const it of near(box)) {
          if (it.disc) {
            if (it.id === own) continue;
            const nx = Math.max(box.l, Math.min(it.X, box.r)), ny = Math.max(box.t, Math.min(it.Y, box.b));
            if (Math.hypot(nx - it.X, ny - it.Y) < it.r) return -1;
          } else if (it.a !== own && it.b !== own && it.x > box.l && it.x < box.r && it.y > box.t && it.y < box.b) edgeHits += 1;
        }
        return edgeHits;
      };
      const boxOf = (X, Y, dx, dy, anchor, tw) => {
        const x = X + dx;
        const l = anchor === "start" ? x : anchor === "end" ? x - tw : x - tw / 2;
        return { l, r: l + tw, t: Y + dy - LABEL.size, b: Y + dy + 3 };
      };

      const keep = new Set();
      const dim = dimRef.current;
      const pool = pages.filter(p => p.d.__vis === 1 && dim(p.d.id) === 1);
      const rank = (p) => (p.d.id === sel ? Infinity : p.d.imp);
      pool.sort((a, b) => rank(b) - rank(a));
      const top = pool.slice(0, Math.ceil(cap * 1.6));

      // scores: the strongest ratings in view
      const scoreSlots = Math.ceil(cap / 2);
      let nScores = 0;
      for (const p of top) {
        if (nScores >= scoreSlots) break;
        const rel = p.d.__rel;
        if (rel == null || rel < SCORE_MIN) continue;
        const txt = String(Math.round(rel * 100));
        const tw = textWidth(txt, true);
        const dx = p.R + 9, dy = -p.R - 4;
        const box = boxOf(p.X, p.Y, dx, dy, "start", tw);
        if (free(box, p.d.id) < 0) continue;
        placed.push(box);
        nScores += 1;
        const T = p.d.__t;
        T.score.textContent = txt;
        T.score.setAttribute("x", dx / k); T.score.setAttribute("y", dy / k);
        T.score.setAttribute("font-size", LABEL.size / k);
        T.score.style.display = null;
        T.leader.setAttribute("x1", (p.R * 0.71) / k); T.leader.setAttribute("y1", -(p.R * 0.71) / k);
        T.leader.setAttribute("x2", (p.R + 7) / k); T.leader.setAttribute("y2", -(p.R + 7) / k);
        T.leader.setAttribute("stroke-width", 1 / k);
        T.leader.style.display = null;
        keep.add(T.score); keep.add(T.leader);
      }

      // labels, most important first, up to the room the viewport has
      let nLabels = 0;
      for (const p of top) {
        const isSel = p.d.id === sel;
        if (nLabels >= cap && !isSel) break;
        const txt = labelText(p.d);
        const tw = textWidth(txt, false);
        const g = 4;
        const below = { dx: 0, dy: p.R + g + 11, anchor: "middle" };
        const above = { dx: 0, dy: -(p.R + g), anchor: "middle" };
        const right = { dx: p.R + g, dy: 4, anchor: "start" };
        const left = { dx: -(p.R + g), dy: 4, anchor: "end" };
        const len = Math.hypot(p.d.tx ?? 0, p.d.ty ?? 0);
        const ux = len > 1 ? p.d.tx / len : 0, uy = len > 1 ? p.d.ty / len : 1;
        const sideways = Math.abs(ux) > 0.35;
        const spoke = p.d.depth === 0 || p.d.isAggregate || len < 1 ? below
          : sideways ? { dx: Math.sign(ux) * (p.R + g), dy: uy * p.R * 0.5 + 4, anchor: ux > 0 ? "start" : "end" }
          : (uy > 0 ? below : above);
        let best = null;
        for (const c of [spoke, below, above, right, left]) {
          const box = boxOf(p.X, p.Y, c.dx, c.dy, c.anchor, tw);
          const e = free(box, p.d.id);
          if (e < 0) continue;
          if (!best || e < best.e) best = { c, box, e };
          if (e === 0) break;
        }
        if (!best) continue;
        placed.push(best.box);
        nLabels += 1;
        const T = p.d.__t;
        T.label.textContent = txt;
        T.label.setAttribute("x", best.c.dx / k); T.label.setAttribute("y", best.c.dy / k);
        T.label.setAttribute("text-anchor", best.c.anchor);
        T.label.setAttribute("font-size", LABEL.size / k);
        T.label.setAttribute("stroke-width", 3 / k);
        T.label.style.display = null;
        keep.add(T.label);
      }

      for (const e of shown) if (!keep.has(e)) e.style.display = "none";
      shown.clear();
      for (const e of keep) shown.add(e);
    };
    const scheduleAnnotate = (ms = 60) => { clearTimeout(annotateTimer); annotateTimer = setTimeout(annotate, ms); };
    annotateRef.current = scheduleAnnotate;

    const zoom = d3.zoom()
      .scaleExtent([ZOOM_MIN, ZOOM_MAX])
      .extent(() => [[0, 0], [svgRef.current?.clientWidth || W, svgRef.current?.clientHeight || H]])
      .on("start", e => { if (e.sourceEvent) userZoomed.current = true; })
      .on("zoom", e => {
        transformRef.current = e.transform;
        container.attr("transform", e.transform);
        setZoomK(prev => (Math.abs(prev - e.transform.k) / prev > 0.005 ? e.transform.k : prev));
        scheduleDraw();
        scheduleCull();
        scheduleAnnotate();
      });
    svg.call(zoom);
    zoomRef.current = zoom;
    svg.on("click", () => onBackgroundClick && onBackgroundClick());

    // Keep the whole graph in view until the user pans or zooms themselves. It fits to where the pages
    // are going (their goals), not to where they happen to be mid-move.
    const fitToView = () => {
      const pts = [];
      for (const n of nodeMapRef.current.values()) {
        const x = n.gx ?? n.x, y = n.gy ?? n.y;
        if (Number.isFinite(x) && Number.isFinite(y)) pts.push({ x, y });
      }
      if (pts.length === 0 || !zoomRef.current) return;
      const w = svgRef.current.clientWidth || W, h = svgRef.current.clientHeight || H;
      const { k, tx, ty } = fitTransform(pts, w, h);
      svg.transition().duration(300).call(zoomRef.current.transform, d3.zoomIdentity.translate(tx, ty).scale(k));
    };

    // ── Layout engine ────────────────────────────────────────────────────────────
    // The layout is deterministic: the radial tree gives every page a goal (gx, gy). Moving to new goals
    // is a short eased tween from where each page is now, not a physics settle, so it always ends exactly
    // on the goals. (A force simulation that stops early leaves pages half-way, with links looping back
    // on themselves: that is what made folding and unfolding messy.)
    const engine = { raf: 0, start: 0, dur: 0 };
    const paint = () => {
      container.select(".nodes").selectAll("g.node-group").attr("transform", d => `translate(${d.x},${d.y})`);
      // Ghosts ride along their parent, fanned out at a small fixed radius.
      container.select(".ghosts").selectAll("g.ghost-group")
        .attr("transform", (d) => {
          const parent = nodeMapRef.current.get(d.parent_id);
          const px = parent?.x ?? 0, py = parent?.y ?? 0;
          const siblings = ghostsByParentRef.current.get(d.parent_id) || [d];
          const idx = siblings.findIndex(s => ghostKey(s) === ghostKey(d));
          const angle = (2 * Math.PI * Math.max(idx, 0)) / Math.max(siblings.length, 1) - Math.PI / 2;
          const r = 24;
          return `translate(${px + r * Math.cos(angle)},${py + r * Math.sin(angle)})`;
        });
      scheduleDraw();
    };
    const finish = () => { if (!userZoomed.current) fitToView(); scheduleCull(); scheduleAnnotate(0); };
    const step = (now) => {
      const p = engine.dur ? Math.min(1, (now - engine.start) / engine.dur) : 1;
      const e = 1 - Math.pow(1 - p, 3);
      for (const n of nodeMapRef.current.values()) {
        if (n.dragging || n.gx == null) continue;
        n.x = n.x0 + (n.gx - n.x0) * e;
        n.y = n.y0 + (n.gy - n.y0) * e;
      }
      paint();
      if (p < 1) engine.raf = requestAnimationFrame(step); else { engine.raf = 0; finish(); }
    };
    engineRef.current = {
      // Point every page at its new goal and move there over `dur` ms (0 places them at once).
      retarget(dur) {
        const { x: cx, y: cy } = centerRef.current;
        for (const n of nodeMapRef.current.values()) {
          if (n.tx == null) continue;
          n.gx = cx + n.tx; n.gy = cy + n.ty;
          if (!Number.isFinite(n.x)) { n.x = n.gx; n.y = n.gy; }
          n.x0 = n.x; n.y0 = n.y;
        }
        engine.dur = dur; engine.start = performance.now();
        if (!userZoomed.current) fitToView();
        if (!engine.raf) engine.raf = requestAnimationFrame(step);
      },
      paint,
      // Zoom utility: step in or out about the middle of the view, fit the whole plate, or centre on a page.
      zoomBy(factor) {
        const el = svgRef.current;
        userZoomed.current = true;
        svg.transition().duration(180).call(zoomRef.current.scaleBy, factor, [el.clientWidth / 2, el.clientHeight / 2]);
      },
      fit() { userZoomed.current = false; fitToView(); },
      focusOn(id) {
        const n = nodeMapRef.current.get(id);
        const el = svgRef.current;
        if (!n || !Number.isFinite(n.x)) return;
        const k = Math.min(ZOOM_MAX, Math.max(transformRef.current.k, 1));
        userZoomed.current = true;
        svg.transition().duration(300).call(zoomRef.current.transform, d3.zoomIdentity.translate(el.clientWidth / 2 - k * n.x, el.clientHeight / 2 - k * n.y).scale(k));
      },
      stop() { if (engine.raf) cancelAnimationFrame(engine.raf); engine.raf = 0; },
    };

    // Docking the annotation panel narrows the canvas: keep the graph centred in what is left.
    let resizeTimer;
    const ro = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(() => {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(() => { if (!userZoomed.current) fitToView(); scheduleDraw(); scheduleAnnotate(); }, 120);
    });
    ro?.observe(svgRef.current);
    cleanupRef.current = () => { ro?.disconnect(); clearTimeout(resizeTimer); clearTimeout(annotateTimer); engineRef.current?.stop(); };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => () => { cleanupRef.current?.(); }, []);

  // ── Sync node/edge data ────────────────────────────────────────────────────
  useEffect(() => {
    if (!engineRef.current || !svgRef.current) return;

    const svg       = d3.select(svgRef.current);
    const container = svg.select(".container");

    // Scrubbing the replay (or folding) removes nodes from the view: drop them from the
    // simulation too, or they linger on the plate, unconnected, as scattered strays.
    for (const id of Array.from(nodeMapRef.current.keys())) {
      if (!vNodes.has(id)) nodeMapRef.current.delete(id);
    }
    Array.from(vNodes.values()).forEach(n => {
      const known = nodeMapRef.current.get(n.node_id);
      if (known) { Object.assign(known, n); return; }
      // A new page appears beside the page it was found on, so the graph grows outward
      // from its parent instead of flying in from the corner of the canvas.
      const parent = n.parent_id ? nodeMapRef.current.get(n.parent_id) : null;
      const seeded = parent && Number.isFinite(parent.x)
        ? { x: parent.x + (Math.random() - 0.5) * 30, y: parent.y + (Math.random() - 0.5) * 30 }
        : {};
      nodeMapRef.current.set(n.node_id, { id: n.node_id, ...n, ...seeded });
    });
    const d3Nodes = Array.from(nodeMapRef.current.values());
    const box = svgRef.current;
    const aspect = aspectOf(box.clientWidth, box.clientHeight);
    const targets = radialTreeTargets(vNodes, aspect);
    centerRef.current = { ...centerRef.current, aspect };
    const depths = depthsOf(vNodes);
    d3Nodes.forEach((n) => {
      const t = targets.get(n.id);
      if (t) {
        n.tx = t.x; n.ty = t.y;
      }
      n.imp = n.isAggregate ? AGGREGATE_IMPORTANCE : importanceOf(n, depths.get(n.id) ?? 0, maxPriority);
      n.__rel = n.isAggregate ? null : relevanceOf(n, maxPriority);
    });

    const d3Links = [];
    for (const e of vEdges) {
      const [src, tgt] = e.split("→");
      const source = nodeMapRef.current.get(src), target = nodeMapRef.current.get(tgt);
      if (source && target) d3Links.push({ source, target, id: e });
    }
    linksRef.current = d3Links;

    // Nobody can follow hundreds of pages moving at once, and each frame costs thousands of DOM writes:
    // past what the eye can track, place pages directly. Otherwise they glide to their new places.
    engineRef.current.retarget(animate ? 450 : 0);

    const baseId = (id) => (String(id).startsWith("agg:") ? String(id).slice(4) : id);
    // Focus: what the selection does not touch recedes.
    const dimmed = (id) => {
      if (neighborhood) return !neighborhood.has(baseId(id)) ? (animate ? 0.12 : 0.03) : 1;
      return 1;
    };
    dimRef.current = dimmed;
    const matchesSearch = (d) => !searchLower || (d.url || "").toLowerCase().includes(searchLower);

    // ── Candidate ghosts ────────────────────────────────────
    const ghostSel = container.select(".ghosts").selectAll("g.ghost-group")
      .data(liveCandidates, ghostKey);

    const ghostEnter = ghostSel.enter().append("g")
      .attr("class", "ghost-group")
      .style("cursor", "default");

    // Dropped = hollow dashed square; trusted (no LLM) = filled diamond.
    ghostEnter.append("path")
      .attr("d", d => d3.symbol().type(d.decision === "dropped" ? d3.symbolSquare : d3.symbolDiamond).size(0)())
      .attr("fill", d => d.decision === "dropped" ? theme.colors.background.primary : theme.colors.state.TRUSTED)
      .attr("stroke", d => theme.colors.state.label[d.decision === "dropped" ? "DROPPED" : "TRUSTED"])
      .attr("stroke-width", 1)
      .attr("stroke-dasharray", d => d.decision === "dropped" ? "2 1.5" : null)
      .attr("opacity", 0)
      .transition().duration(300)
      .attr("d", d => d3.symbol().type(d.decision === "dropped" ? d3.symbolSquare : d3.symbolDiamond).size(d.decision === "dropped" ? 34 : 46)())
      .attr("opacity", 1);

    ghostEnter.append("title")
      .text(d => `${d.decision === "dropped" ? "Skipped: judged off-topic" : "Followed on NLP alone, no LLM call"} (NLP score ${(d.nlp_score ?? 0).toFixed(2)})\n${d.url}`);

    ghostSel.exit()
      .select("path").transition().duration(200).attr("opacity", 0);
    ghostSel.exit().transition().delay(200).remove();

    // ── Nodes ─────────────────────────────────────────────
    const nodeSel = container.select(".nodes").selectAll("g.node-group").data(d3Nodes, d => d.id);

    const radius = radiusOf;
    const relOf = (d) => (d.isAggregate ? null : relevanceOf(d, maxPriority));
    const activate = (d) => {
      if (d.isAggregate) {
        setExpanded(prev => { const next = new Set(prev); next.add(d.parent_id); return next; });
      } else if (onNodeClick) {
        onNodeClick({ node_id: d.node_id ?? d.id, ...d });
      }
    };

    const nodeEnter = nodeSel.enter().append("g")
      .attr("class", "node-group")
      .style("cursor", "pointer")
      .call(
        d3.drag()
          .clickDistance(4)   // a click is not a drag: do not reheat the layout for it
          .on("start", (e, d) => { d.dragging = true; })
          .on("drag", (e, d) => { d.x = e.x; d.y = e.y; engineRef.current.paint(); })
          // Let go and the page returns to its place in the tree.
          .on("end", (e, d) => { d.dragging = false; engineRef.current.retarget(250); })
      )
      .attr("tabindex", 0)
      .attr("role", "button")
      .attr("aria-label", d => d.isAggregate ? `Show ${d.count} more pages` : `Page ${d.url || d.node_id || d.id}`)
      .on("keydown", (event, d) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          activate(d);
        }
      })
      .on("click", (event, d) => {
        event.stopPropagation();
        activate(d);
      });

    // Relevance ring: the one place vermilion appears. Thicker and denser
    // = the crawler judged this link more promising.
    nodeEnter.append("circle").attr("class", "relevance-ring").attr("fill", "none");

    nodeEnter.append("circle")
      .attr("class", "body")
      .attr("r", 0)
      .transition().duration(animate ? 500 : 0)
      .attr("r", radius);

    nodeEnter.append("circle")
      .attr("class", "selection-ring")
      .attr("r", 0)
      .attr("fill", "none")
      .attr("stroke", theme.colors.text.primary)
      .attr("stroke-width", 1.5)
      .attr("stroke-dasharray", "3 2")
      .attr("opacity", 0);

    nodeEnter.append("text")
      .attr("class", "label")
      .attr("text-anchor", "middle")
      .attr("font-size", 12)
      .attr("font-family", theme.typography.fontMono)
      .attr("fill", theme.colors.nodeText)
      .attr("stroke", theme.colors.background.primary)
      .attr("stroke-width", 3)
      .attr("paint-order", "stroke")
      .attr("pointer-events", "none")
      .style("display", "none");

    nodeEnter.append("line")
      .attr("class", "leader")
      .attr("stroke", REL.mark)
      .attr("stroke-width", 1)
      .attr("pointer-events", "none")
      .style("display", "none");

    nodeEnter.append("text")
      .attr("class", "score")
      .attr("text-anchor", "start")
      .attr("font-size", 12)
      .attr("font-weight", 600)
      .attr("font-family", theme.typography.fontData)
      .attr("fill", REL.mark)
      .attr("pointer-events", "none")
      .style("display", "none");

    const nodeAll = nodeEnter.merge(nodeSel);
    const vis = (d) => matchesSearch(d) ? dimmed(d.node_id ?? d.id) : 0.1;

    // Ring weight, like every rule, is in screen pixels (see global.css): it does not thin out as the plate zooms out.
    nodeAll.select("circle.relevance-ring")
      .attr("r", d => radius(d) + 3.5)
      .attr("stroke", REL.mark)
      .attr("stroke-width", d => { const r = relOf(d); return r == null ? 0 : 0.75 + r * 3.25; })
      .attr("stroke-opacity", d => { const r = relOf(d); return r == null ? 0 : 0.35 + r * 0.65; })
      .attr("opacity", vis);

    nodeAll.select("circle.body")
      .attr("r", radius)
      .attr("fill", d => fillFor(d))
      .attr("stroke", d => d.isAggregate ? theme.colors.text.secondary : (theme.colors.state.label[d.state] || theme.colors.text.secondary))
      .attr("stroke-width", d => d.state === "EXPANDED" ? 2 : 1)
      .attr("stroke-dasharray", d => d.isAggregate ? "3 2" : null)
      .attr("opacity", vis);

    nodeAll.select(".selection-ring")
      .attr("r", d => radius(d) + 9)
      .attr("opacity", d => (d.node_id ?? d.id) === selectedNodeId ? 1 : 0);

    // Handles for the annotation pass, and the page's visibility for it.
    nodeAll.each(function (d) {
      d.__t = { label: this.querySelector("text.label"), score: this.querySelector("text.score"), leader: this.querySelector("line.leader") };
      d.__vis = vis(d);
      d.__t.label.setAttribute("opacity", d.__vis); d.__t.score.setAttribute("opacity", d.__vis);
    });

    nodeSel.exit().remove();
    drawRef.current();
    cullRef.current();
    annotateRef.current(120);

  }, [vNodes, vEdges, liveCandidates, onNodeClick, selectedNodeId, maxPriority, neighborhood, searchLower, animate]);

  // Keyboard: + and - step, 0 fits the plate, F centres on the selection. Ignored while typing.
  useEffect(() => {
    const onKey = (e) => {
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      const t = e.target;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable)) return;
      const eng = engineRef.current;
      if (!eng) return;
      if (e.key === "+" || e.key === "=") { e.preventDefault(); eng.zoomBy(ZOOM_STEP); }
      else if (e.key === "-" || e.key === "_") { e.preventDefault(); eng.zoomBy(1 / ZOOM_STEP); }
      else if (e.key === "0") { e.preventDefault(); eng.fit(); }
      else if ((e.key === "f" || e.key === "F") && selectedRef.current) { e.preventDefault(); eng.focusOn(selectedRef.current); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const fold = auto.folded ? {
    folded: folding,
    shown: dNodes.size - auto.hidden,
    total: dNodes.size,
    onToggle: () => { userZoomed.current = false; setShowAll(v => !v); setExpanded(new Set()); },
  } : null;

  return (
    <div style={styles.graphWrap}>
      <canvas ref={canvasRef} aria-hidden="true" style={{ position: "absolute", inset: 0, width: "100%", height: "100%", pointerEvents: "none" }} />
      <svg ref={svgRef} style={{ ...styles.graphSvg, position: "relative" }} />
      {nodes.size > 0 && <GraphControls
        showCandidates={showCandidates} onToggleCandidates={setShowCandidates}
        candidateCount={liveCandidates.length}
        search={search} onSearch={setSearch} fold={fold}
      />}
      {nodes.size > 0 && <Legend />}
      {nodes.size > 0 && (
        <ZoomControls
          k={zoomK} canFocus={!!selectedNodeId}
          onIn={() => engineRef.current?.zoomBy(ZOOM_STEP)} onOut={() => engineRef.current?.zoomBy(1 / ZOOM_STEP)}
          onFit={() => engineRef.current?.fit()} onFocus={() => selectedNodeId && engineRef.current?.focusOn(selectedNodeId)}
        />
      )}
      {replayIndex !== null && replayIndex !== undefined && (
        <div style={styles.replayBadge}>
          Replaying · event {replayIndex + 1}
        </div>
      )}
    </div>
  );
}
