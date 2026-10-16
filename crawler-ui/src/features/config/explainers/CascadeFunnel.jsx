import { useMemo } from "react";
import { getTheme } from "../../../theme";
import ExplainerFrame from "./ExplainerFrame";
import { cascadeCounts } from "./cascadeModel";
import sample from "./sampleData.json";

const theme = getTheme();
const { text } = theme.colors;
const W = 600, HIST_H = 90, BINS = 20;
const ZONE = { low: "#e3e8ee", mid: "#aab4c0", high: "#33435a" };

const f = (v) => (Math.round(v * 100) / 100).toString();

/**
 * One page of 40 example links, split by the two cut-offs, then what the
 * cascade does with each part. `cfg` is the live draft's `scoring_cascade`.
 */
export default function CascadeFunnel({ cfg }) {
  const c = useMemo(() => {
    if (typeof cfg?.low_threshold !== "number") return null;
    return cascadeCounts(sample.cascadeScores, { ...cfg, max_llm_links: cfg.max_llm_links_per_node });
  }, [cfg]);
  const bins = useMemo(() => {
    const out = Array.from({ length: BINS }, () => []);
    sample.cascadeScores.forEach((s) => out[Math.min(BINS - 1, Math.floor(s * BINS))].push(s));
    return out;
  }, []);
  if (!c) return null;

  const x = (v) => Math.max(0, Math.min(1, v)) * W;
  const peak = Math.max(...bins.map((b) => b.length), 1);
  const zoneOf = (mid) => (mid < c.lowCut ? "low" : mid > c.highCut ? "high" : "mid");

  const rows = [
    { label: "Low: dropped", n: c.lowDropped, fill: ZONE.low },
    { label: "Low: kept to explore", n: c.lowKept, fill: "#8794a5", llm: true },
    { label: "Middle band: always to the LLM", n: c.mid, fill: ZONE.mid, llm: true },
    { label: "High: random picks to the LLM", n: c.highRandom, fill: "#56657a", llm: true },
    { label: "High: top-ranked to the LLM", n: c.highTop, fill: "#56657a", llm: true },
    { label: "High: trusted, no LLM", n: c.highTrusted, fill: ZONE.high },
  ];
  const labelW = 250, barW = W - labelW - 40;

  const summary = `Of ${c.total} links: ${c.dropped} dropped, ${c.toLlm} sent to the LLM, ${c.trusted} trusted without one.`
    + (c.capped ? ` ${c.capped} more were held back by the per-page cap.` : "");

  return (
    <ExplainerFrame title="What the cascade does with one page" summary={summary}>
      <svg viewBox={`0 0 ${W} ${HIST_H + 64}`} width="100%" role="img"
           aria-label={`Histogram of ${c.total} example link scores. Cut-offs at ${f(c.lowCut)} and ${f(c.highCut)}.`}>
        {bins.map((b, i) => {
          const h = (b.length / peak) * HIST_H;
          const mid = (i + 0.5) / BINS;
          return (
            <rect key={i} x={x(i / BINS) + 1} y={HIST_H - h} width={W / BINS - 2} height={h}
                  fill={ZONE[zoneOf(mid)]} />
          );
        })}
        {[c.lowCut, c.highCut].map((v, i) => (
          <g key={i}>
            <line x1={x(v)} x2={x(v)} y1="0" y2={HIST_H + 6} stroke={text.primary} strokeWidth="2" />
            <text x={x(v)} y={HIST_H + 20} textAnchor="middle" fontSize="13" fill={text.primary}>{f(v)}</text>
          </g>
        ))}
        <text x="0" y={HIST_H + 40} fontSize="12" fill={text.muted}>0 (weakest)</text>
        <text x={W} y={HIST_H + 40} textAnchor="end" fontSize="12" fill={text.muted}>1 (strongest)</text>
        <text x={W / 2} y={HIST_H + 40} textAnchor="middle" fontSize="12" fill={text.secondary}>
          NLP similarity score of each link, from 0 to 1 (bars: number of links)
        </text>
        {c.usedPercentiles && (
          <text x={W / 2} y={HIST_H + 56} textAnchor="middle" fontSize="12" fill={text.muted}>
            cut-offs moved to this page&apos;s own percentiles
          </text>
        )}
      </svg>
      {cfg.percentile_bucketing && !c.usedPercentiles && (
        <p style={{ fontSize: 13, color: text.muted, margin: "4px 0 0" }}>
          This page has fewer than {cfg.percentile_min_links} links, so the fixed cut-offs apply.
        </p>
      )}
      <p style={{ fontSize: 13, color: text.secondary, margin: "10px 0 0" }}>
        Links on this page by what happens to them, out of {c.total}:
      </p>
      <svg viewBox={`0 0 ${W} ${rows.length * 26 + 6}`} width="100%" role="img" style={{ marginTop: 4 }}
           aria-label={rows.map((r) => `${r.label}: ${r.n}`).join(". ")}>
        {rows.map((r, i) => (
          <g key={r.label} transform={`translate(0 ${i * 26})`}>
            <text x="0" y="16" fontSize="13" fill={text.secondary}>{r.label}</text>
            <rect x={labelW} y="3" width={Math.max(r.n > 0 ? 3 : 0, (r.n / c.total) * barW)} height="16" fill={r.fill} />
            <text x={labelW + Math.max(r.n > 0 ? 3 : 0, (r.n / c.total) * barW) + 8} y="16" fontSize="13" fill={text.primary}>
              {r.n}{r.llm ? " to LLM" : ""}
            </text>
          </g>
        ))}
      </svg>
      <p style={{ fontSize: 13, color: text.secondary, margin: "6px 0 0" }}>
        Every link in the middle band goes to the LLM. The band is the space between the two cut-off sliders
        (low and high threshold, or the percentiles when bucketing is on): raise the low cut-off or lower the high one
        to shrink it and send fewer links to the LLM.
      </p>
      {c.capped > 0 && (
        <p style={{ fontSize: 13, color: text.secondary, margin: "6px 0 0" }}>
          The cap of {cfg.max_llm_links_per_node} links per page keeps only the best-scored of the {c.toLlm + c.capped} bound
          for the LLM; the other {c.capped} are trusted on their NLP score.
        </p>
      )}
    </ExplainerFrame>
  );
}
