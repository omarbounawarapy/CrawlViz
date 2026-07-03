import { useRef, useEffect } from "react";
import * as d3 from "d3";
import { getTheme } from "../../theme";
import { createComponentStyles } from "../../theme/components";

export default function GraphView({ nodes, edges, replayIndex, onNodeClick, selectedNodeId }) {
const svgRef     = useRef(null);
const simRef     = useRef(null);
const nodeMapRef = useRef(new Map());
const edgeSetRef = useRef(new Set());

const theme  = getTheme();
const styles = createComponentStyles(theme);

// ── Initialize simulation ─────────────────────────────────────────────────
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

Object.entries(theme.colors.state.glow).forEach(([state, color]) => {
  const filter = defs.append("filter").attr("id", `glow-${state}`);
  filter.append("feGaussianBlur")
    .attr("stdDeviation", "6")
    .attr("result", "blur");
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

container.append("g").attr("class", "edges");
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
});

}, [theme]);

// ── Sync data ─────────────────────────────────────────────────────────────
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

// ── Edges ─────────────────────────────────────────────
const edgeSel = container.select(".edges")
  .selectAll("line")
  .data(d3Links, d => d.id);

edgeSel.enter().append("line")
  .attr("stroke", theme.colors.edge)
  .attr("stroke-width", 1.2)
  .attr("marker-end", "url(#arrowhead)")
  .attr("opacity", 0)
  .transition().duration(400)
  .attr("opacity", 0.7);

edgeSel.exit().remove();

// ── Nodes ─────────────────────────────────────────────
const nodeSel = container.select(".nodes")
  .selectAll("g.node-group")
  .data(d3Nodes, d => d.id);

const radius = (d) => {
  if (d.state === "EXPANDED") return 14;
  if (d.state === "FETCHED")  return 10;
  if (d.depth === 0)          return 12;
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
      .on("drag", (e, d) => {
        d.fx = e.x; d.fy = e.y;
      })
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

// Selection ring, rendered behind the main circle
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
  .attr("fill", d => theme.colors.state[d.state] || theme.colors.state.CREATED)
  .attr("stroke", d => theme.colors.state.label[d.state] || theme.colors.text.secondary)
  .attr("stroke-width", d => d.state === "EXPANDED" ? 2.5 : 1)
  .attr("filter", d => `url(#glow-${d.state || "CREATED"})`);

nodeAll.select(".selection-ring")
  .attr("r", d => radius(d) + 4)
  .attr("opacity", d => (d.node_id ?? d.id) === selectedNodeId ? 1 : 0);

nodeSel.exit().remove();

}, [nodes, edges, theme, onNodeClick, selectedNodeId]);

return (
  <div style={styles.graphWrap}>
    <svg ref={svgRef} style={styles.graphSvg} />
    {replayIndex !== null && replayIndex !== undefined && (
      <div style={styles.replayBadge}>
        REPLAY · frame {replayIndex + 1}
      </div>
    )}
  </div>
);
}
