import { useMemo } from "react";
import { getTheme } from "../../theme";
import { createComponentStyles } from "../../theme/components";
import EmptyState from "../common/EmptyState";
import { PIPELINE_STAGES, PIPELINE_STAGE_LABELS } from "../../state/nodeStates";
import { formatDuration } from "../../utils/formatters";

const theme = getTheme();
const S = createComponentStyles(theme);

function stagePhase(stats) {
  if (!stats) return "idle";
  if (stats.failed > 0) return "failed";
  if (stats.started > stats.completed + stats.failed) return "active";
  if (stats.completed > 0) return "completed";
  return "idle";
}

const PHASE_WORD = { idle: "Idle", active: "Running", completed: "Done", failed: "Has failures" };

function StageBox({ stage, stats }) {
  const phase = stagePhase(stats);
  const inFlight = Math.max(0, (stats?.started || 0) - (stats?.completed || 0) - (stats?.failed || 0));
  return (
    <div
      style={{
        ...S.stageBox(phase),
        borderStyle: phase === "idle" ? "dashed" : "solid",
        borderWidth: phase === "failed" ? 2 : 1,
      }}
    >
      <h3 style={{ ...S.stageBoxLabel, fontWeight: 400, margin: 0 }}>{PIPELINE_STAGE_LABELS[stage] || stage}</h3>
      {/* The phase in words: the border colour alone would not say it (WCAG 1.4.1). */}
      <div
        style={{
          fontSize: theme.typography.size.xxs,
          fontWeight: 600,
          color: phase === "failed" ? theme.colors.accent.red : theme.colors.text.secondary,
        }}
      >
        {PHASE_WORD[phase]}
      </div>
      <div
        style={{
          fontSize: theme.typography.size.xl,
          fontWeight: theme.typography.weight.semibold,
          color: theme.colors.text.primary,
          marginTop: 4,
          fontVariantNumeric: "tabular-nums",
        }}
      >
        {stats?.completed || 0}
      </div>
      <div style={{ fontSize: theme.typography.size.xxs, color: theme.colors.text.muted, marginTop: 2 }}>
        {inFlight > 0 && <span style={{ color: theme.colors.pipeline.active }}>{inFlight} in flight · </span>}
        {stats?.failed > 0 && <span style={{ color: theme.colors.accent.red }}>{stats.failed} failed · </span>}
        queue {stats?.queue_size ?? 0}
      </div>
      <div style={{ fontSize: theme.typography.size.xxs, color: theme.colors.text.muted, marginTop: 2 }}>
        {stats?.avg_duration_ms != null ? `avg ${formatDuration(stats.avg_duration_ms)}` : "no timing yet"}
        {stats?.last_duration_ms != null && ` · last ${formatDuration(stats.last_duration_ms)}`}
      </div>
    </div>
  );
}

function ThroughputBar({ stage, stats, maxCompleted }) {
  const pct = maxCompleted > 0 ? ((stats?.completed || 0) / maxCompleted) * 100 : 0;
  return (
    <div style={S.breakdownRow}>
      <div style={S.breakdownLabel}>{PIPELINE_STAGE_LABELS[stage] || stage}</div>
      <div style={S.breakdownBarTrack} aria-hidden="true">
        <div style={S.breakdownBarFill(`${pct}%`, theme.colors.pipeline.completed)} />
      </div>
      <div style={S.breakdownValue}>{stats?.completed || 0}</div>
    </div>
  );
}

export default function PipelineMonitor({ pipelineStats, eventLog, errors }) {
  const recentTicks = useMemo(() => {
    const ticks = [];
    for (let i = eventLog.length - 1; i >= 0 && ticks.length < 40; i--) {
      if (eventLog[i].type === "PIPELINE_EVENT") ticks.push(eventLog[i]);
    }
    return ticks;
  }, [eventLog]);

  const recentErrors = useMemo(() => errors.slice(-10).reverse(), [errors]);

  const maxCompleted = Math.max(1, ...PIPELINE_STAGES.map((s) => pipelineStats[s]?.completed || 0));

  return (
    <div style={S.panel}>
      <div style={S.panelHeader}>
        <div>
          <h2 style={{ ...S.panelHeaderTitle, margin: 0 }}>Pipeline Monitor</h2>
          <div style={S.panelHeaderSubtitle}>Where is the bottleneck?</div>
        </div>
      </div>

      <div style={S.panelScroll}>
        {/* Stage DAG */}
        <p style={S.sectionCardTitle}>
          Request, extraction, filtering, scoring, priority, transform, export, in that order.
        </p>
        <ol style={{ ...S.stageRow, listStyle: "none", margin: 0, padding: 0 }}>
          {PIPELINE_STAGES.map((stage, i) => (
            <li key={stage} style={{ display: "flex", alignItems: "stretch" }}>
              <StageBox stage={stage} stats={pipelineStats[stage]} />
              {i < PIPELINE_STAGES.length - 1 && (
                <div aria-hidden="true" style={S.stageBoxArrow}>
                  →
                </div>
              )}
            </li>
          ))}
        </ol>

        {/* Throughput comparison */}
        <div style={{ ...S.sectionCard, marginTop: 20 }}>
          <h3 style={{ ...S.sectionCardTitle, fontWeight: 400 }}>Completed per stage</h3>
          {PIPELINE_STAGES.map((stage) => (
            <ThroughputBar key={stage} stage={stage} stats={pipelineStats[stage]} maxCompleted={maxCompleted} />
          ))}
        </div>

        <div style={{ display: "flex", flexWrap: "wrap", gap: 16, marginTop: 20 }}>
          {/* Recent activity */}
          <div style={{ ...S.sectionCard, flex: "1 1 240px", minWidth: 0 }}>
            <h3 style={{ ...S.sectionCardTitle, fontWeight: 400 }}>Recent activity</h3>
            {recentTicks.length === 0 ? (
              <EmptyState>No pipeline events yet.</EmptyState>
            ) : (
              <div style={{ maxHeight: 320, overflowY: "auto" }}>
                {recentTicks.map((t, i) => (
                  <div
                    key={i}
                    style={{
                      display: "flex",
                      gap: 8,
                      padding: "3px 0",
                      borderBottom: `1px solid ${theme.colors.rowBorder}`,
                      fontSize: theme.typography.size.xxs,
                    }}
                  >
                    <span style={{ color: theme.colors.text.muted, minWidth: 82 }}>
                      {PIPELINE_STAGE_LABELS[t.stage] || t.stage}
                    </span>
                    <span
                      style={{
                        color: t.phase === "failed" ? theme.colors.accent.red : theme.colors.text.secondary,
                        minWidth: 68,
                      }}
                    >
                      {t.phase}
                    </span>
                    <span
                      style={{
                        color: theme.colors.text.muted,
                        flex: 1,
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                      }}
                    >
                      {t.detail}
                    </span>
                    {t.duration_ms != null && (
                      <span style={{ color: theme.colors.text.muted, flexShrink: 0 }}>
                        {formatDuration(t.duration_ms)}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Recent errors */}
          <div style={{ ...S.sectionCard, flex: "1 1 240px", minWidth: 0 }}>
            <h3
              style={{
                ...S.sectionCardTitle,
                fontWeight: 400,
                color: recentErrors.length ? theme.colors.accent.red : theme.colors.text.muted,
              }}
            >
              Recent errors ({errors.length} total)
            </h3>
            {recentErrors.length === 0 ? (
              <EmptyState>No errors recorded.</EmptyState>
            ) : (
              <div style={{ maxHeight: 320, overflowY: "auto" }}>
                {recentErrors.map((e, i) => (
                  <div key={i} style={{ padding: "6px 0", borderBottom: `1px solid ${theme.colors.rowBorder}` }}>
                    <div style={{ fontSize: theme.typography.size.xxs, color: theme.colors.accent.red }}>
                      {e.stage}: {e.error_type}
                    </div>
                    <div
                      style={{ fontSize: theme.typography.size.xxs, color: theme.colors.text.secondary, marginTop: 1 }}
                    >
                      {e.error_message}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
