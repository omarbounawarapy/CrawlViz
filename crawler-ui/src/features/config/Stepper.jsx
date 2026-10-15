import { useEffect, useRef } from "react";
import { getTheme } from "../../theme";
import { clampRange } from "./configModel";

const theme = getTheme();
const { text } = theme.colors;

const HOLD_DELAY = 400;
const HOLD_EVERY = 70;

const btn = {
  width: 30, height: 30, fontSize: 16, lineHeight: 1, borderRadius: theme.radii.sm,
  border: `1px solid ${theme.colors.background.border}`, background: "transparent", color: text.primary,
};

/** `- n +` with hold-to-repeat; the value can only land inside [min, max]. */
export default function Stepper({ value, min = 0, max = Infinity, step = 1, onChange, label, unit, id, disabled }) {
  const latest = useRef(value);
  useEffect(() => { latest.current = value; }, [value]);
  const timers = useRef({});
  const stop = () => { clearTimeout(timers.current.delay); clearInterval(timers.current.repeat); };
  useEffect(() => stop, []);

  const bump = (dir) => {
    const next = clampRange(latest.current + dir * step, min, max);
    if (next !== latest.current) { latest.current = next; onChange(next); }
  };
  const hold = (dir) => (e) => {
    if (e.button > 0 || disabled) return;
    bump(dir);
    stop();
    timers.current.delay = setTimeout(() => {
      timers.current.repeat = setInterval(() => bump(dir), HOLD_EVERY);
    }, HOLD_DELAY);
  };
  // A keyboard activation arrives as a click without a preceding pointerdown.
  const click = (dir) => (e) => { if (e.detail === 0) bump(dir); };
  const onKeyDown = (e) => {
    const dir = { ArrowUp: 1, ArrowRight: 1, ArrowDown: -1, ArrowLeft: -1 }[e.key];
    if (dir) { e.preventDefault(); bump(dir); }
    else if (e.key === "Home") { e.preventDefault(); onChange(min); }
    else if (e.key === "End" && Number.isFinite(max)) { e.preventDefault(); onChange(max); }
  };

  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 6, opacity: disabled ? 0.5 : 1 }}>
      <button type="button" aria-label={`Decrease ${label}`} disabled={disabled || value <= min}
              onPointerDown={hold(-1)} onPointerUp={stop} onPointerLeave={stop} onPointerCancel={stop}
              onClick={click(-1)} style={btn}>−</button>
      <span
        id={id} role="spinbutton" tabIndex={disabled ? -1 : 0} aria-label={label}
        aria-valuenow={value} aria-valuemin={min} aria-valuemax={Number.isFinite(max) ? max : undefined}
        onKeyDown={onKeyDown} className="num"
        style={{ minWidth: 44, textAlign: "center", fontSize: 14, fontWeight: 600, color: text.primary }}
      >
        {value}
      </span>
      <button type="button" aria-label={`Increase ${label}`} disabled={disabled || value >= max}
              onPointerDown={hold(1)} onPointerUp={stop} onPointerLeave={stop} onPointerCancel={stop}
              onClick={click(1)} style={btn}>+</button>
      {unit && <span style={{ fontSize: 13, color: text.muted }}>{unit}</span>}
    </span>
  );
}
