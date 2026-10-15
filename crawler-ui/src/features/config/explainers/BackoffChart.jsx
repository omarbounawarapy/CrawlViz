import { useMemo, useState } from "react";
import { getTheme } from "../../../theme";
import ExplainerFrame from "./ExplainerFrame";
import { scenario, summary, timeline } from "./backoffModel";
import { Chip } from "../../common/Form";

const theme = getTheme();
const { text } = theme.colors;
const W = 640, PAD = { l: 52, r: 12, t: 14, b: 8 }, PANEL_H = 100, GAP = 34, N = 60, LATENCY = 0.3;

const fmt = (v) => (Math.round(v * 10) / 10).toString();
// Round tick values to 1, 2 or 5 times a power of ten so the axis reads cleanly.
function niceMax(v) {
  const p = 10 ** Math.floor(Math.log10(Math.max(v, 1e-6)));
  const n = v / p;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * p;
}

function Panel({ top, points, field, max, tMax, label, unit }) {
  const inner = W - PAD.l - PAD.r;
  const x = (t) => PAD.l + (t / tMax) * inner;
  const y = (v) => top + PAD.t + PANEL_H - (v / max) * PANEL_H;
  const d = points.map((p, i) => `${i ? "L" : "M"}${x(p.t).toFixed(1)} ${y(p[field]).toFixed(1)}`).join(" ");
  const yTicks = [0, max / 2, max];
  const xTicks = [0, 0.25, 0.5, 0.75, 1].map((f) => f * tMax);
  const hits = points.filter((p) => p.outcome === "429");
  return (
    <g>
      <text x={PAD.l} y={top + 10} fontSize="13" fontWeight="600" fill={text.primary}>{label}</text>
      {hits.length > 0 && (
        <rect x={x(hits[0].t)} y={y(max)} width={Math.max(x(hits[hits.length - 1].t) - x(hits[0].t), 2)} height={PANEL_H}
              fill="rgba(15,27,45,0.07)" />
      )}
      {yTicks.map((v) => (
        <g key={v}>
          <line x1={PAD.l} x2={W - PAD.r} y1={y(v)} y2={y(v)} stroke="#e3e8ee" />
          <text x={PAD.l - 8} y={y(v) + 4} textAnchor="end" fontSize="12" fill={text.muted}>{fmt(v)}</text>
        </g>
      ))}
      <text x="0" y={y(max / 2) + 4} fontSize="12" fill={text.muted}>{unit}</text>
      {xTicks.map((t) => (
        <text key={t} x={x(t)} y={y(0) + 16} textAnchor="middle" fontSize="12" fill={text.muted}>{Math.round(t)}</text>
      ))}
      <path d={d} fill="none" stroke={text.primary} strokeWidth="2" />
    </g>
  );
}

/**
 * 60 example requests with an optional burst of rate-limit (429) replies, drawn as two charts
 * on the same time axis. `cfg` is the draft's `fetch`.
 */
export default function BackoffChart({ cfg }) {
  const [burst, setBurst] = useState(true);
  const points = useMemo(
    () => (typeof cfg?.min_delay === "number" ? timeline(scenario(N, burst ? 8 : 0), cfg, LATENCY) : []),
    [cfg, burst],
  );
  if (points.length === 0) return null;
  const s = summary(cfg, LATENCY);
  const tMax = Math.max(points[points.length - 1].t, 1);
  const waitMax = niceMax(Math.max(...points.map((p) => p.wait)));
  const rateMax = niceMax(Math.max(...points.map((p) => p.rate)));
  const panelH = PAD.t + PANEL_H + 24;
  const total = panelH * 2 + GAP + PAD.b + 20;

  return (
    <ExplainerFrame
      title="How fast pages are requested, and what a 429 reply does"
      summary={`Steady pace about ${fmt(s.steadyRate)} requests per second. The longest a request waits is ${fmt(s.worstWait)} s.`}
    >
      <div style={{ marginBottom: 8 }}>
        <Chip pressed={burst} onClick={() => setBurst((v) => !v)}>Site answers 429 for 8 requests in a row</Chip>
      </div>
      <svg viewBox={`0 0 ${W} ${total}`} width="100%" role="img"
           aria-label={`Example of ${N} requests over ${fmt(tMax)} seconds. The wait before a request peaks at ${fmt(Math.max(...points.map((p) => p.wait)))} seconds.`}>
        <Panel top={0} points={points} field="wait" max={waitMax} tMax={tMax} label="Wait before each request" unit="s" />
        <Panel top={panelH + GAP - 8} points={points} field="rate" max={rateMax} tMax={tMax} label="Requests per second" unit="req/s" />
        <text x={PAD.l + (W - PAD.l - PAD.r) / 2} y={total - 2} textAnchor="middle" fontSize="12" fill={text.secondary}>
          Time since the crawl started (seconds)
        </text>
      </svg>
      <p style={{ fontSize: 13, color: text.muted, margin: "6px 0 0" }}>
        Shaded band: the 429 replies. Assumes each request takes {LATENCY} s and the jitter averages {fmt((cfg.jitter_max ?? 0) / 2)} s.
        Backoff is shared by every worker, so this is the pace of the crawl as a whole.
      </p>
    </ExplainerFrame>
  );
}
