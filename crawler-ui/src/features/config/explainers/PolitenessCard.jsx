import { getTheme } from "../../../theme";
import ExplainerFrame from "./ExplainerFrame";
import { politeness } from "./backoffModel";

const theme = getTheme();
const { text } = theme.colors;

const fmt = (v) => (Math.round(v * 100) / 100).toString();

/** The fetch settings as three plain numbers, so the effect of the sliders is visible without a chart. */
export default function PolitenessCard({ cfg, workers, maxRetries, latency }) {
  const p = politeness(cfg, { workers, maxRetries }, latency);
  const minutes = p.requestsPerSecond > 0 ? 100 / p.requestsPerSecond / 60 : null;
  const rows = [
    [
      `At most about ${fmt(p.requestsPerSecond)} requests per second across all workers`,
      p.limitedBy === "min_delay"
        ? "Set by the minimum delay and jitter."
        : `Set by the ${p.inFlight} workers, since each request takes ${fmt(latency)} s.`,
    ],
    [
      minutes === null
        ? "A crawl of 100 pages has no time bound at this pace"
        : `A crawl of 100 pages takes at least ${Math.round(minutes * 10) / 10} minutes at this pace`,
      "Only the fetch time: parsing, scoring and the LLM can make it slower.",
    ],
    [
      `Up to ${p.inFlight} requests in flight at once`,
      "Pipelines › requests › workers.",
    ],
    [
      `A page that keeps failing is tried up to ${p.attempts} time${p.attempts === 1 ? "" : "s"}`,
      "Retries › max request retries, plus the first try.",
    ],
  ];
  return (
    <ExplainerFrame title="Politeness at a glance" summary="Uses your draft, including values you have not saved yet.">
      <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: 8 }}>
        {rows.map(([headline, note]) => (
          <li key={headline} style={{ fontSize: 14, color: text.primary }}>
            {headline}
            <span style={{ display: "block", fontSize: 13, color: text.muted, marginTop: 2 }}>{note}</span>
          </li>
        ))}
      </ul>
    </ExplainerFrame>
  );
}
