import { useState, useReducer, useCallback, useMemo } from "react";
import { deriveMetrics } from "./state/metrics";
import { INITIAL_STATE } from "./state/initialState";
import { crawlReducer } from "./state/reducer";
import { useCrawlStream } from "./hooks/useCrawlStream";
import { useDemoMode } from "./hooks/useDemoMode";
import { useRoute } from "./hooks/useRoute";
import { stopCrawl } from "./api/client";
import { getTheme } from "./theme";

import Shell from "./app/Shell";
import NodeInspector from "./features/inspector/NodeInspector";
import OverviewPage from "./features/overview/OverviewPage";
import GraphView from "./features/graph/GraphView";
import PipelineMonitor from "./features/pipeline/PipelineMonitor";
import TimelineDock from "./features/timeline/TimelinePage";
import RunPage from "./features/run/RunPage";
import BlueprintManager from "./features/blueprints/BlueprintManager";
import DataExplorer from "./features/data/DataExplorer";
import ConfigPage from "./features/config/ConfigPage";

const theme = getTheme();
const WS_URL = import.meta.env.VITE_WS_URL ?? "ws://localhost:8765";

// Routes. The graph is home. The old #/overview, #/pipeline and #/timeline
// links still work: they land on the graph with the matching panel open.
const PAGE_ROUTES = new Set(["graph", "run", "blueprints", "data", "config"]);

function initialDemo() {
  try { return new URLSearchParams(window.location.search).has("demo"); } catch { return false; }
}

function EmptyCanvas({ onRun, onDemo }) {
  const btn = {
    height: 36, padding: "0 16px", borderRadius: theme.radii.md, fontSize: 14, fontWeight: 600,
    border: `1px solid ${theme.colors.text.primary}`,
  };
  return (
    <div style={{
      position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center",
      padding: 32, pointerEvents: "none",
    }}>
      <div style={{ maxWidth: 520, pointerEvents: "auto" }}>
        <h1 style={{
          fontFamily: theme.typography.fontDisplay, fontWeight: 600, fontSize: 34, lineHeight: 1.15,
          color: theme.colors.text.primary, textWrap: "balance", marginBottom: 14,
        }}>
          No crawl on the plate yet.
        </h1>
        <p style={{ fontSize: 15, lineHeight: 1.55, color: theme.colors.text.secondary, marginBottom: 22, maxWidth: "60ch" }}>
          CrawlViz scores every link before it fetches it. Start a crawl to watch the graph grow, then select a
          page to read why the crawler followed it. Vermilion marks the links it judged most promising.
        </p>
        <div style={{ display: "flex", gap: 12 }}>
          <button onClick={onRun} style={{ ...btn, background: theme.colors.text.primary, color: theme.colors.background.panel }}>
            Start a crawl
          </button>
          <button onClick={onDemo} style={{ ...btn, background: "transparent", color: theme.colors.text.primary }}>
            Load a synthetic sample
          </button>
        </div>
      </div>
    </div>
  );
}

export default function App() {
  const { path, navigate } = useRoute();
  const route = path.replace(/^\//, "") || "graph";
  const activeSection = PAGE_ROUTES.has(route) ? route : "graph";

  const [state, dispatch] = useReducer(crawlReducer, INITIAL_STATE);
  const [demoMode, setDemoMode] = useState(initialDemo);
  const [wsUrl] = useState(WS_URL);

  const [measuresOpen, setMeasuresOpen] = useState(route === "overview" || route === "pipeline");
  const [eventsOpen, setEventsOpen] = useState(route === "timeline");

  const [selectedNodeId, setSelectedNodeId] = useState(null);
  const selectedNode = selectedNodeId ? state.nodes.get(selectedNodeId) ?? null : null;
  const handleNodeClick = useCallback((node) => setSelectedNodeId(node.node_id), []);
  const handleClearSelection = useCallback(() => setSelectedNodeId(null), []);

  const replayIndex = state._replayIndex ?? null;

  useCrawlStream(demoMode ? () => {} : dispatch, wsUrl);
  useDemoMode(dispatch, demoMode);

  const handleSeek = useCallback((index) => dispatch({ type: "__REPLAY_SEEK", index }), []);
  const handleExitReplay = useCallback(() => dispatch({ type: "__REPLAY_EXIT" }), []);

  const metrics = useMemo(() => deriveMetrics(state), [state]);
  const navigateSection = useCallback((id) => navigate(`/${id}`), [navigate]);

  const onGraph = activeSection === "graph";

  const inspector = onGraph && selectedNode ? (
    <NodeInspector
      node={selectedNode}
      detail={state.nodeDetails[selectedNode.node_id]}
      allNodes={state.nodes}
      errors={state.errors}
      eventLog={state.eventLog}
      onSelectNode={setSelectedNodeId}
      onClose={handleClearSelection}
    />
  ) : null;

  const summary = state.nodes.size > 0
    ? `${state.nodes.size} pages · ${metrics.candidatesDropped} links skipped`
    : null;

  const banner = demoMode ? (
    <div role="status" style={{
      flexShrink: 0, padding: "8px 20px", fontSize: 13, fontWeight: 500,
      background: theme.colors.background.panel, color: theme.colors.text.primary,
      borderBottom: `1px solid ${theme.colors.background.border}`,
      display: "flex", justifyContent: "space-between", alignItems: "center",
    }}>
      <span>Synthetic sample: generated in the browser, not a real crawl.</span>
      <a
        href={window.location.pathname}
        style={{ color: theme.colors.text.primary, fontWeight: 600 }}
      >
        Leave sample
      </a>
    </div>
  ) : null;

  return (
    <Shell
      activeSection={activeSection}
      onNavigate={navigateSection}
      status={state.status}
      connectionStatus={demoMode ? "CONNECTED" : state.connectionStatus}
      stopReason={state.status === "STOPPED" ? state.stop_reason : null}
      summary={onGraph ? summary : null}
      errorCount={state.errors.length}
      measuresOpen={onGraph ? measuresOpen : undefined}
      onToggleMeasures={onGraph ? () => setMeasuresOpen(o => !o) : undefined}
      onShowErrors={() => { navigate("/graph"); setMeasuresOpen(true); }}
      onStop={() => { stopCrawl().catch(() => {}); }}
      banner={banner}
      inspector={inspector}
    >
      {onGraph && (
        <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column" }}>
          <div style={{ flex: 1, minHeight: 0, display: "flex" }}>
            <div style={{ flex: 1, minWidth: 0, position: "relative" }}>
              <GraphView
                nodes={state.nodes}
                edges={state.edges}
                candidates={state.candidates}
                replayIndex={replayIndex}
                onNodeClick={handleNodeClick}
                onBackgroundClick={handleClearSelection}
                selectedNodeId={selectedNodeId}
              />
              {state.nodes.size === 0 && (
                <EmptyCanvas onRun={() => navigate("/run")} onDemo={() => setDemoMode(true)} />
              )}
            </div>

            {measuresOpen && (
              <aside
                aria-label="Measurements"
                style={{
                  width: 460, flexShrink: 0, overflowY: "auto",
                  background: theme.colors.background.panel, borderLeft: `1px solid ${theme.colors.background.border}`,
                }}
              >
                <OverviewPage state={state} metrics={metrics} />
                <div style={{ borderTop: `1px solid ${theme.colors.background.border}` }}>
                  <PipelineMonitor pipelineStats={state.pipelineStats} eventLog={state.eventLog} errors={state.errors} />
                </div>
              </aside>
            )}
          </div>

          <TimelineDock
            eventLog={state.eventLog}
            replayIndex={replayIndex}
            onSeek={handleSeek}
            onExitReplay={handleExitReplay}
            expanded={eventsOpen}
            onToggleExpanded={() => setEventsOpen(o => !o)}
          />
        </div>
      )}

      {activeSection === "run" && (
        <RunPage onNavigate={navigateSection} state={state} metrics={metrics} />
      )}
      {activeSection === "blueprints" && <BlueprintManager />}
      {activeSection === "data" && <DataExplorer />}
      {activeSection === "config" && <ConfigPage />}
    </Shell>
  );
}
