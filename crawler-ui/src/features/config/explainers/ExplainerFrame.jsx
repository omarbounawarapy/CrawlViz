import { getTheme } from "../../../theme";

const theme = getTheme();
const { text, background } = theme.colors;

import sample from "./sampleData.json";

/** A framed illustration; all of them use the same example crawl, named under the title. */
export default function ExplainerFrame({ title, summary, children }) {
  return (
    <figure style={{
      margin: "8px 0 16px", padding: "12px 14px", maxWidth: 680, background: background.panel,
      border: `1px solid ${background.border}`, borderRadius: theme.radii.lg,
    }}>
      <figcaption style={{ marginBottom: 10 }}>
        <span style={{ display: "block", fontSize: 14, fontWeight: 600, color: text.primary }}>{title}</span>
        <span style={{ display: "block", fontSize: 13, color: text.muted, marginTop: 2 }}>
          Example crawl: target “{sample.strategyTarget.topic}”.
        </span>
      </figcaption>
      {children}
      {summary && (
        <p role="status" style={{ fontSize: 14, color: text.primary, margin: "10px 0 0" }}>{summary}</p>
      )}
    </figure>
  );
}
