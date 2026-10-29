import { useEffect, useRef } from "react";
import { getTheme } from "../../theme";
import { clampRange } from "./configModel";

const theme = getTheme();
const { text } = theme.colors;

const HOLD_DELAY = 400;
const HOLD_EVERY = 70;

const btn = {
  minWidth: 30,
  minHeight: 30,
  fontSize: 16,
  lineHeight: 1,
  borderRadius: theme.radii.sm,
  border: `1px solid ${theme.colors.control}`,
  background: "transparent",
  color: text.primary,
};

/**
 * `- n +` with hold-to-repeat; the value can only land inside [min, max]. A press changes the
 * value on release (the click), so sliding off the button cancels it (WCAG 2.5.2); holding
 * repeats only after HOLD_DELAY. `labelledBy` names the value from a visible label;
 * `label` is used for the buttons and when there is no visible label.
 */
export default function Stepper({
  value,
  min = 0,
  max = Infinity,
  step = 1,
  onChange,
  label,
  labelledBy,
  describedBy,
  unit,
  id,
  disabled,
}) {
  const latest = useRef(value);
  useEffect(() => {
    latest.current = value;
  }, [value]);
  const timers = useRef({});
  const stop = () => {
    clearTimeout(timers.current.delay);
    clearInterval(timers.current.repeat);
  };
  useEffect(() => stop, []);

  const bump = (dir) => {
    const next = clampRange(latest.current + dir * step, min, max);
    if (next !== latest.current) {
      latest.current = next;
      onChange(next);
    }
  };
  const hold = (dir) => (e) => {
    if (e.button > 0 || disabled) return;
    stop();
    timers.current.repeated = false;
    timers.current.delay = setTimeout(() => {
      timers.current.repeated = true;
      bump(dir);
      timers.current.repeat = setInterval(() => bump(dir), HOLD_EVERY);
    }, HOLD_DELAY);
  };
  // The click (pointer released over the button, or a keyboard press) is the step. After a
  // hold that already repeated, the click that ends it adds nothing.
  const click = (dir) => () => {
    if (timers.current.repeated) {
      timers.current.repeated = false;
      return;
    }
    bump(dir);
  };
  const onKeyDown = (e) => {
    const dir = { ArrowUp: 1, ArrowRight: 1, ArrowDown: -1, ArrowLeft: -1 }[e.key];
    if (dir) {
      e.preventDefault();
      bump(dir);
    } else if (e.key === "Home") {
      e.preventDefault();
      onChange(min);
    } else if (e.key === "End" && Number.isFinite(max)) {
      e.preventDefault();
      onChange(max);
    }
  };

  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 6, opacity: disabled ? 0.5 : 1 }}>
      <button
        type="button"
        aria-label={`Decrease ${label}`}
        disabled={disabled || value <= min}
        onPointerDown={hold(-1)}
        onPointerUp={stop}
        onPointerLeave={stop}
        onPointerCancel={stop}
        onClick={click(-1)}
        style={btn}
      >
        −
      </button>
      <span
        id={id}
        role="spinbutton"
        tabIndex={disabled ? -1 : 0}
        aria-labelledby={labelledBy}
        aria-label={labelledBy ? undefined : label}
        aria-describedby={describedBy}
        aria-valuenow={value}
        aria-valuemin={min}
        aria-valuemax={Number.isFinite(max) ? max : undefined}
        aria-valuetext={unit ? `${value} ${unit}` : undefined}
        onKeyDown={onKeyDown}
        className="num focus-box"
        style={{ minWidth: 44, textAlign: "center", fontSize: 14, fontWeight: 600, color: text.primary }}
      >
        {value}
      </span>
      <button
        type="button"
        aria-label={`Increase ${label}`}
        disabled={disabled || value >= max}
        onPointerDown={hold(1)}
        onPointerUp={stop}
        onPointerLeave={stop}
        onPointerCancel={stop}
        onClick={click(1)}
        style={btn}
      >
        +
      </button>
      {unit && <span style={{ fontSize: 13, color: text.muted }}>{unit}</span>}
    </span>
  );
}
