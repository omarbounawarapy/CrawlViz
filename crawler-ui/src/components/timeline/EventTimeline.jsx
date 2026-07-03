import { useRef, useEffect } from "react";
import { TYPE_BADGE } from "../../state/constants";
import { formatTs, eventSummary } from "../../utils/formatters";
import { getTheme } from "../../theme";
import { createComponentStyles } from "../../theme/components";

const theme  = getTheme();
const styles = createComponentStyles(theme);

export default function EventTimeline({ eventLog, replayIndex, onSeek, onExitReplay }) {
  const listRef     = useRef(null);
  const isReplaying = replayIndex !== null && replayIndex !== undefined;

  useEffect(() => {
    if (!isReplaying && listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
  }, [eventLog.length, isReplaying]);

  return (
    <div style={styles.timelineWrap}>

      {/* Header */}
      <div style={styles.timelineHeader}>
        <span style={styles.timelineHeaderLabel}>EVENT LOG · {eventLog.length}</span>
        {isReplaying && (
          <button style={styles.exitReplayBtn} onClick={onExitReplay}>EXIT REPLAY</button>
        )}
      </div>

      {/* Log entries */}
      <div ref={listRef} style={styles.timelineList}>
        {eventLog.map((ev, i) => {
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
      </div>

      {/* Replay scrubber */}
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
            <span style={styles.timelineScrubberLabel}>t={eventLog.length - 1}</span>
          </div>
        </div>
      )}
    </div>
  );
}
