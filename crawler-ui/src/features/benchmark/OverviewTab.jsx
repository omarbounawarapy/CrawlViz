import { fetchBenchmarkOverview } from "../../api/client";
import { getTheme } from "../../theme";
import { SectionTitle, Row } from "../common/Page";
import Loading from "./Loading";
import {useLoad, num} from "./shared";

const { text } = getTheme().colors;

export default function OverviewTab() {
  const state = useLoad(fetchBenchmarkOverview);
  return (
    <Loading state={state}>{(o) => (
      <>
        <SectionTitle>Hypotheses</SectionTitle>
        {o.protocol.hypotheses.map((h) => <Row key={h.id} label={h.id} note={`${h.text} (${h.comparison})`}>{" "}</Row>)}
        <p style={{ fontSize: 13, color: text.muted, marginTop: 10, maxWidth: "66ch" }}>
          Primary metric: {o.protocol.primary_metric}
        </p>

        <SectionTitle>Design</SectionTitle>
        <Row label="Budgets (fetched pages)">{o.protocol.budgets.join(" / ")}</Row>
        {o.protocol.arms.map((a) => (
          <Row key={a.arm} label={a.arm} note={`${a.scopes}; LLM: ${a.llm}`}>{a.repeats}</Row>
        ))}
        {o.protocol.models.map((m) => (
          <Row key={m.role} label={m.role}>{m.provider === "local" || m.provider.startsWith("same") ? m.model : `${m.provider} ${m.model}`}</Row>
        ))}
        <Row label="Result files on disk">{o.runs}</Row>

        {o.protocol.amendments.length > 0 && (
          <>
            <SectionTitle>Amendments</SectionTitle>
            {o.protocol.amendments.map((a) => (
              <details key={a.title} style={{ margin: "6px 0" }}>
                <summary style={{ fontSize: 14, cursor: "pointer" }}>{a.title}</summary>
                <p style={{ fontSize: 13, lineHeight: 1.55, color: text.secondary, maxWidth: "66ch", whiteSpace: "pre-wrap" }}>{a.body}</p>
              </details>
            ))}
          </>
        )}

        {Object.entries(o.graphs).map(([name, g]) => (
          <section key={name} aria-labelledby={`bench-graph-${name}`}>
            <SectionTitle id={`bench-graph-${name}`}>Graph: {name}</SectionTitle>
            <Row label="Pages / edges">{g.pages.toLocaleString()} / {g.edges.toLocaleString()}</Row>
            <Row label="Labels 0 / 1 / 2">{g.labels[0]} / {g.labels[1]} / {g.labels[2]}</Row>
            <Row label="Out-degree mean / median / max">
              {num(g.out_degree.mean, 1)} / {g.out_degree.median} / {g.out_degree.max}
            </Row>
            <Row label="Links to absent pages" note="Zero means the graph is closed (GRAPH_RULE.md).">
              {g.absent_links}
            </Row>
            <Row label="Relevant pages unreachable from the seed">{g.relevant_unreachable}</Row>
            <table style={{ marginTop: 12, fontSize: 13, borderCollapse: "collapse" }}>
              <thead><tr>
                {["Depth", "Pages", "Label 1", "Label 2"].map((h) => (
                  <th scope="col" key={h} style={{ textAlign: "right", padding: "4px 14px", color: text.muted, fontWeight: 600 }}>{h}</th>
                ))}
              </tr></thead>
              <tbody>{g.depth.map((d) => (
                <tr key={d.depth}>
                  <th scope="row" className="num" style={{ textAlign: "right", padding: "4px 14px", fontWeight: 600 }}>{d.depth}</th>
                  {[d.pages, d.label1, d.label2].map((v, i) => (
                    <td key={i} className="num" style={{ textAlign: "right", padding: "4px 14px" }}>{v}</td>
                  ))}
                </tr>
              ))}</tbody>
            </table>
          </section>
        ))}
      </>
    )}</Loading>
  );
}
