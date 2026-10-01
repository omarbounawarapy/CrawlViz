import { useRef, useState, useCallback, useEffect, useMemo } from "react";
import { getTheme } from "../../theme";

const theme = getTheme();
const C = theme.colors;

const BAR = 3;       // one bar is 3px wide...
const GAP = 2;       // ...with a 2px gap
const H = 22;        // band height

/**
 * The replay scrubber: the event record drawn as a band of bars.
 *
 * Each bar is a slice of the record, as tall as the activity in it, so you can see where the
 * crawl was busy before you drag there. Played slices are ink, the rest pale slate; slices
 * with an error turn plum and a stop stands at full height. A playhead (a notch and a rule)
 * marks the current event. Hovering or dragging shows what is at that point (event number, clock time,
 * pages found so far) in a margin-note tooltip, the same way the graph annotates a page.
 * It is one slider for assistive tech: arrow keys step by one event, Shift by ten, Page keys
 * by fifty, Home to the start, End back to live.
 */
export default function Scrubber({ total, position, types, describe, onSeek, onLive, onUserSeek, disabled }) {
  const ref = useRef(null);
  const [hover, setHover] = useState(null);      // index under the pointer
  const [dragging, setDragging] = useState(false);
  const [focused, setFocused] = useState(false);

  const [width, setWidth] = useState(600);
  useEffect(() => {
    const el = ref.current;
    if (!el) return undefined;
    if (typeof ResizeObserver === "undefined") return undefined;
    const ro = new ResizeObserver(() => setWidth(el.clientWidth || 600));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const last = Math.max(total - 1, 0);

  // Slices of the record: how many events, and whether an error or a stop falls inside.
  const slices = useMemo(() => {
    const n = Math.max(1, Math.min(total || 1, Math.floor((width - 16 + GAP) / (BAR + GAP))));
    const out = Array.from({ length: n }, (_, b) => ({ count: 0, error: false, stop: false, from: Math.floor((b * total) / n), to: Math.floor(((b + 1) * total) / n) - 1 }));
    let max = 1;
    for (let i = 0; i < (types?.length ?? 0); i++) {
      const t = types[i];
      const b = out[Math.min(n - 1, Math.floor((i * n) / Math.max(total, 1)))];
      if (t === "NODE_ERROR") b.error = true;
      else if (t === "CRAWL_STOPPED") b.stop = true;
      if (t !== "PIPELINE_EVENT") { b.count += 1; if (b.count > max) max = b.count; }
    }
    return out.map(b => ({ ...b, h: b.stop || b.error ? 1 : 0.22 + 0.78 * (b.count / max) }));
  }, [types, total, width]);
  const frac = (i) => (last > 0 ? i / last : 0);

  const indexAt = useCallback((clientX) => {
    const r = ref.current.getBoundingClientRect();
    const x = Math.min(Math.max(clientX - r.left - 8, 0), Math.max(r.width - 16, 1));
    return Math.round((x / Math.max(r.width - 16, 1)) * last);
  }, [last]);

  const seek = (i) => { onUserSeek?.(); onSeek(Math.min(Math.max(i, 0), last)); };

  const onPointerDown = (e) => {
    if (disabled) return;
    ref.current.setPointerCapture?.(e.pointerId);
    setDragging(true);
    seek(indexAt(e.clientX));
  };
  const onPointerMove = (e) => {
    if (disabled) return;
    const i = indexAt(e.clientX);
    setHover(i);
    if (dragging) seek(i);
  };
  const end = () => setDragging(false);

  const onKeyDown = (e) => {
    if (disabled) return;
    const big = e.shiftKey ? 10 : 1;
    const map = {
      ArrowLeft: -big, ArrowDown: -big, ArrowRight: big, ArrowUp: big, PageDown: -50, PageUp: 50,
    };
    if (e.key in map) { e.preventDefault(); seek(position + map[e.key]); }
    else if (e.key === "Home") { e.preventDefault(); seek(0); }
    else if (e.key === "End") { e.preventDefault(); onLive?.(); }
  };

  const shown = hover ?? (dragging || focused ? position : null);
  const info = shown != null && total > 0 ? describe(shown) : null;
  const pct = (i) => `calc(8px + (100% - 16px) * ${frac(i)})`;

  return (
    <div
      ref={ref}
      role="slider"
      tabIndex={disabled ? -1 : 0}
      aria-label="Replay position"
      aria-orientation="horizontal"
      aria-valuemin={1}
      aria-valuemax={Math.max(total, 1)}
      aria-valuenow={Math.min(position + 1, Math.max(total, 1))}
      aria-valuetext={total ? describe(position).spoken : "No events yet"}
      aria-disabled={disabled || undefined}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={end}
      onPointerCancel={end}
      onPointerLeave={() => { if (!dragging) setHover(null); }}
      onKeyDown={onKeyDown}
      onFocus={() => setFocused(true)}
      onBlur={() => setFocused(false)}
      style={{
        position: "relative", height: 40, cursor: disabled ? "default" : "pointer", touchAction: "none",
        opacity: disabled ? 0.5 : 1, userSelect: "none", outline: "none",
      }}
    >
      {/* the record as a band of bars */}
      <div aria-hidden="true" style={{
        position: "absolute", left: 8, right: 8, top: 9, height: H, display: "flex", alignItems: "flex-end", justifyContent: "space-between",
      }}>
        {slices.map((b, i) => {
          const played = total > 0 && b.from <= position;
          return (
            <span key={i} style={{
              width: BAR, height: `${Math.round(b.h * 100)}%`, flexShrink: 0, borderRadius: 1,
              background: b.error ? C.accent.red : played ? C.text.primary : C.state.FETCHED,
            }} />
          );
        })}
      </div>

      {/* hover guide */}
      {hover != null && !disabled && (
        <span aria-hidden="true" style={{
          position: "absolute", left: pct(hover), top: 7, width: 1, height: H + 4, marginLeft: -0.5, background: C.text.muted,
        }} />
      )}

      {/* playhead: a notch on top of a rule through the band */}
      <span aria-hidden="true" style={{
        position: "absolute", left: pct(position), top: 2, width: focused ? 4 : 2, height: H + 10, marginLeft: focused ? -2 : -1, background: C.text.primary,
      }} />
      <span aria-hidden="true" style={{
        position: "absolute", left: pct(position), top: 0, marginLeft: focused ? -7 : -5, width: 0, height: 0,
        borderLeft: `${focused ? 7 : 5}px solid transparent`, borderRight: `${focused ? 7 : 5}px solid transparent`, borderTop: `${focused ? 9 : 7}px solid ${C.text.primary}`,
      }} />

      {/* margin note */}
      {info && (
        <div aria-hidden="true" style={{
          position: "absolute", bottom: 42, left: pct(shown), transform: "translateX(-50%)",
          background: C.background.panel, border: `1px solid ${C.background.border}`, borderRadius: theme.radii.lg,
          padding: "5px 9px", whiteSpace: "nowrap", pointerEvents: "none", zIndex: 6,
          fontSize: 12, lineHeight: 1.4, color: C.text.secondary,
        }}>
          <span className="num" style={{ color: C.text.primary, fontWeight: 600 }}>{info.title}</span>
          <span className="num" style={{ marginLeft: 8 }}>{info.detail}</span>
        </div>
      )}
    </div>
  );
}
