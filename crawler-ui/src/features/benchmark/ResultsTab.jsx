import { useEffect, useMemo, useState } from "react";
import { fetchBenchmarkCurves } from "../../api/client";
import { getTheme } from "../../theme";
import { SectionTitle } from "../common/Page";
import { Tabs, TabPanel } from "../common/Form";
import Loading from "./Loading";
import {useLoad, POLICY_ORDER, num} from "./shared";
import ScrollRegion from "../common/ScrollRegion";

const { text, background } = getTheme().colors;
const W = 640, H = 300, M = { l: 44, r: 110, t: 12, b: 34 };

// Policies are told apart by dash, weight and a direct label, not hue. Every line keeps 3:1
// on the paper (WCAG 1.4.11); the lighter inks rely on their dash pattern.
const STYLE = {
  cascade:        { stroke: "#0f1b2d", width: 2.5, dash: "" },
  no_llm:         { stroke: "#33435a", width: 1.6, dash: "6 3" },
  llm_all:        { stroke: "#56657a", width: 1.6, dash: "2 3" },
  anchor_lexical: { stroke: "#707d90", width: 1.6, dash: "" },
  bfs:            { stroke: "#707d90", width: 1.6, dash: "8 3 2 3" },
  random:         { stroke: "#707d90", width: 1.6, dash: "12 4" },
  oracle:         { stroke: "#c7311a", width: 1.6, dash: "4 2" },
};

function Chart({ series }) {
  const policies = POLICY_ORDER.filter((p) => series[p]).concat(Object.keys(series).filter((p) => !POLICY_ORDER.includes(p)));
  const maxK = Math.max(...policies.map((p) => series[p].points.length));
  const x = (k) => M.l + ((k - 1) / Math.max(1, maxK - 1)) * (W - M.l - M.r);
  const y = (v) => H - M.b - v * (H - M.t - M.b);
  const [hover, setHover] = useState(null);
  // The hover box can be dismissed without moving the pointer (WCAG 1.4.13).
  useEffect(() => {
    if (hover == null) return undefined;
    const onKey = (e) => { if (e.key === "Escape") setHover(null); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [hover]);
  // Direct labels sit at the line ends; push them apart so they never overprint.
  const ends = policies.map((p) => {
    const pts = series[p].points.filter((d) => d.mean != null);
    return { p, y: pts.length ? y(pts[pts.length - 1].mean) + 4 : null, k: pts.length ? pts[pts.length - 1].k : 1 };
  }).filter((e) => e.y != null).sort((a, b) => a.y - b.y);
  for (let i = 1; i < ends.length; i++) if (ends[i].y - ends[i - 1].y < 13) ends[i].y = ends[i - 1].y + 13;
  const labelY = Object.fromEntries(ends.map((e) => [e.p, e.y]));
  const ticks = [0, 0.25, 0.5, 0.75, 1];
  const xt = [1, 10, 30, 50, 100].filter((k) => k <= maxK);
  // The picture's text alternative: the ranking at the last k every policy reached.
  const kEnd = Math.min(...policies.map((p) => series[p].points.filter((d) => d.mean != null).length).filter(Boolean), maxK);
  const ranking = policies
    .map((p) => [p, series[p].points[kEnd - 1]?.mean])
    .filter(([, v]) => v != null).sort((a, b) => b[1] - a[1])
    .map(([p, v]) => `${p} ${v.toFixed(2)}`).join(", ");
  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="img" style={{ width: "100%", maxWidth: W }}
      aria-label={`Harvest rate against pages fetched, one line per policy. At k = ${kEnd}: ${ranking}. The table under the chart has the values.`}
      onMouseLeave={() => setHover(null)}
      onMouseMove={(e) => {
        const r = e.currentTarget.getBoundingClientRect();
        const px = ((e.clientX - r.left) / r.width) * W;
        setHover(Math.min(maxK, Math.max(1, Math.round(1 + ((px - M.l) / (W - M.l - M.r)) * (maxK - 1)))));
      }}>
      {ticks.map((t) => (
        <g key={t}>
          <line x1={M.l} x2={W - M.r} y1={y(t)} y2={y(t)} stroke={background.border} />
          <text x={M.l - 6} y={y(t) + 4} textAnchor="end" fontSize="11" fill={text.muted}>{t}</text>
        </g>
      ))}
      {xt.map((k) => <text key={k} x={x(k)} y={H - 12} textAnchor="middle" fontSize="11" fill={text.muted}>{k}</text>)}
      <text x={(M.l + W - M.r) / 2} y={H - 0} textAnchor="middle" fontSize="11" fill={text.muted}>pages fetched (k)</text>
      {policies.map((p) => {
        const pts = series[p].points.filter((d) => d.mean != null);
        const s = STYLE[p] ?? STYLE.random;
        const band = pts.filter((d) => d.ci95 != null);
        const last = pts[pts.length - 1];
        return (
          <g key={p}>
            {p === "cascade" && band.length > 1 && (
              <path fill={s.stroke} opacity="0.12" d={
                "M" + band.map((d) => `${x(d.k)},${y(Math.min(1, d.mean + d.ci95))}`).join("L")
                + "L" + [...band].reverse().map((d) => `${x(d.k)},${y(Math.max(0, d.mean - d.ci95))}`).join("L") + "Z"} />
            )}
            <path fill="none" stroke={s.stroke} strokeWidth={s.width} strokeDasharray={s.dash}
              d={"M" + pts.map((d) => `${x(d.k)},${y(d.mean)}`).join("L")} />
            {last && <text x={x(last.k) + 6} y={labelY[p]} fontSize="11" fill={text.primary}>{p} ({series[p].runs})</text>}
          </g>
        );
      })}
      {hover && (() => {
        const rows = policies.map((p) => [p, series[p].points[hover - 1]?.mean]).filter(([, v]) => v != null)
          .sort((a, b) => b[1] - a[1]);
        const left = x(hover) > W / 2;
        const bx = left ? x(hover) - 132 : x(hover) + 8;
        return (
          <g pointerEvents="none">
            <line x1={x(hover)} x2={x(hover)} y1={M.t} y2={H - M.b} stroke={text.muted} strokeDasharray="2 2" />
            <rect x={bx} y={M.t} width="124" height={20 + rows.length * 15} fill={background.panel} stroke={background.border} />
            <text x={bx + 8} y={M.t + 14} fontSize="11" fontWeight="600" fill={text.primary}>k = {hover}</text>
            {rows.map(([p, v], i) => (
              <text key={p} x={bx + 8} y={M.t + 29 + i * 15} fontSize="11" fill={text.primary}>
                {p}: {v.toFixed(2)}
              </text>
            ))}
          </g>
        );
      })()}
    </svg>
  );
}

export default function ResultsTab() {
  const [grade, setGrade] = useState("1");
  const state = useLoad(() => fetchBenchmarkCurves(Number(grade)), [grade]);
  return (
    <>
      <Tabs id="grade" label="Relevance threshold" value={grade} onChange={setGrade}
        options={[["1", "Label ≥ 1"], ["2", "Label 2 only"]]} />
      <TabPanel tabsId="grade" value={grade}>
        <Loading state={state}>{(d) => <Body d={d} />}</Loading>
      </TabPanel>
    </>
  );
}

function Body({ d }) {
  const policies = useMemo(
    () => POLICY_ORDER.filter((p) => d.series[p]).concat(Object.keys(d.series).filter((p) => !POLICY_ORDER.includes(p))),
    [d]);
  if (!policies.length) return <p style={{ color: text.muted, marginTop: 16 }}>No valid runs yet.</p>;
  const at = (p, k) => d.series[p].points[k - 1];
  return (
    <>
      <SectionTitle>Harvest@k</SectionTitle>
      <p style={{ fontSize: 13, color: text.muted, marginBottom: 10 }}>
        Share of the first k fetched pages that are relevant, mean over repeats (n in brackets). Band: cascade 95% CI.
        "Short" counts runs that stopped well under their budget; check them on the Runs tab before averaging.
      </p>
      <Chart series={d.series} />
      <ul aria-label="Line key" style={{ display: "flex", flexWrap: "wrap", gap: "4px 18px", listStyle: "none", padding: 0, margin: "8px 0 0", fontSize: 12 }}>
        {policies.map((p) => {
          const s = STYLE[p] ?? STYLE.random;
          return (
            <li key={p} style={{ display: "flex", alignItems: "center", gap: 6, color: text.secondary }}>
              <svg width="26" height="8" aria-hidden="true">
                <line x1="0" x2="26" y1="4" y2="4" stroke={s.stroke} strokeWidth={s.width} strokeDasharray={s.dash} />
              </svg>
              {p}
            </li>
          );
        })}
      </ul>
      <CurveTable series={d.series} policies={policies} />
      <SectionTitle>Summary</SectionTitle>
      <ScrollRegion label="Summary table">
      <table style={{ fontSize: 13, borderCollapse: "collapse", width: "100%" }}>
        <thead><tr>
          {["Policy", "n", "@10", "@30", "@50", "Rel / call", "Rel / 1k tok", "Valid / invalid", "Short"].map((h, i) => (
            <th scope="col" key={h} style={{ textAlign: i ? "right" : "left", padding: "6px 8px", color: text.muted, fontWeight: 600 }}>{h}</th>
          ))}
        </tr></thead>
        <tbody>{policies.map((p) => {
          const v = d.validity[p] ?? {};
          const cell = (k) => at(p, k) ? `${num(at(p, k).mean, 2)}${at(p, k).ci95 != null ? ` ±${num(at(p, k).ci95, 2)}` : ""}` : "n/a";
          return (
            <tr key={p} style={{ borderTop: `1px solid ${background.border}` }}>
              <th scope="row" style={{ padding: "6px 8px", fontWeight: 600, textAlign: "left" }}>{p}</th>
              <td className="num" style={{ textAlign: "right", padding: "6px 8px" }}>{d.series[p].runs}</td>
              {[10, 30, 50].map((k) => <td key={k} className="num" style={{ textAlign: "right", padding: "6px 8px" }}>{cell(k)}</td>)}
              <td className="num" style={{ textAlign: "right", padding: "6px 8px" }}>{num(d.series[p].rel_per_call, 2)}</td>
              <td className="num" style={{ textAlign: "right", padding: "6px 8px" }}>{num(d.series[p].rel_per_1k_tokens, 2)}</td>
              <td className="num" style={{ textAlign: "right", padding: "6px 8px" }}>
                {v.valid ?? 0} / {v.invalid ?? 0}
              </td>
              <td className="num" style={{ textAlign: "right", padding: "6px 8px" }}>{d.series[p].short || "0"}</td>
            </tr>
          );
        })}</tbody>
      </table>
      </ScrollRegion>
    </>
  );
}

// The curves as numbers, every tenth k: what the chart shows on hover, for keyboard and screen readers.
function CurveTable({ series, policies }) {
  const maxK = Math.max(...policies.map((p) => series[p].points.length));
  const ks = [1, ...Array.from({ length: Math.floor(maxK / 10) }, (_, i) => (i + 1) * 10)].filter((k) => k <= maxK);
  const cell = { textAlign: "right", padding: "4px 8px" };
  return (
    <details style={{ margin: "10px 0 0" }}>
      <summary style={{ fontSize: 13, cursor: "pointer", color: text.primary }}>The curves as a table</summary>
      <ScrollRegion label="Curves table">
        <table style={{ fontSize: 12, borderCollapse: "collapse", marginTop: 6 }}>
          <caption className="sr-only">Share of the first k fetched pages that are relevant, mean over repeats</caption>
          <thead><tr>
            <th scope="col" style={{ ...cell, textAlign: "left", color: text.muted }}>k</th>
            {policies.map((p) => <th scope="col" key={p} style={{ ...cell, color: text.muted }}>{p}</th>)}
          </tr></thead>
          <tbody>{ks.map((k) => (
            <tr key={k} style={{ borderTop: `1px solid ${background.border}` }}>
              <th scope="row" style={{ ...cell, textAlign: "left", fontWeight: 600 }}>{k}</th>
              {policies.map((p) => <td key={p} className="num" style={cell}>{num(series[p].points[k - 1]?.mean, 2)}</td>)}
            </tr>
          ))}</tbody>
        </table>
      </ScrollRegion>
    </details>
  );
}
