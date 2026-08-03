import { useMemo } from "react";
import { getTheme } from "../../theme";
import { createComponentStyles } from "../../theme/components";
import { PIPELINE_STAGES, PIPELINE_STAGE_LABELS } from "../../state/nodeStates";
import { formatDuration } from "../../utils/formatters";

const theme = getTheme();
const S = createComponentStyles(theme);

const FUNNEL_STAGES = ["CREATED", "FETCHED", "FILTERED", "SCORED", "EXPANDED"];

function FunnelBar({ label, count, max, color }) {
  const pct = max > 0 ? Math.max(2, (count / max) * 100) : 0;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
      <div style={{ width: 76, fontSize: theme.typography.size.xxs, color: theme.colors.text.muted, textTransform: "uppercase", letterSpacing: theme.typography.letterSpacing.wide }}>
        {label}
      </div>
      <div style={{ flex: 1, height: 18, background: theme.colors.background.border, borderRadius: theme.radii.sm, overflow: "hidden" }}>
        <div style={{ width: `${pct}%`, height: "100%", background: color, transition: "width 0.3s ease" }} />
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
        {/* Top stats */}
        <div style={S.statTileGrid()}>
          <div style={S.statTile}>
            <div style={S.statTileLabel}>Nodes discovered</div>
            <div style={S.statTileValue(theme.colors.accent.blue)}>{state.nodes.size}</div>
            <div style={S.statTileSub}>{state.edges.size} edges</div>
          </div>
          <div style={S.statTile}>
            <div style={S.statTileLabel}>Throughput</div>
            <div style={S.statTileValue(theme.colors.accent.green)}>{pagesPerSec.toFixed(2)}</div>
            <div style={S.statTileSub}>pages / sec</div>
          </div>
          <div style={S.statTile}>
            <div style={S.statTileLabel}>Elapsed</div>
            <div style={S.statTileValue()}>{formatDuration(elapsed * 1000)}</div>
            <div style={S.statTileSub}>{state.status}{state.stop_reason ? ` — ${state.stop_reason}` : ""}</div>
          </div>
          <div style={S.statTile}>
            <div style={S.statTileLabel}>Candidates excluded</div>
            <div style={S.statTileValue(theme.colors.state.label.DROPPED)}>{metrics.candidatesDropped}</div>
            <div style={S.statTileSub}>of {totalCandidates} evaluated without an LLM call ({(dropRate * 100).toFixed(0)}% dropped)</div>
          </div>
          <div style={S.statTile}>
            <div style={S.statTileLabel}>Errors</div>
            <div style={S.statTileValue(state.errors.length > 0 ? theme.colors.accent.red : theme.colors.text.primary)}>{state.errors.length}</div>
            <div style={S.statTileSub}>across all pipeline stages</div>
          </div>
          <div style={S.statTile}>
            <div style={S.statTileLabel}>Slowest stage</div>
            <div style={S.statTileValue(theme.colors.accent.gold)}>
              {bottleneckStage ? PIPELINE_STAGE_LABELS[bottleneckStage.stage] : "—"}
            </div>
            <div style={S.statTileSub}>{bottleneckStage ? `avg ${formatDuration(bottleneckStage.avg)}` : "not enough data yet"}</div>
          </div>
        </div>

        {/* Cascade funnel */}
        <div style={{ ...S.sectionCard, marginTop: 20 }}>
          <div style={S.sectionCardTitle}>Traversal funnel — how far nodes got</div>
          {FUNNEL_STAGES.map((stage, i) => (
            <FunnelBar
              key={stage}
              label={stage}
              count={cumulative[i]}
              max={maxFunnel}
              color={theme.colors.state[stage]}
            />
          ))}
          <div style={{ fontSize: theme.typography.size.xxs, color: theme.colors.text.muted, marginTop: 6 }}>
            Each bar counts nodes that reached at least that stage (a SCORED node has already passed FETCHED and FILTERED).
          </div>
        </div>

        {/* Pipeline snapshot */}
        <div style={{ ...S.sectionCard, marginTop: 16 }}>
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
