import { useMemo, useState } from "react";
import { getTheme } from "../../theme";
import { createComponentStyles } from "../../theme/components";
import { formatDuration, hostnameOf, pathOf, shortId } from "../../utils/formatters";

const theme = getTheme();
const S = createComponentStyles(theme);

const TABS = ["Overview", "Scoring", "Activity"];

// Every named sub-signal the cascade's NLP stage can produce (see
// nlp/feature_extractor.py FeatureExtractor.extract_all / traceability's
// NLP_SimilarityScored) -- fixed order so the breakdown reads the same way
// for every node instead of reshuffling by whatever keys happened to be present.
const NLP_SIGNAL_ORDER = [
  "target_similarity", "contextual_consistency", "novelty_injection",
  "region_density", "cluster_distance", "coverage_gap",
  "lexical_overlap", "semantic_delta",
];

function orderedSignals(breakdown) {
  if (!breakdown) return [];
  const known = NLP_SIGNAL_ORDER.filter(k => k in breakdown).map(k => [k, breakdown[k]]);
  const rest = Object.entries(breakdown).filter(([k]) => !NLP_SIGNAL_ORDER.includes(k));
  return [...known, ...rest];
}

function relativeAge(createdAt) {
  if (!createdAt) return "—";
  const seconds = Date.now() / 1000 - createdAt;
  if (seconds < 60) return `${Math.round(seconds)}s ago`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`;
  return `${Math.round(seconds / 3600)}h ago`;
}

function StateBadge({ state }) {
  const color = theme.colors.state.label[state] || theme.colors.text.muted;
  const fill = theme.colors.state[state] || theme.colors.background.border;
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 5,
      fontSize: theme.typography.size.xxs, color, fontFamily: theme.typography.fontMono,
      padding: "2px 7px", borderRadius: theme.radii.sm, background: fill,
      letterSpacing: theme.typography.letterSpacing.wide,
    }}>
      {state}
    </span>
  );
}

function Row({ label, value, mono = true }) {
  return (
    <div style={S.nodeDetailRow}>
      <div style={S.nodeDetailKey}>{label}</div>
      <div style={{ ...S.nodeDetailVal, maxWidth: "220px", fontFamily: mono ? theme.typography.fontMono : theme.typography.fontDisplay }}>
        {value ?? "—"}
      </div>
    </div>
  );
}

function OverviewTab({ node, children, onSelectNode }) {
  return (
    <div>
      <div style={{ marginBottom: 14 }}>
        <div style={S.breakdownLabel}>URL</div>
        <div style={S.inspectorUrl}>{node.url}</div>
      </div>
      <Row label="State" value={<StateBadge state={node.state} />} />
      <Row label="Depth" value={node.depth} />
      <Row label="Priority" value={typeof node.priority === "number" ? node.priority.toFixed(3) : "—"} />
      <Row label="LLM score" value={node.llm_score || node.llm_score === 0 ? node.llm_score : "—"} />
      <Row label="Node ID" value={shortId(node.node_id, 12)} />
      <Row
        label="Parent"
        value={node.parent_id ? (
          <button onClick={() => onSelectNode(node.parent_id)} style={linkBtnStyle}>{shortId(node.parent_id, 12)}</button>
        ) : "— (seed)"}
      />
      <Row label="Discovered" value={relativeAge(node.created_at)} />
      <Row label="Links found" value={node.links_accepted != null ? `${node.links_accepted} accepted / ${node.links_rejected ?? 0} rejected` : "—"} />
      <Row label="Items stored" value={node.items_accepted ?? "—"} />

      <div style={{ ...S.sectionCardTitle, marginTop: 16 }}>Children ({children.length})</div>
      {children.length === 0 ? (
        <div style={{ fontSize: theme.typography.size.xxs, color: theme.colors.text.muted }}>
          {node.state === "EXPANDED" ? "Expanded with no surviving children." : "Not expanded yet."}
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 3, maxHeight: 180, overflowY: "auto" }}>
          {children.map(c => (
            <button key={c.node_id} onClick={() => onSelectNode(c.node_id)} style={{ ...linkBtnStyle, textAlign: "left", display: "flex", justifyContent: "space-between", gap: 8 }}>
              <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{pathOf(c.url) || hostnameOf(c.url)}</span>
              <StateBadge state={c.state} />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

const linkBtnStyle = {
  background: "transparent", border: "none", padding: "3px 0",
  color: theme.colors.accent.blue, cursor: "pointer",
  fontFamily: theme.typography.fontMono, fontSize: theme.typography.size.xxs,
  width: "100%",
};

function ScoringTab({ detail }) {
  if (!detail) {
    return (
      <div style={S.emptyState}>
        <div>No cascade scoring recorded for this node.</div>
        <div style={{ fontSize: theme.typography.size.xxs }}>
          This is normal for a seed URL — seeds enter the graph directly, without going through the scoring cascade.
        </div>
      </div>
    );
  }

  const signals = orderedSignals(detail.nlp_breakdown);
  const maxAbs = Math.max(0.001, ...signals.map(([, v]) => Math.abs(v)));

  return (
    <div>
      <div style={S.sectionCardTitle}>NLP breakdown</div>
      {signals.length === 0 ? (
        <div style={{ fontSize: theme.typography.size.xxs, color: theme.colors.text.muted, marginBottom: 12 }}>
          No sub-signal breakdown available.
        </div>
      ) : signals.map(([key, value]) => {
        const pct = Math.min(100, (Math.abs(value) / maxAbs) * 100);
        const positive = value >= 0;
        return (
          <div key={key} style={S.breakdownRow}>
            <div style={S.breakdownLabel} title={key}>{key.replace(/_/g, " ")}</div>
            <div style={S.breakdownBarTrack}>
              <div style={S.breakdownBarFill(`${pct}%`, positive ? theme.colors.accent.blue : theme.colors.accent.red)} />
            </div>
            <div style={S.breakdownValue}>{value.toFixed(2)}</div>
          </div>
        );
      })}

      <div style={{ height: 1, background: theme.colors.background.border, margin: "14px 0" }} />

      <Row label="NLP score" value={typeof detail.nlp_score === "number" ? detail.nlp_score.toFixed(3) : "—"} />
      <Row
        label="LLM score"
        value={detail.llm_score != null
          ? detail.llm_score
          : <span style={{ color: theme.colors.state.label.TRUSTED }}>skipped — trusted on NLP alone</span>}
      />
      <Row label="Final priority" value={typeof detail.priority === "number" ? detail.priority.toFixed(3) : "—"} />
      <Row label="Strategy" value={detail.priority_strategy} />
    </div>
  );
}

function ActivityTab({ history, errors }) {
  return (
    <div>
      {errors.length > 0 && (
        <>
          <div style={{ ...S.sectionCardTitle, color: theme.colors.accent.red }}>Errors ({errors.length})</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6, marginBottom: 16 }}>
            {errors.map((e, i) => (
              <div key={i} style={{
                background: "rgba(255,80,80,0.08)", border: `1px solid rgba(255,80,80,0.25)`,
                borderRadius: theme.radii.md, padding: 8,
              }}>
                <div style={{ fontSize: theme.typography.size.xxs, color: theme.colors.accent.red }}>
                  {e.stage} — {e.error_type}
                </div>
                <div style={{ fontSize: theme.typography.size.xxs, color: theme.colors.text.secondary, marginTop: 2 }}>
                  {e.error_message}
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      <div style={S.sectionCardTitle}>Pipeline history</div>
      {history.length === 0 ? (
        <div style={{ fontSize: theme.typography.size.xxs, color: theme.colors.text.muted }}>
          No pipeline-stage events recorded for this node in the current event log
          {/* i.e. it may have existed before this session's log started, e.g. after a reconnect */}
          .
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column" }}>
          {history.map((h, i) => (
            <div key={i} style={{ ...S.nodeDetailRow, borderBottom: `1px solid ${theme.colors.rowBorder}` }}>
              <div style={{ ...S.nodeDetailKey, minWidth: 90 }}>{h.stage}</div>
              <div style={{ ...S.nodeDetailVal, maxWidth: "none", flex: 1, color: h.phase === "failed" ? theme.colors.accent.red : theme.colors.text.secondary }}>
                {h.phase}{h.detail ? ` — ${h.detail}` : ""}
              </div>
              <div style={{ fontSize: theme.typography.size.xxs, color: theme.colors.text.muted, flexShrink: 0 }}>
                {formatDuration(h.duration_ms)}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/**
 * Docked Node Inspector. Persists across sections (not just Graph) so
 * selecting a node in one view keeps it visible while browsing another --
 * see docs/V2_ARCHITECTURE.md §B.3.3.
 */
export default function NodeInspector({ node, detail, allNodes, errors, eventLog, onSelectNode, onClose }) {
  const [tab, setTab] = useState("Overview");

  const children = useMemo(() => {
    if (!node) return [];
    const out = [];
    for (const n of allNodes.values()) {
      if (n.parent_id === node.node_id) out.push(n);
    }
    return out;
  }, [node, allNodes]);

  const history = useMemo(() => {
    if (!node) return [];
    return eventLog
      .filter(e => e.type === "PIPELINE_EVENT" && e.node_id === node.node_id)
      .map(e => ({ stage: e.stage, phase: e.phase, duration_ms: e.duration_ms, detail: e.detail }));
  }, [node, eventLog]);

  const nodeErrors = useMemo(() => {
    if (!node) return [];
    return errors.filter(e => e.node_id === node.node_id);
  }, [node, errors]);

  if (!node) return null;

  return (
    <div style={S.inspectorDock}>
      <div style={S.inspectorHeader}>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: theme.typography.size.xs, fontFamily: theme.typography.fontDisplay, fontWeight: 600, color: theme.colors.text.primary }}>
            {hostnameOf(node.url)}
          </div>
          <div style={{ fontSize: theme.typography.size.xxs, color: theme.colors.text.muted, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: "260px" }}>
            {pathOf(node.url)}
          </div>
        </div>
        <button onClick={onClose} style={S.nodeDetailCloseBtn}>✕</button>
      </div>

      <div style={S.tabRow}>
        {TABS.map(t => (
          <button key={t} onClick={() => setTab(t)} style={S.tabBtn(tab === t)}>
            {t}{t === "Activity" && nodeErrors.length > 0 ? ` (${nodeErrors.length})` : ""}
          </button>
        ))}
      </div>

      <div style={S.panelScroll}>
        {tab === "Overview" && <OverviewTab node={node} children={children} onSelectNode={onSelectNode} />}
        {tab === "Scoring" && <ScoringTab detail={detail} />}
        {tab === "Activity" && <ActivityTab history={history} errors={nodeErrors} />}
      </div>
    </div>
  );
}
