import { fetchBenchmarkOverview } from "../../api/client";
import { getTheme } from "../../theme";
import { SectionTitle, Row } from "../common/Page";
import Loading from "./Loading";
import { useLoad, num } from "./shared";

const { text } = getTheme().colors;

const hasProtocol = (protocol) => protocol.hypotheses.length > 0 || protocol.arms.length > 0;

function ProtocolSections({ protocol, runs }) {
  return (
    <>
      <SectionTitle>Hypotheses</SectionTitle>
      {protocol.hypotheses.map((h) => (
        <Row key={h.id} label={h.id} note={`${h.text} (${h.comparison})`}>
          {" "}
        </Row>
      ))}
      <p style={{ fontSize: 13, color: text.muted, marginTop: 10, maxWidth: "66ch" }}>
        Primary metric: {protocol.primary_metric}
      </p>

      <SectionTitle>Design</SectionTitle>
      <Row label="Budgets (fetched pages)">{protocol.budgets.join(" / ")}</Row>
      {protocol.arms.map((a) => (
        <Row key={a.arm} label={a.arm} note={`${a.scopes}; LLM: ${a.llm}`}>
          {a.repeats}
        </Row>
      ))}
      {protocol.models.map((m) => (
        <Row key={m.role} label={m.role}>
          {m.provider === "local" || m.provider.startsWith("same") ? m.model : `${m.provider} ${m.model}`}
        </Row>
      ))}
      <Row label="Result files on disk">{runs}</Row>

      {protocol.amendments.length > 0 && (
        <>
          <SectionTitle>Amendments</SectionTitle>
          {protocol.amendments.map((a) => (
            <details key={a.title} style={{ margin: "6px 0" }}>
              <summary style={{ fontSize: 14, cursor: "pointer" }}>{a.title}</summary>
              <p
                style={{
                  fontSize: 13,
                  lineHeight: 1.55,
                  color: text.secondary,
                  maxWidth: "66ch",
                  whiteSpace: "pre-wrap",
                }}
              >
                {a.body}
              </p>
            </details>
          ))}
        </>
      )}
    </>
  );
}

export default function OverviewTab() {
  const state = useLoad(fetchBenchmarkOverview);
  return (
    <Loading state={state}>
      {(o) => (
        <>
          {hasProtocol(o.protocol) ? (
            <ProtocolSections protocol={o.protocol} runs={o.runs} />
          ) : (
            <p style={{ fontSize: 14, color: text.muted, maxWidth: "66ch" }}>
              No study protocol has been written yet, so there are no hypotheses or arms to show. The graphs below are
              still available.
            </p>
          )}

          {Object.entries(o.graphs).map(([name, g]) => (
            <section key={name} aria-labelledby={`bench-graph-${name}`}>
              <SectionTitle id={`bench-graph-${name}`}>Graph: {name}</SectionTitle>
              <Row label="Pages / edges">
                {g.pages.toLocaleString()} / {g.edges.toLocaleString()}
              </Row>
              <Row label="Labels 0 / 1 / 2">
                {g.labels[0]} / {g.labels[1]} / {g.labels[2]}
              </Row>
              <Row label="Out-degree mean / median / max">
                {num(g.out_degree.mean, 1)} / {g.out_degree.median} / {g.out_degree.max}
              </Row>
              <Row label="Links to absent pages" note="Zero means the graph is closed (GRAPH_RULE.md).">
                {g.absent_links}
              </Row>
              <Row label="Relevant pages unreachable from the seed">{g.relevant_unreachable}</Row>
              <table style={{ marginTop: 12, fontSize: 13, borderCollapse: "collapse" }}>
                <thead>
                  <tr>
                    {["Depth", "Pages", "Label 1", "Label 2"].map((h) => (
                      <th
                        scope="col"
                        key={h}
                        style={{ textAlign: "right", padding: "4px 14px", color: text.muted, fontWeight: 600 }}
                      >
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {g.depth.map((d) => (
                    <tr key={d.depth}>
                      <th
                        scope="row"
                        className="num"
                        style={{ textAlign: "right", padding: "4px 14px", fontWeight: 600 }}
                      >
                        {d.depth}
                      </th>
                      {[d.pages, d.label1, d.label2].map((v, i) => (
                        <td key={i} className="num" style={{ textAlign: "right", padding: "4px 14px" }}>
                          {v}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          ))}
        </>
      )}
    </Loading>
  );
}
