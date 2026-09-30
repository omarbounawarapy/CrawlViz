import { useRef, useEffect, useMemo, useState } from "react";
import * as d3 from "d3";
import { getTheme } from "../../theme";
import { createComponentStyles } from "../../theme/components";
import Legend from "./Legend";

const theme  = getTheme();
const styles = createComponentStyles(theme);

const STAGE_ORDER = ["CREATED", "FETCHED", "FILTERED", "SCORED", "EXPANDED"];
const REL = theme.colors.relevance;

function safeDecode(t) { try { return decodeURIComponent(t); } catch { return t; } }

function ghostKey(c) { return `${c.parent_id}::${c.url}`; }

// Relevance in [0,1], or null when the crawler has not judged the node.
// Prefers the LLM score (0-100), falls back to priority scaled by the
// highest priority seen so far.
function relevanceOf(d, maxPriority) {
  if (typeof d.llm_score === "number") return Math.max(0, Math.min(1, d.llm_score / 100));
  if (typeof d.priority === "number" && maxPriority > 0) return Math.max(0, Math.min(1, d.priority / maxPriority));
  return null;
}

// ── Filter bar: URL search + excluded-candidate toggle ─────────────────────
function GraphControls({ showCandidates, onToggleCandidates, candidateCount, search, onSearch }) {
  return (
    <div style={{
      position: "absolute", top: 16, left: 16, zIndex: 5,
      display: "flex", alignItems: "center", gap: 16,
      background: theme.colors.background.panel, border: `1px solid ${theme.colors.background.border}`,
      borderRadius: theme.radii.lg, padding: "8px 12px", fontFamily: theme.typography.fontMono,
    }}>
      <input
        value={search}
        onChange={e => onSearch(e.target.value)}
        placeholder="Find a URL…"
        aria-label="Find a node by URL" className="find-input"
        style={{
          background: "transparent", border: "none", borderBottom: `1px solid ${theme.colors.text.muted}`,
          padding: "3px 2px", fontSize: 13, color: theme.colors.text.primary, width: 180,
        }}
      />
      {candidateCount > 0 && (
        <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, color: theme.colors.text.secondary, cursor: "pointer" }}>
          <input type="checkbox" checked={showCandidates} onChange={e => onToggleCandidates(e.target.checked)} />
          Show {candidateCount} links the crawler skipped
        </label>
      )}
    </div>
  );
}

export default function GraphView({ nodes, edges, candidates = [], replayIndex, onNodeClick, onBackgroundClick, selectedNodeId }) {
  const svgRef     = useRef(null);
  const simRef     = useRef(null);
  const nodeMapRef = useRef(new Map());
  const zoomRef    = useRef(null);
  const userZoomed = useRef(false);
  const edgeSetRef = useRef(new Set());
  const ghostsByParentRef = useRef(new Map());

  const [showCandidates, setShowCandidates] = useState(true);
  const [search, setSearch] = useState("");

  const maxPriority = useMemo(() => {
    let max = 0;
    for (const n of nodes.values()) if (typeof n.priority === "number" && n.priority > max) max = n.priority;
    return max;
  }, [nodes]);

  const fillFor = (d) => theme.colors.state[d.state] || theme.colors.state.CREATED;

  // Neighborhood of the selected node: itself, its ancestor chain to root,
  // and its direct children -- everything else dims (see
  // docs/V2_ARCHITECTURE.md §B.3.4 "highlight neighborhood / path to root").
  const neighborhood = useMemo(() => {
    if (!selectedNodeId) return null;
    const ids = new Set([selectedNodeId]);
    let cur = nodes.get(selectedNodeId);
    while (cur?.parent_id) { ids.add(cur.parent_id); cur = nodes.get(cur.parent_id); }
    for (const n of nodes.values()) if (n.parent_id === selectedNodeId) ids.add(n.node_id);
    return ids;
  }, [selectedNodeId, nodes]);

  const searchLower = search.trim().toLowerCase();

  // Candidates whose URL hasn't (yet) been promoted to a real node --
  // avoids drawing a ghost and a real node for the same link once a
  // "trusted" candidate's NODE_ADDED arrives a moment later.
  const liveCandidates = useMemo(() => {
    if (!showCandidates) return [];
    const existingUrls = new Set(Array.from(nodes.values()).map(n => n.url));
    return candidates.filter(c => !existingUrls.has(c.url) && nodes.has(c.parent_id));
  }, [candidates, nodes, showCandidates]);

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

    const defs = svg.append("defs");

    defs.append("marker")
      .attr("id", "arrowhead")
      .attr("viewBox", "0 -4 8 8")
      .attr("refX", 14)
      .attr("refY", 0)
      .attr("markerWidth", 5)
      .attr("markerHeight", 5)
      .attr("orient", "auto")
      .append("path")
      .attr("d", "M0,-4L8,0L0,4")
      .attr("fill", theme.colors.arrow);

    const container = svg.append("g").attr("class", "container");

    const zoom = d3.zoom()
      .scaleExtent([0.1, 4])
      .on("start", e => { if (e.sourceEvent) userZoomed.current = true; })
      .on("zoom", e => container.attr("transform", e.transform));
    svg.call(zoom);
    zoomRef.current = zoom;
    svg.on("click", () => onBackgroundClick && onBackgroundClick());

    container.append("g").attr("class", "edges");
    container.append("g").attr("class", "ghosts");
    container.append("g").attr("class", "nodes");

    simRef.current = d3.forceSimulation()
      .force("link", d3.forceLink().id(d => d.id).distance(95).strength(0.4))
      .force("charge", d3.forceManyBody().strength(-200))
      .force("center", d3.forceCenter(W / 2, H / 2))
      .force("x", d3.forceX(W / 2).strength(0.05))
      .force("y", d3.forceY(H / 2).strength(0.05))
      .force("collision", d3.forceCollide(30))
      .alphaDecay(0.03);

    // Keep the whole graph in view until the user pans or zooms themselves.
    let tickCount = 0;
    const fitToView = () => {
      const pts = Array.from(nodeMapRef.current.values()).filter(n => Number.isFinite(n.x));
      if (pts.length === 0 || !zoomRef.current) return;
      const w = svgRef.current.clientWidth || W, h = svgRef.current.clientHeight || H;
      const x0 = d3.min(pts, n => n.x), x1 = d3.max(pts, n => n.x);
      const y0 = d3.min(pts, n => n.y), y1 = d3.max(pts, n => n.y);
      const padX = 140, padY = 120;   // room for labels, the key and the filter bar
      const k = Math.min(1.6, Math.max(0.3, Math.min((w - padX * 2) / Math.max(x1 - x0, 1), (h - padY * 2) / Math.max(y1 - y0, 1))));
      const tx = w / 2 - k * (x0 + x1) / 2, ty = h / 2 - k * (y0 + y1) / 2;
      svg.transition().duration(300).call(zoomRef.current.transform, d3.zoomIdentity.translate(tx, ty).scale(k));
    };

    // Hide the lower-relevance label wherever two labels would overlap.
    const declutter = () => {
      const labels = svg.selectAll("text.label").filter(function () { return this.getAttribute("opacity") !== "0"; });
      labels.style("display", null);
      const items = [];
      labels.each(function (d) { items.push({ el: this, r: d.llm_score ?? d.priority ?? 0, box: this.getBoundingClientRect() }); });
      items.sort((a, b) => b.r - a.r);
      const kept = [];
      for (const it of items) {
        const clash = kept.some(k => !(it.box.right < k.left || it.box.left > k.right || it.box.bottom < k.top || it.box.top > k.bottom));
        if (clash) it.el.style.display = "none"; else kept.push(it.box);
      }
    };

    simRef.current.on("tick", () => {
      tickCount += 1;
      if (!userZoomed.current && tickCount % 20 === 0) fitToView();
      if (tickCount % 20 === 5) declutter();
      container.select(".edges").selectAll("line")
        .attr("x1", d => d.source.x).attr("y1", d => d.source.y)
        .attr("x2", d => d.target.x).attr("y2", d => d.target.y);

      container.select(".nodes").selectAll("g.node-group")
        .attr("transform", d => `translate(${d.x},${d.y})`);

      // Ghosts ride along their parent's live simulation position, fanned
      // out at a small fixed radius rather than participating in the
      // physics themselves -- see module notes above.
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
    });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Sync node/edge data ────────────────────────────────────────────────────
  useEffect(() => {
    if (!simRef.current || !svgRef.current) return;

    const svg       = d3.select(svgRef.current);
    const container = svg.select(".container");

    const nodesArr = Array.from(nodes.values());
    nodesArr.forEach(n => {
      if (!nodeMapRef.current.has(n.node_id)) {
        nodeMapRef.current.set(n.node_id, { id: n.node_id, ...n });
      } else {
        Object.assign(nodeMapRef.current.get(n.node_id), n);
      }
    });
    const d3Nodes = Array.from(nodeMapRef.current.values());

    edges.forEach(e => edgeSetRef.current.add(e));
    const d3Links = Array.from(edges).map(e => {
      const [src, tgt] = e.split("→");
      return { source: src, target: tgt, id: e };
    }).filter(l => nodes.has(l.source));

    simRef.current.nodes(d3Nodes);
    simRef.current.force("link").links(d3Links);
    simRef.current.alpha(0.3).restart();

    const dimmed = (id) => {
      if (neighborhood) return !neighborhood.has(id) ? 0.12 : 1;
      return 1;
    };
    const matchesSearch = (d) => !searchLower || (d.url || "").toLowerCase().includes(searchLower);

    // ── Edges ─────────────────────────────────────────────
    const edgeSel = container.select(".edges").selectAll("line").data(d3Links, d => d.id);
    edgeSel.enter().append("line")
      .attr("stroke", theme.colors.edge)
      .attr("stroke-width", 1.2)
      .attr("marker-end", "url(#arrowhead)")
      .attr("opacity", 0)
      .transition().duration(400).attr("opacity", 0.7);
    edgeSel
      .attr("opacity", d => 0.7 * Math.min(dimmed(d.source.id ?? d.source), dimmed(d.target.id ?? d.target)));
    edgeSel.exit().remove();

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

    const radius = (d) => {
      if (d.depth === 0) return 11;
      const i = STAGE_ORDER.indexOf(d.state);
      return 5 + Math.max(i, 0) * 1.5;
    };
    const relOf = (d) => relevanceOf(d, maxPriority);

    const nodeEnter = nodeSel.enter().append("g")
      .attr("class", "node-group")
      .style("cursor", "pointer")
      .call(
        d3.drag()
          .on("start", (e, d) => {
            if (!e.active) simRef.current.alphaTarget(0.3).restart();
            d.fx = d.x; d.fy = d.y;
          })
          .on("drag", (e, d) => { d.fx = e.x; d.fy = e.y; })
          .on("end", (e, d) => {
            if (!e.active) simRef.current.alphaTarget(0);
            d.fx = null; d.fy = null;
          })
      )
      .attr("tabindex", 0)
      .attr("role", "button")
      .attr("aria-label", d => `Page ${d.url || d.node_id || d.id}`)
      .on("keydown", (event, d) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          if (onNodeClick) onNodeClick({ node_id: d.node_id ?? d.id, ...d });
        }
      })
      .on("click", (event, d) => {
        event.stopPropagation();
        if (onNodeClick) onNodeClick({ node_id: d.node_id ?? d.id, ...d });
      });

    // Relevance ring: the one place vermilion appears. Thicker and denser
    // = the crawler judged this link more promising.
    nodeEnter.append("circle").attr("class", "relevance-ring").attr("fill", "none");

    nodeEnter.append("circle")
      .attr("class", "body")
      .attr("r", 0)
      .transition().duration(500)
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
      .attr("pointer-events", "none");

    nodeEnter.append("line")
      .attr("class", "leader")
      .attr("stroke", REL.mark)
      .attr("stroke-width", 1)
      .attr("pointer-events", "none");

    nodeEnter.append("text")
      .attr("class", "score")
      .attr("text-anchor", "start")
      .attr("font-size", 12)
      .attr("font-weight", 600)
      .attr("font-family", theme.typography.fontData)
      .attr("fill", REL.mark)
      .attr("pointer-events", "none");

    const nodeAll = nodeEnter.merge(nodeSel);
    const vis = (d) => matchesSearch(d) ? dimmed(d.node_id ?? d.id) : 0.1;

    nodeAll.select("circle.relevance-ring")
      .attr("r", d => radius(d) + 3.5)
      .attr("stroke", REL.mark)
      .attr("stroke-width", d => { const r = relOf(d); return r == null ? 0 : 0.75 + r * 3.25; })
      .attr("stroke-opacity", d => { const r = relOf(d); return r == null ? 0 : 0.35 + r * 0.65; })
      .attr("opacity", vis);

    nodeAll.select("circle.body")
      .attr("r", radius)
      .attr("fill", d => fillFor(d))
      .attr("stroke", d => theme.colors.state.label[d.state] || theme.colors.text.secondary)
      .attr("stroke-width", d => d.state === "EXPANDED" ? 2 : 1)
      .attr("opacity", vis);

    nodeAll.select(".selection-ring")
      .attr("r", d => radius(d) + 9)
      .attr("opacity", d => (d.node_id ?? d.id) === selectedNodeId ? 1 : 0);

    // Labels earn their place: seeds, expanded nodes, the selection, and
    // anything the crawler rated highly. Everything else stays quiet.
    const labelled = (d) => d.depth === 0 || d.state === "EXPANDED" || (d.node_id ?? d.id) === selectedNodeId || (relOf(d) ?? 0) >= 0.6;
    nodeAll.select("text.label")
      .attr("y", d => radius(d) + 18)
      .attr("opacity", d => labelled(d) ? vis(d) : 0)
      .text(d => {
        const url   = d.url || d.id;
        const parts = url.split("/").filter(Boolean);
        const last  = safeDecode(parts[parts.length - 1] || url).replace(/_/g, " ");
        return last.length > 22 ? last.slice(0, 21) + "…" : last;
      });

    nodeAll.select("line.leader")
      .attr("x1", d => (radius(d) + 3.5) * 0.71).attr("y1", d => -(radius(d) + 3.5) * 0.71)
      .attr("x2", d => radius(d) + 9).attr("y2", d => -radius(d) - 9)
      .attr("opacity", d => (relOf(d) ?? 0) >= 0.7 ? vis(d) : 0);

    // Score annotation, pinned to the node: only for strongly relevant ones.
    nodeAll.select("text.score")
      .attr("x", d => radius(d) + 11)
      .attr("y", d => -radius(d) - 6)
      .attr("opacity", d => (relOf(d) ?? 0) >= 0.7 ? vis(d) : 0)
      .text(d => `${Math.round((relOf(d) ?? 0) * 100)}`);

    nodeSel.exit().remove();

  }, [nodes, edges, liveCandidates, onNodeClick, selectedNodeId, maxPriority, neighborhood, searchLower]);

  return (
    <div style={styles.graphWrap}>
      <svg ref={svgRef} style={styles.graphSvg} />
      {nodes.size > 0 && <GraphControls
        showCandidates={showCandidates} onToggleCandidates={setShowCandidates}
        candidateCount={liveCandidates.length}
        search={search} onSearch={setSearch}
      />}
      {nodes.size > 0 && <Legend />}
      {replayIndex !== null && replayIndex !== undefined && (
        <div style={styles.replayBadge}>
          Replaying · event {replayIndex + 1}
        </div>
      )}
    </div>
  );
}
