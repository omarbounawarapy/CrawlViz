import { useMemo } from "react";
import { getTheme } from "../../theme";
import { createComponentStyles } from "../../theme/components";
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

function StageBox({ stage, stats }) {
  const phase = stagePhase(stats);
  const inFlight = Math.max(0, (stats?.started || 0) - (stats?.completed || 0) - (stats?.failed || 0));
  return (
    <div style={S.stageBox(phase)}>
      <div style={S.stageBoxLabel}>{PIPELINE_STAGE_LABELS[stage] || stage}</div>
      <div style={{ fontSize: theme.typography.size.xl, fontWeight: theme.typography.weight.semibold, color: theme.colors.text.primary, marginTop: 4, fontVariantNumeric: "tabular-nums" }}>
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
      <div style={S.breakdownBarTrack}>
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

  const maxCompleted = Math.max(1, ...PIPELINE_STAGES.map(s => pipelineStats[s]?.completed || 0));

  return (
    <div style={S.panel}>
      <div style={S.panelHeader}>
        <div>
          <div style={S.panelHeaderTitle}>Pipeline Monitor</div>
          <div style={S.panelHeaderSubtitle}>Where is the bottleneck?</div>
        </div>
      </div>

      <div style={S.panelScroll}>
        {/* Stage DAG */}
        <div style={S.sectionCardTitle}>Request → Extraction → Filtering → Scoring → Priority → Transform → Export</div>
        <div style={S.stageRow}>
          {PIPELINE_STAGES.map((stage, i) => (
            <div key={stage} style={{ display: "flex", alignItems: "stretch" }}>
              <StageBox stage={stage} stats={pipelineStats[stage]} />
              {i < PIPELINE_STAGES.length - 1 && <div style={S.stageBoxArrow}>→</div>}
            </div>
          ))}
        </div>

        {/* Throughput comparison */}
        <div style={{ ...S.sectionCard, marginTop: 20 }}>
          <div style={S.sectionCardTitle}>Completed per stage</div>
          {PIPELINE_STAGES.map(stage => (
            <ThroughputBar key={stage} stage={stage} stats={pipelineStats[stage]} maxCompleted={maxCompleted} />
          ))}
        </div>

        <div style={{ display: "flex", gap: 16, marginTop: 20 }}>
          {/* Recent activity */}
          <div style={{ ...S.sectionCard, flex: 1, minWidth: 0 }}>
            <div style={S.sectionCardTitle}>Recent activity</div>
            {recentTicks.length === 0 ? (
              <div style={S.emptyState}>No pipeline events yet.</div>
            ) : (
              <div style={{ maxHeight: 320, overflowY: "auto" }}>
                {recentTicks.map((t, i) => (
                  <div key={i} style={{ display: "flex", gap: 8, padding: "3px 0", borderBottom: `1px solid ${theme.colors.rowBorder}`, fontSize: theme.typography.size.xxs }}>
                    <span style={{ color: theme.colors.text.muted, minWidth: 82 }}>{PIPELINE_STAGE_LABELS[t.stage] || t.stage}</span>
                    <span style={{ color: t.phase === "failed" ? theme.colors.accent.red : theme.colors.text.secondary, minWidth: 68 }}>{t.phase}</span>
                    <span style={{ color: theme.colors.text.muted, flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{t.detail}</span>
                    {t.duration_ms != null && <span style={{ color: theme.colors.text.muted, flexShrink: 0 }}>{formatDuration(t.duration_ms)}</span>}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Recent errors */}
          <div style={{ ...S.sectionCard, flex: 1, minWidth: 0 }}>
            <div style={{ ...S.sectionCardTitle, color: recentErrors.length ? theme.colors.accent.red : theme.colors.text.muted }}>
              Recent errors ({errors.length} total)
            </div>
            {recentErrors.length === 0 ? (
              <div style={S.emptyState}>No errors recorded.</div>
            ) : (
              <div style={{ maxHeight: 320, overflowY: "auto" }}>
                {recentErrors.map((e, i) => (
                  <div key={i} style={{ padding: "6px 0", borderBottom: `1px solid ${theme.colors.rowBorder}` }}>
                    <div style={{ fontSize: theme.typography.size.xxs, color: theme.colors.accent.red }}>{e.stage} — {e.error_type}</div>
                    <div style={{ fontSize: theme.typography.size.xxs, color: theme.colors.text.secondary, marginTop: 1 }}>{e.error_message}</div>
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
