import { useEffect, useState } from "react";
import Spider from "./Spider";
import "./loading.css";

const TIPS = [
  "Scoring every link before it is fetched.",
  "A local embedding pass runs first. It costs milliseconds.",
  "Only mid-confidence links reach the language model.",
  "Every decision is logged, so the crawl can be replayed.",
  "Vermilion marks the links the crawler judged most promising.",
];

const SPOKES = 12;
const RINGS = 7;
const R = 300;
const C = 320;

// Web geometry: radial spokes plus sagging ring threads, all in one viewBox.
function buildWeb() {
  const spokes = [];
  for (let i = 0; i < SPOKES; i++) {
    const a = (i / SPOKES) * Math.PI * 2 - Math.PI / 2;
    spokes.push({ x: C + Math.cos(a) * R, y: C + Math.sin(a) * R, a });
  }
  const rings = [];
  for (let r = 1; r <= RINGS; r++) {
    const rad = (r / RINGS) ** 1.15 * R;
    let d = "";
    for (let i = 0; i <= SPOKES; i++) {
      const a = (i / SPOKES) * Math.PI * 2 - Math.PI / 2;
      const x = C + Math.cos(a) * rad;
      const y = C + Math.sin(a) * rad;
      if (i === 0) d += `M${x.toFixed(1)} ${y.toFixed(1)}`;
      else {
        const pa = ((i - 0.5) / SPOKES) * Math.PI * 2 - Math.PI / 2;
        const sag = rad * 0.965;
        d += ` Q${(C + Math.cos(pa) * sag * 1.0).toFixed(1)} ${(C + Math.sin(pa) * sag).toFixed(1)} ${x.toFixed(1)} ${y.toFixed(1)}`;
      }
    }
    rings.push(d);
  }
  // A few dew nodes where threads cross; one is the relevance mark.
  const nodes = [];
  for (let r = 2; r <= RINGS; r += 2) {
    for (let i = (r % 4 === 0 ? 1 : 0); i < SPOKES; i += 3) {
      const a = (i / SPOKES) * Math.PI * 2 - Math.PI / 2;
      const rad = (r / RINGS) ** 1.15 * R;
      nodes.push({ x: C + Math.cos(a) * rad, y: C + Math.sin(a) * rad, r });
    }
  }
  return { spokes, rings, nodes };
}

/**
 * Page-wide loading screen. `progress` is 0..1. When `done` becomes true the
 * overlay completes the bar, holds a beat, then lifts away and calls onExit.
 */
const web = buildWeb();

export default function SpiderLoader({ progress, done, onExit, onSkip, title = "CrawlViz" }) {

  const [tip, setTip] = useState(0);
  const [leaving, setLeaving] = useState(false);

  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = prev; };
  }, []);

  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape" || e.key === "Enter" || e.key === " ") onSkip?.(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onSkip]);

  useEffect(() => {
    const t = setInterval(() => setTip((n) => (n + 1) % TIPS.length), 1500);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    if (!done) return undefined;
    const a = setTimeout(() => setLeaving(true), 450);
    const b = setTimeout(() => onExit?.(), 450 + 700);
    return () => { clearTimeout(a); clearTimeout(b); };
  }, [done, onExit]);

  const pct = Math.round(Math.min(1, Math.max(0, done ? 1 : progress)) * 100);

  return (
    <div
      className={`sl${leaving ? " sl-leaving" : ""}${pct >= 100 ? " sl-caught" : ""}`}
      role="status"
      aria-live="polite"
      aria-label="Loading CrawlViz"
      onClick={onSkip}
    >
      <svg className="sl-web" viewBox="0 0 640 640" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
        <g className="sl-rings" fill="none">
          {web.rings.map((d, i) => (
            <path key={i} d={d} pathLength="1" style={{ animationDelay: `${0.5 + i * 0.1}s` }} />
          ))}
        </g>
        <g className="sl-spokes">
          {web.spokes.map((s, i) => (
            <line key={i} x1={C} y1={C} x2={s.x} y2={s.y} pathLength="1" style={{ animationDelay: `${0.1 + i * 0.04}s` }} />
          ))}
        </g>
        <g className="sl-nodes">
          {web.nodes.map((n, i) => (
            <circle key={i} cx={n.x} cy={n.y} r={3 + (n.r % 3)} style={{ animationDelay: `${1 + i * 0.04}s` }} />
          ))}
        </g>
        <circle className="sl-target" cx={web.nodes[5]?.x ?? C} cy={web.nodes[5]?.y ?? C} r="12" />
      </svg>

      <div className="sl-center">
        <div className="sl-thread" />
        <div className="sl-spider"><Spider size={132} /></div>
      </div>

      <div className="sl-hud">
        <div className="sl-title">{title}</div>
        <div className="sl-bar" aria-hidden="true">
          <div className="sl-fill" style={{ transform: `scaleX(${pct / 100})` }} />
        </div>
        <div className="sl-row">
          <span className="sl-tip" key={tip} aria-hidden={pct < 100}>{pct >= 100 ? "Ready." : TIPS[tip]}</span>
          <button type="button" className="sl-skip" onClick={(e) => { e.stopPropagation(); onSkip?.(); }}>Skip</button>
        </div>
      </div>
    </div>
  );
}
