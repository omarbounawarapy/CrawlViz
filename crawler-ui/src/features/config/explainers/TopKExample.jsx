import { useMemo } from "react";
import { getTheme } from "../../../theme";
import ExplainerFrame from "./ExplainerFrame";
import { clusterAngles, linkContext, topKMean } from "./topkModel";
import sample from "./sampleData.json";

const theme = getTheme();
const { text } = theme.colors;
const R = 78;
// Cluster inks keep 3:1 on the card; each dot also carries its cluster's letter (WCAG 1.4.1).
const PALETTE = ["#0f1b2d", "#56657a", "#707d90", "#33435a"];
const LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
const f2 = (v) => v.toFixed(2);

/** `target_top_k`: which reference vectors count towards a link's topic similarity. */
export function TopKExample({ k }) {
  const basis = sample.topK.basis;
  const kk = Math.max(1, Math.min(Number(k) || 1, basis.length));
  const sorted = [...basis].sort((a, b) => b.similarity - a.similarity);
  const mean = topKMean(basis.map((b) => b.similarity), kk);
  return (
    <ExplainerFrame
      title="How a link is compared with the target"
      summary={`With k = ${kk}, the link scores ${f2(mean)}${kk === 1 ? ", its single closest match" : `, the average of its ${kk} closest matches`}.`}
    >
      <p style={{ fontSize: 13, color: text.secondary, margin: "0 0 8px" }}>
        Link being scored: “{sample.topK.link}”. Each row is a reference text describing the target, with how close the link is to it.
      </p>
      <ol style={{ listStyle: "none", margin: 0, padding: 0 }}>
      {sorted.map((b, i) => {
        const on = i < kk;
        // Rows outside the top k keep full-contrast text; the bar goes hollow and the row says so.
        return (
          <li key={b.label} style={{ display: "grid", gridTemplateColumns: "minmax(0, 210px) minmax(60px, 1fr) 40px", gap: 10, alignItems: "center", padding: "2px 0" }}>
            <span style={{ fontSize: 13, color: on ? text.primary : text.secondary }}>
              {b.label}{!on && <span style={{ color: text.muted }}> (not counted)</span>}
            </span>
            <div aria-hidden="true" style={{ height: 12, background: "#e3e8ee" }}>
              <div style={{ width: `${b.similarity * 100}%`, height: "100%", boxSizing: "border-box",
                            background: on ? text.primary : "transparent", border: on ? "none" : `1.5px solid ${theme.colors.control}` }} />
            </div>
            <span style={{ fontSize: 13, fontVariantNumeric: "tabular-nums" }}>{f2(b.similarity)}</span>
          </li>
        );
      })}
      </ol>
      <p style={{ fontSize: 13, color: text.muted, margin: "6px 0 0" }}>
        Filled bars count towards the average; hollow ones do not. A larger k rewards links that match several reference texts at once.
      </p>
    </ExplainerFrame>
  );
}

/** DBSCAN on cosine distance: points are directions on a circle, so an arc is a distance. */
export function ClusterExample({ eps, minSamples }) {
  const angles = sample.cluster.angles;
  const labels = useMemo(() => clusterAngles(angles, Number(eps) || 0.0001, Number(minSamples) || 1), [angles, eps, minSamples]);
  const groups = new Set(labels.filter((l) => l >= 0)).size;
  const noise = labels.filter((l) => l < 0).length;
  const reach = (Math.acos(Math.max(-1, Math.min(1, 1 - Number(eps)))) * 180) / Math.PI;
  return (
    <ExplainerFrame
      title="Which links form a cluster"
      summary={`${groups} cluster${groups === 1 ? "" : "s"} and ${noise} stray link${noise === 1 ? "" : "s"}. Two links are neighbours when they sit within ${Math.round(reach)}° of each other.`}
    >
      <svg viewBox="-100 -100 200 200" width="220" role="img"
           aria-label={`${angles.length} example links on a circle, grouped into ${groups} clusters with ${noise} strays.${
             groups ? ` ${[...new Set(labels.filter((l) => l >= 0))].map((l) => `Cluster ${LETTERS[l % 26]}: ${labels.filter((x) => x === l).length} links`).join(". ")}.` : ""}`}>
        <circle r={R} fill="none" stroke={theme.colors.control} />
        {angles.map((a, i) => {
          const rad = (a * Math.PI) / 180;
          const l = labels[i];
          const x = R * Math.cos(rad), y = -R * Math.sin(rad);
          return (
            <g key={a}>
              <circle cx={x} cy={y} r="5"
                      fill={l < 0 ? "none" : PALETTE[l % PALETTE.length]}
                      stroke={l < 0 ? text.muted : "none"} strokeWidth="1.5" />
              {l >= 0 && (
                <text x={x * 1.22} y={y * 1.22 + 4} textAnchor="middle" fontSize="11" fill={text.secondary}>{LETTERS[l % 26]}</text>
              )}
            </g>
          );
        })}
      </svg>
      <p style={{ fontSize: 13, color: text.muted, margin: "0" }}>
        Filled dots are lettered by cluster; hollow dots belong to none. A cluster needs at least {minSamples} links
        counting the link itself.
      </p>
    </ExplainerFrame>
  );
}

/** `link_context_length`: how much of the surrounding text the scorer sees. */
export function ContextExample({ length }) {
  const { text: full, anchor } = sample.context;
  const n = Math.max(1, Number(length) || 1);
  const kept = full.slice(0, n);
  const used = linkContext(full, anchor, n);
  const anchorCut = !kept.toLowerCase().includes(anchor.toLowerCase());
  return (
    <ExplainerFrame
      title="How much of the text around a link is kept"
      summary={anchorCut
        ? `Only ${Math.min(n, full.length)} characters are kept, and the link text “${anchor}” falls outside them, so the scorer sees the cut text as it is.`
        : `The scorer sees: “${used}”`}
    >
      <p style={{ fontSize: 13, color: text.secondary, margin: "0 0 8px" }}>
        A paragraph on the shop's page, with the link “{anchor}” inside it:
      </p>
      <p style={{ fontSize: 14, margin: 0, lineHeight: 1.5 }}>
        <mark style={{ background: "rgba(15,27,45,0.12)", color: text.primary }}>{kept}</mark>
        <span style={{ color: text.muted }}>{full.slice(n)}</span>
      </p>
      <p style={{ fontSize: 13, color: text.muted, margin: "6px 0 0" }}>
        The highlighted part is kept ({Math.min(n, full.length)} of {full.length} characters). The text is cut from the start
        of the surrounding element, then trimmed to the sentence that holds the link text.
      </p>
    </ExplainerFrame>
  );
}
