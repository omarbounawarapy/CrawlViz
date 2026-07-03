import { NODE_STATES } from "../../state/constants";
import { getTheme } from "../../theme";
import { createComponentStyles } from "../../theme/components";

const theme  = getTheme();
const styles = createComponentStyles(theme);

function MetricRow({ label, value, accent }) {
  return (
    <div style={styles.metricRowWrap}>
      <span style={styles.metricRowLabel}>{label}</span>
      <span style={styles.metricRowValue(accent)}>{value ?? "—"}</span>
    </div>
  );
}

export default function MetricsPanel({ metrics, nodes, edges, status, stopReason, replayIndex }) {
  const nodeArr = Array.from(nodes.values());
  const byState = {};
  NODE_STATES.forEach(s => { byState[s] = 0; });
  nodeArr.forEach(n => { if (byState[n.state] !== undefined) byState[n.state]++; });

  const elapsed     = metrics ? (metrics.elapsed_seconds || 0).toFixed(1) + "s" : "—";
  const isReplaying = replayIndex !== null && replayIndex !== undefined;
  const isRunning   = status === "RUNNING";

  return (
    <div style={styles.metricsContainer}>

      {/* Status badge */}
      <div style={{ marginBottom: theme.spacing.lg }}>
        <div style={styles.statusBadgeWrap(status)}>
          <div style={styles.statusDot(status, isRunning)} />
          <span style={styles.statusText(status)}>
            {isReplaying ? "REPLAY" : status}
          </span>
        </div>
        {stopReason && (
          <div style={styles.stopReason}>reason: {stopReason}</div>
        )}
      </div>

      <div style={{ ...styles.sectionLabel, marginBottom: theme.spacing.sm }}>CRAWL METRICS</div>

      <MetricRow label="nodes total"  value={nodes.size}                       accent={theme.colors.accent.blue} />
      <MetricRow label="edges"        value={edges.size}                       accent={theme.colors.accent.blueDim} />
      <MetricRow label="links found"  value={metrics?.total_links_found  ?? 0} accent={theme.colors.accent.blueDim} />
      <MetricRow label="items stored" value={metrics?.total_items_stored ?? 0} accent={theme.colors.accent.blueDim} />
      <MetricRow label="elapsed"      value={elapsed}                          accent={theme.colors.accent.gold} />

      <div style={{ ...styles.sectionLabel, margin: `14px 0 ${theme.spacing.sm}` }}>NODE STATES</div>

      {NODE_STATES.map(s => {
        const stateColor = theme.colors.state.label[s];
        const width      = nodes.size ? `${(byState[s] / nodes.size) * 100}%` : "0%";
        return (
          <div key={s} style={{ marginBottom: theme.spacing.sm }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "3px" }}>
              <span style={{ ...styles.sectionLabel, color: stateColor }}>{s}</span>
              <span style={{ ...styles.sectionLabel, color: stateColor }}>{byState[s]}</span>
            </div>
            <div style={styles.stateBarTrack}>
              <div style={styles.stateBarFill(stateColor, width)} />
            </div>
          </div>
        );
      })}
    </div>
  );
}
