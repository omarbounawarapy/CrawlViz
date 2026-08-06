import { useRef, useEffect, useMemo, useState } from "react";
import { TYPE_BADGE } from "../../state/constants";
import { formatTs, eventSummary } from "../../utils/formatters";
import { getTheme } from "../../theme";
import { createComponentStyles } from "../../theme/components";

const theme  = getTheme();
const styles = createComponentStyles(theme);
const S = styles;

const FILTERABLE_TYPES = Object.keys(TYPE_BADGE).filter(t => !t.startsWith("__"));

export default function TimelinePage({ eventLog, replayIndex, onSeek, onExitReplay }) {
  const listRef     = useRef(null);
  const isReplaying = replayIndex !== null && replayIndex !== undefined;

  // Default filter excludes PIPELINE_EVENT -- at realistic crawl sizes it
  // dominates the raw log several-to-one over everything else, and the
  // Pipeline Monitor is the better place to watch it live; the timeline's
  // job is the higher-level narrative. One click re-enables it.
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
    if (!isReplaying && listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
  }, [eventLog.length, isReplaying]);

  return (
    <div style={{ ...S.panel, flexDirection: "row" }}>
      <div style={{ display: "flex", flexDirection: "column", flex: 1, minWidth: 0 }}>
        <div style={S.panelHeader}>
          <div>
            <div style={S.panelHeaderTitle}>Timeline / Replay</div>
            <div style={S.panelHeaderSubtitle}>What sequence of decisions produced this outcome?</div>
          </div>
          {isReplaying && (
            <button style={styles.exitReplayBtn} onClick={onExitReplay}>EXIT REPLAY</button>
          )}
        </div>

        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", padding: "8px 16px", borderBottom: `1px solid ${theme.colors.background.border}` }}>
          {FILTERABLE_TYPES.map(t => {
            const badge = TYPE_BADGE[t];
            const active = !hidden.has(t);
            return (
              <button
                key={t}
                onClick={() => toggle(t)}
                style={{
                  fontSize: theme.typography.size.xxs, fontFamily: theme.typography.fontMono,
                  padding: "2px 7px", borderRadius: theme.radii.sm, cursor: "pointer",
                  border: `1px solid ${active ? badge.fg : theme.colors.background.border}`,
                  background: active ? badge.bg : "transparent",
                  color: active ? badge.fg : theme.colors.text.muted,
                  opacity: active ? 1 : 0.6,
                }}
              >
                {badge.label}
              </button>
            );
          })}
        </div>

        <div ref={listRef} style={styles.timelineList}>
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

        {eventLog.length > 0 && (
          <div style={styles.timelineScrubberWrap}>
            <input
              type="range"
              min={0}
              max={eventLog.length - 1}
              value={replayIndex ?? eventLog.length - 1}
              onChange={e => onSeek(Number(e.target.value))}
              style={styles.timelineScrubberRange}
            />
            <div style={styles.timelineScrubberLabels}>
              <span style={styles.timelineScrubberLabel}>t=0</span>
              <span style={styles.timelineScrubberLabel}>{eventLog.length} events · scrub to replay the whole app's state</span>
              <span style={styles.timelineScrubberLabel}>t={eventLog.length - 1}</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
