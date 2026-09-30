import { useRef, useEffect, useMemo, useState } from "react";
import { TYPE_BADGE } from "../../state/constants";
import { formatTs, eventSummary } from "../../utils/formatters";
import { getTheme } from "../../theme";
import { createComponentStyles } from "../../theme/components";

const theme  = getTheme();
const styles = createComponentStyles(theme);
const S = styles;

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

  return (
    <section
      aria-label="Timeline"
      style={{
        flexShrink: 0, display: "flex", flexDirection: "column",
        background: theme.colors.background.panel, borderTop: `1px solid ${theme.colors.background.border}`,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 20, height: 56, padding: "0 20px" }}>
        <div style={{ width: 150, flexShrink: 0, display: "flex", alignItems: "center", gap: 10 }}>
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

        <div style={{ flex: 1, minWidth: 0, position: "relative" }}>
          {/* Landmarks on the record: stops and errors, placed by position in the log */}
          <div aria-hidden="true" style={{ position: "absolute", left: 8, right: 8, top: -14, height: 10 }}>
            {eventLog.map((ev, i) => (ev.type === "CRAWL_STOPPED" || ev.type === "NODE_ERROR") ? (
              <span key={i} style={{
                position: "absolute", left: `${last > 0 ? (i / last) * 100 : 0}%`, top: 0, width: 2, height: 10,
                background: ev.type === "NODE_ERROR" ? theme.colors.accent.red : theme.colors.text.primary,
              }} />
            ) : null)}
          </div>
          <input
            type="range"
            min={0}
            max={last}
            value={position}
            disabled={eventLog.length === 0}
            onChange={e => onSeek(Number(e.target.value))}
            aria-label="Replay position"
            aria-valuetext={`Event ${position + 1} of ${eventLog.length}`}
            style={{ width: "100%", display: "block" }}
          />
        </div>

        <output className="num" style={{ width: 170, textAlign: "right", fontSize: 13, color: theme.colors.text.secondary, flexShrink: 0 }}>
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
        <div style={{ borderTop: `1px solid ${theme.colors.background.border}`, display: "flex", flexDirection: "column", height: 260 }}>
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
