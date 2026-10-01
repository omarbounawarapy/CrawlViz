// Deterministic illustrative graph for the landing plate. Not crawl data.
function rng(seed) {
  let s = seed >>> 0;
  return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296);
}

export function buildPlate({ seed = 12489193, w = 640, h = 520, branches = 5, cx = 0.46, cy = 0.5, reach = 130 } = {}) {
  const rand = rng(seed);
  const nodes = [{ id: 0, x: w * cx, y: h * cy, depth: 0, score: 1, kind: "seed" }];
  const edges = [];
  let id = 1;
  const grow = (parent, angle, depth, reach) => {
    const count = depth === 1 ? branches : 2 + Math.floor(rand() * 2);
    for (let i = 0; i < count; i++) {
      const spread = depth === 1 ? (Math.PI * 2) / count : 1.25;
      const a = depth === 1 ? angle + i * spread + (rand() - 0.5) * 0.4 : angle + (i - (count - 1) / 2) * 0.55 + (rand() - 0.5) * 0.3;
      const d = reach * (0.75 + rand() * 0.5);
      const x = Math.min(w - 16, Math.max(16, parent.x + Math.cos(a) * d));
      const y = Math.min(h - 16, Math.max(16, parent.y + Math.sin(a) * d));
      const score = Math.max(0.05, Math.min(0.98, 0.9 - depth * 0.18 + (rand() - 0.5) * 0.6));
      const kind = depth === 3 && score < 0.3 ? "dropped" : depth === 3 && score > 0.55 ? "trusted" : "page";
      const n = { id: id++, x, y, depth, score, kind };
      nodes.push(n);
      edges.push([parent.id, n.id]);
      if (depth < 3 && kind !== "dropped") grow(n, a, depth + 1, reach * 0.62);
    }
  };
  grow(nodes[0], -Math.PI / 2 + 0.3, 1, reach);
  const pad = 26;
  const xs = nodes.map((n) => n.x), ys = nodes.map((n) => n.y);
  const box = { x: Math.min(...xs) - pad, y: Math.min(...ys) - pad };
  box.w = Math.max(...xs) + pad - box.x;
  box.h = Math.max(...ys) + pad - box.y;
  return { nodes, edges, w, h, box };
}
