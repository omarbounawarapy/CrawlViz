import { useRef } from "react";
import { getTheme } from "../../theme";
import { clampPair, roundStep as round } from "./configModel";

const theme = getTheme();
const { text, background } = theme.colors;

/**
 * One track, two thumbs. Dragging picks the nearest thumb; the thumbs can
 * never cross, so the schema's low < high rule cannot be broken from here.
 */
export default function RangeSlider({
  low, high, min = 0, max = 1, step = 0.01, onChange, format = String,
  lowLabel = "Low", highLabel = "High", invalid, labelledBy, describedBy,
}) {
  const track = useRef(null);
  const bounds = { min, max, step };
  const pct = (v) => `${((v - min) / (max - min)) * 100}%`;

  const move = (which, value) => {
    const next = clampPair({ low, high }, which, value, bounds);
    if (next.low !== low || next.high !== high) onChange(next.low, next.high);
  };
  const valueAt = (clientX) => {
    const r = track.current.getBoundingClientRect();
    const t = r.width ? (clientX - r.left) / r.width : 0;
    return min + Math.max(0, Math.min(1, t)) * (max - min);
  };
  const nearest = (v) => (Math.abs(v - low) <= Math.abs(v - high) ? "low" : "high");

  const onPointerDown = (e) => {
    if (e.button > 0) return;
    const v = valueAt(e.clientX);
    const which = e.target.dataset?.thumb ?? nearest(v);
    e.currentTarget.setPointerCapture?.(e.pointerId);
    track.current.dataset.dragging = which;
    move(which, v);
  };
  const onPointerMove = (e) => {
    const which = track.current.dataset.dragging;
    if (which) move(which, valueAt(e.clientX));
  };
  const onPointerUp = () => { delete track.current.dataset.dragging; };

  const onKeyDown = (which) => (e) => {
    const cur = which === "low" ? low : high;
    const big = step * 10;
    const target = {
      ArrowLeft: cur - step, ArrowDown: cur - step, ArrowRight: cur + step, ArrowUp: cur + step,
      PageDown: cur - big, PageUp: cur + big, Home: min, End: max,
    }[e.key];
    if (target === undefined) return;
    e.preventDefault();
    move(which, target);
  };

  const thumb = (which, value, lo, hi, label) => (
    <div
      role="slider" tabIndex={0} data-thumb={which} aria-label={label} aria-describedby={describedBy}
      aria-valuemin={lo} aria-valuemax={hi} aria-valuenow={value} aria-valuetext={format(value)}
      aria-orientation="horizontal" onKeyDown={onKeyDown(which)}
      style={{
        position: "absolute", top: "50%", left: pct(value), width: 18, height: 18, marginLeft: -9, marginTop: -9,
        borderRadius: "50%", background: text.primary, border: `2px solid ${background.panel}`,
        boxShadow: `0 0 0 1px ${invalid ? theme.colors.accent.red : text.primary}`, cursor: "grab", touchAction: "none",
      }}
    />
  );

  return (
    // One group, named by the row's label; each thumb is its own slider named by its end.
    <div role="group" aria-labelledby={labelledBy} style={{ display: "flex", flexDirection: "column", gap: 4, width: "min(260px, 100%)" }}>
      <div
        ref={track} onPointerDown={onPointerDown} onPointerMove={onPointerMove}
        onPointerUp={onPointerUp} onPointerCancel={onPointerUp}
        style={{ position: "relative", height: 28, cursor: "pointer", touchAction: "none" }}
      >
        <div style={{ position: "absolute", left: 0, right: 0, top: "50%", height: 4, marginTop: -2, borderRadius: 2,
                      background: theme.colors.control }} />
        <div style={{ position: "absolute", left: pct(low), width: `calc(${pct(high)} - ${pct(low)})`, top: "50%",
                      height: 4, marginTop: -2, borderRadius: 2, background: text.primary }} />
        {thumb("low", low, min, round(high - step), lowLabel)}
        {thumb("high", high, round(low + step), max, highLabel)}
      </div>
      <div className="num" style={{ display: "flex", justifyContent: "space-between", fontSize: 13, color: text.secondary }}>
        <span>{lowLabel} {format(low)}</span>
        <span>{highLabel} {format(high)}</span>
      </div>
    </div>
  );
}
