import { describe, it, expect } from "vitest";
import { radialTreeTargets, chooseView, depthsOf, fitTransform, labelCapacity, importanceOf, edgeCurve, bezierPoint, PITCH_PX, MIN_PITCH_PX } from "./layout";

// A crawl as the reducer holds it: nodes by id, edges as "parent→child".
function crawl(rows) {
  const nodes = new Map();
  const edges = new Set();
  for (const [id, parent, score] of rows) {
    nodes.set(id, { node_id: id, parent_id: parent, llm_score: score, state: "SCORED" });
    if (parent) edges.add(`${parent}→${id}`);
  }
  return { nodes, edges };
}

function fan(n, depth = 2) {
  const rows = [["root", null, 90]];
  let i = 0;
  const add = (parent, d) => {
    if (d > depth) return;
    for (let k = 0; k < n; k++) { const id = `n${i++}`; rows.push([id, parent, 20]); add(id, d + 1); }
  };
  add("root", 1);
  return rows;
}

describe("radialTreeTargets", () => {
  it("puts a lone seed at the centre and every page on a ring by depth", () => {
    const { nodes } = crawl([["a", null], ["b", "a"], ["c", "a"], ["d", "b"]]);
    const t = radialTreeTargets(nodes, 1);
    expect(t.get("a")).toEqual({ x: 0, y: 0 });
    const r = (id) => Math.hypot(t.get(id).x, t.get(id).y);
    expect(r("b")).toBeCloseTo(r("c"));
    expect(r("d")).toBeGreaterThan(r("b"));
  });

  it("gives every page a finite, distinct position", () => {
    const { nodes } = crawl(fan(4));
    const t = radialTreeTargets(nodes);
    const seen = new Set();
    for (const p of t.values()) {
      expect(Number.isFinite(p.x) && Number.isFinite(p.y)).toBe(true);
      seen.add(`${Math.round(p.x)},${Math.round(p.y)}`);
    }
    expect(seen.size).toBe(nodes.size);
  });

  it("keeps pages on a busy level apart instead of piling them up", () => {
    const { nodes } = crawl(fan(9, 2));
    const t = [...radialTreeTargets(nodes, 1).values()];
    let min = Infinity;
    for (let i = 0; i < t.length; i++) for (let j = i + 1; j < t.length; j++) min = Math.min(min, Math.hypot(t[i].x - t[j].x, t[i].y - t[j].y));
    expect(min).toBeGreaterThan(14);
  });

  it("keeps existing pages roughly where they were when one more page arrives", () => {
    const base = crawl(fan(4));
    const before = radialTreeTargets(base.nodes);
    const more = crawl([...fan(4), ["extra", "n0", 10]]);
    const after = radialTreeTargets(more.nodes);
    let moved = 0;
    for (const [id, p] of before) {
      const q = after.get(id);
      if (Math.hypot(p.x - q.x, p.y - q.y) > 120) moved += 1;
    }
    expect(moved / before.size).toBeLessThan(0.2);
  });

  it("survives a cycle and an orphan without looping", () => {
    const nodes = new Map([
      ["a", { node_id: "a", parent_id: "b" }],
      ["b", { node_id: "b", parent_id: "a" }],
      ["c", { node_id: "c", parent_id: "missing" }],
    ]);
    expect(() => radialTreeTargets(nodes)).not.toThrow();
  });
});

describe("chooseView", () => {
  const roomy = { w: 1568, h: 609 };
  const opts = (extra = {}) => ({ showAll: false, expanded: new Set(), selectedId: null, neighborhood: null, search: "", maxPriority: 0, viewport: roomy, ...extra });

  it("draws everything while the whole crawl stays legible", () => {
    const { nodes, edges } = crawl(fan(3, 2));
    const v = chooseView(nodes, edges, opts());
    expect(v.folded).toBe(false);
    expect(v.nodes).toBe(nodes);
    expect(v.pitchPx).toBeGreaterThanOrEqual(MIN_PITCH_PX);
  });

  it("folds when pages would be closer than the eye can tell apart, and the result is legible", () => {
    const { nodes, edges } = crawl(fan(6, 3));
    const v = chooseView(nodes, edges, opts());
    expect(v.folded).toBe(true);
    expect(v.pitchPx).toBeGreaterThanOrEqual(MIN_PITCH_PX);
    const aggregates = [...v.nodes.values()].filter((n) => n.isAggregate);
    const shown = v.nodes.size - aggregates.length;
    expect(aggregates.reduce((s, n) => s + n.count, 0)).toBe(v.hidden);
    expect(shown + v.hidden).toBe(nodes.size);
    for (const e of v.edges) {
      const [s, t] = e.split("→");
      expect(v.nodes.has(s) && v.nodes.has(t)).toBe(true);
    }
  });

  it("keeps more of a crawl on a bigger screen, derived from the viewport and not from a constant", () => {
    const { nodes, edges } = crawl(fan(6, 3));
    const small = chooseView(nodes, edges, opts({ viewport: { w: 700, h: 400 } }));
    const big = chooseView(nodes, edges, opts({ viewport: { w: 2400, h: 1200 } }));
    expect(big.nodes.size).toBeGreaterThan(small.nodes.size);
  });

  it("showAll lifts the fold", () => {
    const { nodes, edges } = crawl(fan(6, 3));
    const v = chooseView(nodes, edges, opts({ showAll: true }));
    expect(v.nodes).toBe(nodes);
    expect(v.hidden).toBe(0);
  });

  it("keeps highly rated pages ahead of dull ones, and the path to what it keeps", () => {
    const rows = [["r", null, 90], ["a", "r", 10], ["b", "a", 10]];
    for (let i = 0; i < 200; i++) rows.push([`dull${i}`, "b", 5]);
    rows.push(["gem", "b", 95]);
    const { nodes, edges } = crawl(rows);
    const v = chooseView(nodes, edges, opts({ viewport: { w: 700, h: 400 } }));
    expect(v.folded).toBe(true);
    for (const id of ["r", "a", "b", "gem"]) expect(v.nodes.has(id)).toBe(true);
  });

  it("pins the selection, a search hit, and a branch the viewer opened", () => {
    const rows = [["r", null, 90], ["a", "r", 10], ["b", "a", 10], ["c", "b", 10], ["d", "c", 10]];
    for (let i = 0; i < 300; i++) rows.push([`x${i}`, "b", 60]);
    const { nodes, edges } = crawl(rows);
    nodes.get("d").url = "/wiki/Needle";
    const small = { viewport: { w: 600, h: 360 } };
    expect(chooseView(nodes, edges, opts(small)).nodes.has("d")).toBe(false);
    expect(chooseView(nodes, edges, opts({ ...small, selectedId: "d" })).nodes.has("d")).toBe(true);
    expect(chooseView(nodes, edges, opts({ ...small, search: "needle" })).nodes.has("d")).toBe(true);
    expect(chooseView(nodes, edges, opts({ ...small, expanded: new Set(["c"]) })).nodes.has("d")).toBe(true);
  });
});

describe("the legibility model", () => {
  it("scales label room with the screen", () => {
    expect(labelCapacity(1568, 609)).toBeGreaterThan(labelCapacity(800, 400));
    expect(labelCapacity(10, 10)).toBeGreaterThanOrEqual(8);
  });

  it("fits points inside the viewport at the zoom it reports", () => {
    const pts = [{ x: -500, y: -200 }, { x: 500, y: 200 }];
    const { k, tx, ty } = fitTransform(pts, 1000, 600);
    for (const p of pts) {
      expect(p.x * k + tx).toBeGreaterThan(0);
      expect(p.x * k + tx).toBeLessThan(1000);
      expect(p.y * k + ty).toBeGreaterThan(0);
      expect(p.y * k + ty).toBeLessThan(600);
    }
    expect(k * PITCH_PX).toBeGreaterThan(0);
  });

  it("ranks a rated, expanded, shallow page above an unrated deep one", () => {
    const good = importanceOf({ llm_score: 90, state: "EXPANDED" }, 1, 0);
    const poor = importanceOf({ state: "CREATED" }, 6, 0);
    expect(good).toBeGreaterThan(poor);
  });

  it("measures depth from the seed and survives cycles", () => {
    const { nodes } = crawl([["a", null], ["b", "a"], ["c", "b"]]);
    const d = depthsOf(nodes);
    expect([d.get("a"), d.get("b"), d.get("c")]).toEqual([0, 1, 2]);
    const loop = new Map([["x", { node_id: "x", parent_id: "y" }], ["y", { node_id: "y", parent_id: "x" }]]);
    expect(() => depthsOf(loop)).not.toThrow();
  });
});

describe("edgeCurve", () => {
  it("starts on the parent and ends on the child", () => {
    const c = edgeCurve({ x: 0, y: 0 }, { x: 100, y: 50 }, 0, 0, 1);
    expect(bezierPoint(c, 0)).toEqual([0, 0]);
    expect(bezierPoint(c, 1)).toEqual([100, 50]);
  });

  it("leaves a parent along its own spoke, so siblings share the start of their path", () => {
    const parent = { x: 100, y: 0 };
    const a = edgeCurve(parent, { x: 200, y: 60 }, 0, 0, 1);
    const b = edgeCurve(parent, { x: 200, y: -60 }, 0, 0, 1);
    // first control points both lie on the parent's spoke (angle 0, so y = 0)
    expect(a[3]).toBeCloseTo(0);
    expect(b[3]).toBeCloseTo(0);
    expect(a[2]).toBeCloseTo(b[2]);
  });

  it("always follows where the pages are now, so a link never loops while pages move", () => {
    const parent = { x: 100, y: 0 };
    const child = { x: 220, y: 40 };
    const c = edgeCurve(parent, child, 0, 0, 1);
    // every point on the curve stays inside the box spanned by its four defining points
    const xs = [c[0], c[2], c[4], c[6]], ys = [c[1], c[3], c[5], c[7]];
    for (let u = 0; u <= 1; u += 0.1) {
      const [x, y] = bezierPoint(c, u);
      expect(x).toBeGreaterThanOrEqual(Math.min(...xs) - 1e-9);
      expect(x).toBeLessThanOrEqual(Math.max(...xs) + 1e-9);
      expect(y).toBeGreaterThanOrEqual(Math.min(...ys) - 1e-9);
      expect(y).toBeLessThanOrEqual(Math.max(...ys) + 1e-9);
    }
  });

  it("handles a parent sitting at the centre", () => {
    const c = edgeCurve({ x: 0, y: 0 }, { x: 80, y: 80 }, 0, 0, 1);
    expect(c.every(Number.isFinite)).toBe(true);
  });
});
