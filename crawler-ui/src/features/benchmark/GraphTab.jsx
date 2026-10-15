import { useMemo, useState, useEffect } from "react";
import { fetchBenchmarkGraph, fetchBenchmarkPage } from "../../api/client";
import { getTheme } from "../../theme";
import { SectionTitle } from "../common/Page";
import { Field, Select } from "../common/Form";
import GraphView from "../graph/GraphView";
import Loading from "./Loading";
import { LABEL, useLoad } from "./shared";

const { text } = getTheme().colors;

/**
 * The frozen graph drawn by the same renderer as a live crawl.
 *
 * The crawl view draws a tree, so the graph is shown as its breadth-first
 * spanning tree. The judge's label rides the "how promising" ring (score 0,
 * 50, 100 for labels 0, 1, 2); every page counts as scored.
 */
function toCrawlState(g) {
  const nodes = new Map();
  const edges = new Set();
  for (const n of g.nodes) {
    nodes.set(n.id, {
      node_id: n.id, parent_id: n.parent, url: n.title, state: "SCORED",
      llm_score: n.label * 50, priority: n.label, title: n.title, depth: n.depth,
    });
    if (n.parent) edges.add(`${n.parent}→${n.id}`);
  }
  return { nodes, edges };
}

export default function GraphTab({ graphName = "isi.json" }) {
  const [depth, setDepth] = useState(1);
  const state = useLoad(() => fetchBenchmarkGraph(graphName, depth, 300), [graphName, depth]);
  return (
    <>
      <Field label="Depth from the seed" hint="Relevant pages are kept first; the view holds at most 300 pages.">
        <Select value={depth} onChange={(e) => setDepth(Number(e.target.value))} style={{ width: 160 }}>
          {[0, 1, 2, 3].map((d) => <option key={d} value={d}>{d}</option>)}
        </Select>
      </Field>
      <Loading state={state}>{(g) => <Plot g={g} graphName={graphName} />}</Loading>
    </>
  );
}

function Plot({ g, graphName }) {
  const { nodes, edges } = useMemo(() => toCrawlState(g), [g]);
  const [sel, setSel] = useState(null);
  const [page, setPage] = useState(null);
  useEffect(() => {
    if (!sel) return undefined;
    let live = true;
    fetchBenchmarkPage(graphName, sel).then((p) => live && setPage(p), () => {});
    return () => { live = false; };
  }, [sel, graphName]);
  const chosen = sel ? nodes.get(sel) : null;

  return (
    <>
      <p style={{ fontSize: 13, color: text.muted, margin: "0 0 8px", maxWidth: "70ch" }}>
        {g.shown} of {g.total.toLocaleString()} pages, drawn as a spanning tree from the seed
        ({g.cross_links.toLocaleString()} other links not drawn). Topic: {g.topic || "n/a"}. Ring and number show the
        judge's label on a 0 to 100 scale: label 1 ({LABEL[1].name}) prints 50, label 2 ({LABEL[2].name}) prints 100,
        label 0 is unmarked. The legend's "how far it got" does not apply here; every page is shown as scored.
      </p>
      <div style={{ position: "relative", height: 520, border: `1px solid ${getTheme().colors.background.border}` }}>
        <GraphView nodes={nodes} edges={edges} candidates={[]} selectedNodeId={sel}
          onNodeClick={(n) => setSel(n.node_id)} onBackgroundClick={() => { setSel(null); setPage(null); }} />
      </div>
      {chosen && (
        <>
          <SectionTitle>{chosen.title}</SectionTitle>
          <p style={{ fontSize: 13, color: text.muted }}>
            Label {chosen.priority} · depth {chosen.depth}
            {page && page.id === sel ? ` · ${page.links.length}${page.links.length >= 60 ? "+" : ""} links` : ""}
          </p>
          {page && page.id === sel && (
            <p style={{ fontSize: 14, lineHeight: 1.5, maxWidth: "66ch", whiteSpace: "pre-wrap" }}>{page.text.slice(0, 900)}</p>
          )}
        </>
      )}
    </>
  );
}
