import { useRef, useEffect, useMemo, useState, useCallback } from "react";
import { TYPE_BADGE } from "../../state/constants";
import { formatTs, eventSummary } from "../../utils/formatters";
import { getTheme } from "../../theme";
import { createComponentStyles } from "../../theme/components";
import Scrubber from "./Scrubber";

const theme  = getTheme();
const styles = createComponentStyles(theme);
const S = styles;

const SPEEDS = [1, 4, 16];
const ICONS = {
  start: <><path d="M3.5 3v8" /><path d="M11 3 6 7l5 4z" /></>,
  back: <path d="M9.5 3 4.5 7l5 4z" />,
  play: <path d="M4.5 3 11 7l-6.5 4z" />,
  pause: <><path d="M4.5 3v8" /><path d="M9.5 3v8" /></>,
  forward: <path d="M4.5 3 9.5 7l-5 4z" transform="translate(1 0)" />,
  live: <><path d="M3 3 8 7l-5 4z" /><path d="M11 3v8" /></>,
};

function TransportButton({ label, icon, onClick, disabled, pressed }) {
  return (
    <button
      type="button" onClick={onClick} disabled={disabled} aria-label={label} title={label} aria-pressed={pressed}
      style={{
        width: 30, height: 30, display: "inline-flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
        borderRadius: theme.radii.md, border: `1px solid ${disabled ? theme.colors.background.border : theme.colors.text.primary}`,
        background: pressed ? theme.colors.text.primary : "transparent",
        color: pressed ? theme.colors.background.panel : disabled ? theme.colors.text.muted : theme.colors.text.primary,
        padding: 0,
      }}
    >
      <svg width="14" height="14" viewBox="0 0 14 14" fill="currentColor" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" aria-hidden="true">
        {ICONS[icon]}
      </svg>
    </button>
  );
}

const FILTERABLE_TYPES = Object.keys(TYPE_BADGE).filter(t => !t.startsWith("__"));

/**
 * TimelineDock -- the measurement record, docked under the graph.
 *
 * Collapsed it is one row: replay state, the scrubber, and an Events toggle.
 * Dragging the scrubber replays the whole app state to that event; the graph
 * above and the annotation panel beside it follow. Expanded, it lists the
 * events behind the scrubber.
 */
export default function TimelineDock({ eventLog, replayIndex, onSeek, onExitReplay, expanded, onToggleExpanded }) {
  const listRef     = useRef(null);
  const isReplaying = replayIndex !== null && replayIndex !== undefined;

  // PIPELINE_EVENT dominates the raw log several-to-one; the Measurements
  // drawer is the better place for it, so it starts hidden.
  const [hidden, setHidden] = useState(() => new Set(["PIPELINE_EVENT"]));
  const toggle = (t) => setHidden(prev => {
    const next = new Set(prev);
    if (next.has(t)) next.delete(t); else next.add(t);
    return next;
  });

  const visibleIndices = useMemo(
    () => eventLog.map((_, i) => i).filter(i => !hidden.has(eventLog[i].type)),
    [eventLog, hidden]
  );

  useEffect(() => {
    if (expanded && !isReplaying && listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
  }, [eventLog.length, isReplaying, expanded]);

  const last = Math.max(eventLog.length - 1, 0);
  const position = replayIndex ?? last;

  // What the record says at each point: how many pages had been found by then.
  const pagesAt = useMemo(() => {
    const out = new Array(eventLog.length);
    let n = 0;
    for (let i = 0; i < eventLog.length; i++) {
      const ev = eventLog[i];
      if (ev.type === "NODE_ADDED") n += 1;
      else if (ev.type === "SNAPSHOT_FULL") n = ev.nodes?.length ?? n;
      out[i] = n;
    }
    return out;
  }, [eventLog]);

  const types = useMemo(() => eventLog.map(ev => ev.type), [eventLog]);

  const describe = useCallback((i) => {
    const ev = eventLog[i];
    const clock = ev?._receivedAt ? formatTs(ev._receivedAt).slice(0, 8) : "";
    const pages = pagesAt[i] ?? 0;
    return {
      title: `Event ${(i + 1).toLocaleString()} of ${eventLog.length.toLocaleString()}`,
      detail: `${clock}${clock ? " · " : ""}${pages.toLocaleString()} ${pages === 1 ? "page" : "pages"}`,
      spoken: `Event ${i + 1} of ${eventLog.length}, ${pages} pages found${clock ? `, at ${clock}` : ""}`,
    };
  }, [eventLog, pagesAt]);

  // Playback: steps forward through the record at a readable pace, then hands back to live.
  const [playing, setPlaying] = useState(false);
  const [speedIdx, setSpeedIdx] = useState(0);
  const posRef = useRef(position);
  const lastRef = useRef(last);
  useEffect(() => { posRef.current = position; lastRef.current = last; });
  useEffect(() => {
    if (!playing) return undefined;
    const step = Math.max(1, Math.round(SPEEDS[speedIdx] * 12 * 0.08));
    const id = setInterval(() => {
      const next = posRef.current + step;
      if (next >= lastRef.current) { setPlaying(false); onExitReplay(); } else onSeek(next);
    }, 80);
    return () => clearInterval(id);
  }, [playing, speedIdx, onSeek, onExitReplay]);

  const togglePlay = () => {
    if (playing) { setPlaying(false); return; }
    if (!isReplaying) onSeek(0);
    setPlaying(true);
  };
  const stepBy = (d) => { setPlaying(false); onSeek(Math.min(Math.max(position + d, 0), last)); };
  const goLive = () => { setPlaying(false); onExitReplay(); };
  const none = eventLog.length === 0;

  return (
    <section
      aria-label="Timeline"
      style={{
        flexShrink: 0, display: "flex", flexDirection: "column",
        background: theme.colors.background.panel, borderTop: `1px solid ${theme.colors.background.border}`,
      }}
    >
      <div className="tl-bar" style={{ display: "flex", alignItems: "center", gap: 20, height: 56, padding: "0 20px" }}>
        <div className="tl-mode" style={{ width: 120, flexShrink: 0, display: "flex", alignItems: "center", gap: 10 }}>
          {isReplaying ? (
            <button onClick={onExitReplay} style={{
              height: 30, padding: "0 12px", fontSize: 13, fontWeight: 600, borderRadius: theme.radii.md,
              background: theme.colors.text.primary, color: theme.colors.background.panel, border: "none",
            }}>
              Return to live
            </button>
          ) : (
            <span style={{ fontSize: 13, fontWeight: 600, color: theme.colors.text.primary }}>Live</span>
          )}
        </div>

        <div className="tl-transport" style={{ display: "flex", gap: 6, alignItems: "center", flexShrink: 0 }}>
          <TransportButton label="Go to the first event" icon="start" disabled={none} onClick={() => { setPlaying(false); onSeek(0); }} />
          <TransportButton label="Previous event" icon="back" disabled={none || position <= 0} onClick={() => stepBy(-1)} />
          <TransportButton label={playing ? "Pause replay" : "Play replay"} icon={playing ? "pause" : "play"} disabled={none} pressed={playing} onClick={togglePlay} />
          <TransportButton label="Next event" icon="forward" disabled={none || position >= last} onClick={() => stepBy(1)} />
          <TransportButton label="Return to live" icon="live" disabled={none || !isReplaying} onClick={goLive} />
          <button
            type="button" onClick={() => setSpeedIdx((speedIdx + 1) % SPEEDS.length)} disabled={none}
            aria-label={`Playback speed ${SPEEDS[speedIdx]} times, press to change`} title="Playback speed"
            className="num"
            style={{
              height: 30, minWidth: 38, padding: "0 6px", fontSize: 12, fontWeight: 600, borderRadius: theme.radii.md,
              background: "transparent", color: theme.colors.text.primary, border: `1px solid ${theme.colors.background.border}`,
            }}
          >
            {SPEEDS[speedIdx]}×
          </button>
        </div>

        <div style={{ flex: 1, minWidth: 0 }}>
          <Scrubber
            total={eventLog.length} position={position} types={types} describe={describe}
            disabled={none} onSeek={onSeek} onLive={goLive} onUserSeek={() => setPlaying(false)}
          />
        </div>

        <output className="num tl-count" style={{ width: 170, textAlign: "right", fontSize: 13, color: theme.colors.text.secondary, flexShrink: 0 }}>
          {eventLog.length === 0 ? "No events yet" : `Event ${position + 1} of ${eventLog.length}`}
        </output>

        <button
          onClick={onToggleExpanded}
          aria-expanded={expanded}
          style={{
            height: 30, padding: "0 12px", fontSize: 13, fontWeight: 500, borderRadius: theme.radii.md,
            background: "transparent", color: theme.colors.text.primary, border: `1px solid ${theme.colors.text.primary}`,
          }}
        >
          {expanded ? "Hide events" : "Show events"}
        </button>
      </div>

      {expanded && (
        <div style={{ borderTop: `1px solid ${theme.colors.background.border}`, display: "flex", flexDirection: "column", height: "min(260px, 32vh)" }}>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", padding: "8px 20px", borderBottom: `1px solid ${theme.colors.background.border}` }}>
            {FILTERABLE_TYPES.map(t => {
              const badge = TYPE_BADGE[t];
              const active = !hidden.has(t);
              return (
                <button
                  key={t}
                  onClick={() => toggle(t)}
                  aria-pressed={active}
                  style={{
                    fontSize: 12, padding: "2px 8px", borderRadius: theme.radii.sm, fontWeight: 500,
                    border: `1px solid ${active ? theme.colors.text.primary : theme.colors.background.border}`,
                    background: active ? badge.bg : "transparent",
                    color: active ? badge.fg : theme.colors.text.muted,
                    textDecoration: active ? "none" : "line-through",
                  }}
                >
                  {badge.label}
                </button>
              );
            })}
          </div>

          <div ref={listRef} style={{ ...styles.timelineList, flex: 1 }}>
            {visibleIndices.map((i) => {
              const ev = eventLog[i];
              const badge     = TYPE_BADGE[ev.type] || { bg: theme.colors.background.border, fg: theme.colors.text.secondary, label: "?" };
              const isCurrent = isReplaying && i === replayIndex;
              const isPast    = isReplaying && i < replayIndex;
              return (
                <div key={i} onClick={() => onSeek(i)} style={styles.timelineEntry(isCurrent, isPast, isReplaying)}>
                  <span style={styles.timelineTs}>{formatTs(ev._receivedAt)}</span>
                  <span style={styles.timelineBadge(badge)}>{badge.label}</span>
                  <span style={styles.timelineSummary(isPast, isReplaying)}>{eventSummary(ev)}</span>
                </div>
              );
            })}
            {visibleIndices.length === 0 && (
              <div style={S.emptyState}>No events match the current filter.</div>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
