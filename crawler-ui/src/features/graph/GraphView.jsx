import { useRef, useEffect, useMemo, useState } from "react";
import * as d3 from "d3";
import { getTheme } from "../../theme";
import { createComponentStyles } from "../../theme/components";

const theme  = getTheme();
const styles = createComponentStyles(theme);

const COLOR_MODES = [
  { id: "state",    label: "State" },
  { id: "depth",    label: "Depth" },
  { id: "priority", label: "Priority" },
];

function ghostKey(c) { return `${c.parent_id}::${c.url}`; }

// ── Small control overlay: color mode, candidate visibility, search ────────
function GraphControls({ colorMode, onColorMode, showCandidates, onToggleCandidates, candidateCount, search, onSearch }) {
  return (
    <div style={{
      position: "absolute", top: 12, left: 12, zIndex: 5,
      display: "flex", flexDirection: "column", gap: 6,
      background: "rgba(10,15,31,0.85)", backdropFilter: "blur(4px)",
      border: `1px solid ${theme.colors.background.border}`, borderRadius: theme.radii.lg,
      padding: "8px 10px", fontFamily: theme.typography.fontMono,
    }}>
      <div style={{ display: "flex", gap: 4 }}>
        {COLOR_MODES.map(m => (
          <button
            key={m.id}
            onClick={() => onColorMode(m.id)}
            style={{
              fontSize: theme.typography.size.xxs, padding: "3px 8px", borderRadius: theme.radii.sm,
              border: "none", cursor: "pointer",
              background: colorMode === m.id ? theme.colors.accent.blueDim : "transparent",
              color: colorMode === m.id ? "#fff" : theme.colors.text.muted,
            }}
          >
            {m.label}
          </button>
        ))}
      </div>

      <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: theme.typography.size.xxs, color: theme.colors.text.muted, cursor: "pointer" }}>
        <input type="checkbox" checked={showCandidates} onChange={e => onToggleCandidates(e.target.checked)} />
        Show excluded candidates ({candidateCount})
      </label>

      <input
        value={search}
        onChange={e => onSearch(e.target.value)}
        placeholder="Filter by URL…"
        style={{
          background: theme.colors.background.primary, border: `1px solid ${theme.colors.background.border}`,
          borderRadius: theme.radii.sm, padding: "4px 6px", fontSize: theme.typography.size.xxs,
          color: theme.colors.text.primary, fontFamily: theme.typography.fontMono, width: 150,
        }}
      />
    </div>
  );
}

export default function GraphView({ nodes, edges, candidates = [], replayIndex, onNodeClick, onBackgroundClick, selectedNodeId }) {
  const svgRef     = useRef(null);
  const simRef     = useRef(null);
  const nodeMapRef = useRef(new Map());
  const edgeSetRef = useRef(new Set());
  const ghostsByParentRef = useRef(new Map());

  const [colorMode, setColorMode] = useState("state");
  const [showCandidates, setShowCandidates] = useState(true);
  const [search, setSearch] = useState("");

  const maxDepth = useMemo(() => {
    let max = 0;
    for (const n of nodes.values()) if (n.depth > max) max = n.depth;
    return max || 1;
  }, [nodes]);

  const depthScale = useMemo(
    () => d3.scaleSequential(d3.interpolateRgb(theme.colors.accent.blueDim, theme.colors.accent.purple)).domain([0, maxDepth]),
    [maxDepth]
  );
  const priorityScale = useMemo(
    () => d3.scaleSequential(d3.interpolateRgb(theme.colors.background.border, theme.colors.accent.gold)).domain([0, 1]),
    []
  );

  const fillFor = (d) => {
    if (colorMode === "depth") return depthScale(d.depth || 0);
    if (colorMode === "priority") return priorityScale(Math.max(0, Math.min(1, d.priority || 0)));
    return theme.colors.state[d.state] || theme.colors.state.CREATED;
  };

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
      .attr("markerWidth", 6)
      .attr("markerHeight", 6)
      .attr("orient", "auto")
      .append("path")
      .attr("d", "M0,-4L8,0L0,4")
      .attr("fill", theme.colors.arrow);

    Object.keys(theme.colors.state.glow).forEach((state) => {
      const filter = defs.append("filter").attr("id", `glow-${state}`);
      filter.append("feGaussianBlur").attr("stdDeviation", "6").attr("result", "blur");
      const merge = filter.append("feMerge");
      merge.append("feMergeNode").attr("in", "blur");
      merge.append("feMergeNode").attr("in", "SourceGraphic");
    });

    const container = svg.append("g").attr("class", "container");

    svg.call(
      d3.zoom()
        .scaleExtent([0.1, 4])
        .on("zoom", e => container.attr("transform", e.transform))
    );
    svg.on("click", () => onBackgroundClick && onBackgroundClick());

    container.append("g").attr("class", "edges");
    container.append("g").attr("class", "ghosts");
    container.append("g").attr("class", "nodes");

    simRef.current = d3.forceSimulation()
      .force("link", d3.forceLink().id(d => d.id).distance(80).strength(0.4))
      .force("charge", d3.forceManyBody().strength(-200))
      .force("center", d3.forceCenter(W / 2, H / 2))
      .force("collision", d3.forceCollide(18))
      .alphaDecay(0.03);

    simRef.current.on("tick", () => {
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

    ghostEnter.append("circle")
      .attr("r", 0)
      .attr("fill", d => theme.colors.state[d.decision === "dropped" ? "DROPPED" : "TRUSTED"])
      .attr("stroke", d => theme.colors.state.label[d.decision === "dropped" ? "DROPPED" : "TRUSTED"])
      .attr("stroke-width", 1)
      .attr("opacity", 0)
      .transition().duration(300)
      .attr("r", 3.5)
      .attr("opacity", 0.85);

    ghostEnter.append("title")
      .text(d => `${d.decision === "dropped" ? "Dropped" : "Trusted, skipped LLM"} — nlp_score=${(d.nlp_score ?? 0).toFixed(2)}\n${d.url}`);

    ghostSel.exit()
      .select("circle").transition().duration(200).attr("r", 0).attr("opacity", 0);
    ghostSel.exit().transition().delay(200).remove();

    // ── Nodes ─────────────────────────────────────────────
    const nodeSel = container.select(".nodes").selectAll("g.node-group").data(d3Nodes, d => d.id);

    const radius = (d) => {
      if (d.state === "EXPANDED") return 14;
      if (d.state === "FETCHED" || d.state === "FILTERED" || d.state === "SCORED") return 10;
      if (d.depth === 0) return 12;
      return 7;
    };

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
      .on("click", (event, d) => {
        event.stopPropagation();
        if (onNodeClick) onNodeClick({ node_id: d.node_id ?? d.id, ...d });
      });

    nodeEnter.append("circle")
      .attr("r", 0)
      .transition().duration(500)
      .attr("r", radius);

    nodeEnter.append("circle")
      .attr("class", "selection-ring")
      .attr("r", 0)
      .attr("fill", "none")
      .attr("stroke", "#ffffff")
      .attr("stroke-width", 2)
      .attr("opacity", 0);

    nodeEnter.append("text")
      .attr("dy", "0.35em")
      .attr("text-anchor", "middle")
      .attr("font-size", theme.typography.size.xxs)
      .attr("font-family", theme.typography.fontMono)
      .attr("fill", theme.colors.nodeText)
      .attr("pointer-events", "none")
      .attr("y", 18)
      .text(d => {
        const url   = d.url || d.id;
        const parts = url.split("/").filter(Boolean);
        const last  = parts[parts.length - 1] || url;
        return last.length > 14 ? last.slice(0, 13) + "…" : last;
      });

    const nodeAll = nodeEnter.merge(nodeSel);

    nodeAll.select("circle:not(.selection-ring)")
      .attr("r", radius)
      .attr("fill", d => fillFor(d))
      .attr("stroke", d => theme.colors.state.label[d.state] || theme.colors.text.secondary)
      .attr("stroke-width", d => d.state === "EXPANDED" ? 2.5 : 1)
      .attr("filter", d => `url(#glow-${d.state || "CREATED"})`)
      .attr("opacity", d => matchesSearch(d) ? dimmed(d.node_id ?? d.id) : 0.08);

    nodeAll.select(".selection-ring")
      .attr("r", d => radius(d) + 4)
      .attr("opacity", d => (d.node_id ?? d.id) === selectedNodeId ? 1 : 0);

    nodeAll.select("text")
      .attr("opacity", d => (matchesSearch(d) ? dimmed(d.node_id ?? d.id) : 0.08));

    nodeSel.exit().remove();

  }, [nodes, edges, liveCandidates, onNodeClick, selectedNodeId, colorMode, neighborhood, searchLower]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div style={styles.graphWrap}>
      <svg ref={svgRef} style={styles.graphSvg} />
      <GraphControls
        colorMode={colorMode} onColorMode={setColorMode}
        showCandidates={showCandidates} onToggleCandidates={setShowCandidates}
        candidateCount={liveCandidates.length}
        search={search} onSearch={setSearch}
      />
      {replayIndex !== null && replayIndex !== undefined && (
        <div style={styles.replayBadge}>
          REPLAY · frame {replayIndex + 1}
        </div>
      )}
    </div>
  );
}
