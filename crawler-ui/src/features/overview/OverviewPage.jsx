import { useMemo } from "react";
import { getTheme } from "../../theme";
import { createComponentStyles } from "../../theme/components";
import { PIPELINE_STAGES, PIPELINE_STAGE_LABELS } from "../../state/nodeStates";
import { formatDuration } from "../../utils/formatters";

const theme = getTheme();
const S = createComponentStyles(theme);

const FUNNEL_STAGES = ["CREATED", "FETCHED", "FILTERED", "SCORED", "EXPANDED"];
const FUNNEL_LABEL = { CREATED: "Found", FETCHED: "Fetched", FILTERED: "Filtered", SCORED: "Scored", EXPANDED: "Expanded" };
const STATUS_WORD = { RUNNING: "Crawling", STOPPED: "Finished", IDLE: "Idle", CONNECTING: "Waiting for backend" };

function FunnelBar({ label, count, max, color }) {
  const pct = max > 0 ? Math.max(2, (count / max) * 100) : 0;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
      <div style={{ width: 76, fontSize: theme.typography.size.xxs, color: theme.colors.text.muted, textTransform: "none", letterSpacing: theme.typography.letterSpacing.wide }}>
        {label}
      </div>
      <div style={{ flex: 1, height: 18, background: theme.colors.background.border, borderRadius: theme.radii.sm, overflow: "hidden" }}>
        <div style={{ width: "100%", height: "100%", background: color, transform: `scaleX(${pct / 100})`, transformOrigin: "left", transition: "transform 0.3s cubic-bezier(0.22, 1, 0.36, 1)" }} />
      </div>
      <div style={{ width: 46, textAlign: "right", fontSize: theme.typography.size.sm, color: theme.colors.text.primary, fontVariantNumeric: "tabular-nums" }}>
        {count}
      </div>
    </div>
  );
}

export default function OverviewPage({ state, metrics }) {
  const stateCounts = metrics.stateCounts;

  // Monotonic "reached at least this stage" funnel -- a node currently
  // sitting at SCORED has already passed through FETCHED and FILTERED, so
  // the funnel sums forward rather than showing the momentary distribution
  // (which would make later stages look artificially small).
  const cumulative = useMemo(() => {
    return FUNNEL_STAGES.map((stage, i) =>
      FUNNEL_STAGES.slice(i).reduce((sum, s) => sum + (stateCounts[s] || 0), 0)
    );
  }, [stateCounts]);

  const maxFunnel = cumulative[0] || 1;

  const elapsed = metrics.elapsed_seconds || 0;
  const pagesPerSec = elapsed > 0 ? (metrics.nodes_created / elapsed) : 0;

  const totalCandidates = metrics.candidatesDropped + metrics.candidatesTrusted;
  const dropRate = totalCandidates > 0 ? metrics.candidatesDropped / totalCandidates : 0;

  const maxPipelineCompleted = Math.max(1, ...PIPELINE_STAGES.map(s => state.pipelineStats[s]?.completed || 0));
  const bottleneckStage = PIPELINE_STAGES.reduce((worst, s) => {
    const avg = state.pipelineStats[s]?.avg_duration_ms;
    if (avg == null) return worst;
    if (!worst || avg > worst.avg) return { stage: s, avg };
    return worst;
  }, null);

  return (
    <div style={S.panel}>
      <div style={S.panelHeader}>
        <div>
          <div style={S.panelHeaderTitle}>Overview</div>
          <div style={S.panelHeaderSubtitle}>What is this crawl doing right now?</div>
        </div>
      </div>

      <div style={S.panelScroll}>
        {/* Measurements: one ruled list, figures right-aligned and tabular */}
        <dl style={{ margin: 0 }}>
          {[
            ["Pages discovered", state.nodes.size, `${state.edges.size} links followed`],
            ["Throughput", `${pagesPerSec.toFixed(2)} pages/s`, null],
            ["Elapsed", formatDuration(elapsed * 1000), `${STATUS_WORD[state.status] ?? state.status}${state.stop_reason ? ` (${String(state.stop_reason).toLowerCase().replace(/_/g, " ")})` : ""}`],
            ["Links skipped", metrics.candidatesDropped, `${totalCandidates} evaluated, ${(dropRate * 100).toFixed(0)}% skipped`],
            ["Errors", state.errors.length, "across all pipeline stages"],
            ["Slowest stage", bottleneckStage ? PIPELINE_STAGE_LABELS[bottleneckStage.stage] : "Not enough data yet", bottleneckStage ? `average ${formatDuration(bottleneckStage.avg)}` : null],
          ].map(([label, value, sub]) => (
            <div key={label} style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 16, padding: "10px 0", borderBottom: `1px solid ${theme.colors.rowBorder}` }}>
              <div>
                <dt style={{ fontSize: 14, color: theme.colors.text.primary }}>{label}</dt>
                {sub && <dd style={{ margin: 0, fontSize: 12, color: theme.colors.text.muted }}>{sub}</dd>}
              </div>
              <dd className="num" style={{ margin: 0, fontSize: 16, fontWeight: 600, color: theme.colors.text.primary, textAlign: "right" }}>{value}</dd>
            </div>
          ))}
        </dl>

        {/* Cascade funnel */}
        <div style={{ marginTop: 24 }}>
          <div style={S.sectionCardTitle}>How far pages got</div>
          {FUNNEL_STAGES.map((stage, i) => (
            <FunnelBar
              key={stage}
              label={FUNNEL_LABEL[stage]}
              count={cumulative[i]}
              max={maxFunnel}
              color={theme.colors.state[stage]}
            />
          ))}
          <div style={{ fontSize: theme.typography.size.xxs, color: theme.colors.text.muted, marginTop: 6 }}>
            Each bar counts nodes that reached at least that stage (a scored page has already been fetched and filtered).
          </div>
        </div>

        {/* Pipeline snapshot */}
        <div style={{ marginTop: 24 }}>
          <div style={S.sectionCardTitle}>Pipeline completions</div>
          {PIPELINE_STAGES.map(stage => {
            const stats = state.pipelineStats[stage];
            const pct = maxPipelineCompleted > 0 ? ((stats?.completed || 0) / maxPipelineCompleted) * 100 : 0;
            return (
              <div key={stage} style={S.breakdownRow}>
                <div style={S.breakdownLabel}>{PIPELINE_STAGE_LABELS[stage]}</div>
                <div style={S.breakdownBarTrack}>
                  <div style={S.breakdownBarFill(`${pct}%`, theme.colors.pipeline.completed)} />
                </div>
                <div style={S.breakdownValue}>{stats?.completed || 0}</div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
