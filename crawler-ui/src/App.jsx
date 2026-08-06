import { useState, useReducer, useCallback, useMemo } from "react";
import { deriveMetrics } from "./state/metrics";
import { INITIAL_STATE } from "./state/initialState";
import { crawlReducer } from "./state/reducer";
import { useCrawlStream } from "./hooks/useCrawlStream";
import { useDemoMode } from "./hooks/useDemoMode";
import { useRoute } from "./hooks/useRoute";

import Shell from "./app/Shell";
import NodeInspector from "./features/inspector/NodeInspector";
import OverviewPage from "./features/overview/OverviewPage";
import GraphView from "./features/graph/GraphView";
import Legend from "./features/graph/Legend";
import PipelineMonitor from "./features/pipeline/PipelineMonitor";
import TimelinePage from "./features/timeline/TimelinePage";
import RunPage from "./features/run/RunPage";
import BlueprintManager from "./features/blueprints/BlueprintManager";
import DataExplorer from "./features/data/DataExplorer";
import ConfigPage from "./features/config/ConfigPage";

const WS_URL = import.meta.env.VITE_WS_URL ?? "ws://localhost:8765";

// Sections whose whole point is explaining a specific crawl node -- these
// get the docked Node Inspector alongside them. Run/Blueprints/Data/Config
// aren't about an individual node, so they get the full content width
// instead (see docs/V2_ARCHITECTURE.md §B.3.1 / §B.3.3).
const INSPECTOR_SECTIONS = new Set(["overview", "graph", "pipeline", "timeline"]);

export default function App() {
  const { path, navigate } = useRoute();
  const activeSection = path.replace(/^\//, "") || "overview";

  const [state, dispatch] = useReducer(crawlReducer, INITIAL_STATE);
  const [demoMode] = useState(false);
  const [wsUrl] = useState(WS_URL);

  const [selectedNodeId, setSelectedNodeId] = useState(null);
  const selectedNode = selectedNodeId ? state.nodes.get(selectedNodeId) ?? null : null;
  const handleNodeClick = useCallback((node) => setSelectedNodeId(node.node_id), []);
  const handleClearSelection = useCallback(() => setSelectedNodeId(null), []);

  const replayIndex = state._replayIndex ?? null;

  useCrawlStream(demoMode ? () => {} : dispatch, wsUrl);
  useDemoMode(dispatch, demoMode);

  const handleSeek = useCallback((index) => {
    dispatch({ type: "__REPLAY_SEEK", index });
  }, []);

  const handleExitReplay = useCallback(() => {
    dispatch({ type: "__REPLAY_EXIT" });
  }, []);

  const metrics = useMemo(() => deriveMetrics(state), [state]);

  const navigateSection = useCallback((id) => navigate(`/${id}`), [navigate]);

  const inspector = INSPECTOR_SECTIONS.has(activeSection) && selectedNode ? (
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

  return (
    <Shell
      activeSection={activeSection}
      onNavigate={navigateSection}
      status={state.status}
      connectionStatus={state.connectionStatus}
      stopReason={state.status === "STOPPED" ? state.stop_reason : null}
      errorCount={state.errors.length}
      inspector={inspector}
    >
      {activeSection === "overview" && (
        <OverviewPage state={state} metrics={metrics} />
      )}

      {activeSection === "graph" && (
        <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column" }}>
          <div style={{ padding: "8px 16px", borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
            <Legend />
          </div>
          <div style={{ flex: 1, minHeight: 0 }}>
            <GraphView
              nodes={state.nodes}
              edges={state.edges}
              candidates={state.candidates}
              replayIndex={replayIndex}
              onNodeClick={handleNodeClick}
              onBackgroundClick={handleClearSelection}
              selectedNodeId={selectedNodeId}
            />
          </div>
        </div>
      )}

      {activeSection === "pipeline" && (
        <PipelineMonitor pipelineStats={state.pipelineStats} eventLog={state.eventLog} errors={state.errors} />
      )}

      {activeSection === "timeline" && (
        <TimelinePage
          eventLog={state.eventLog}
          replayIndex={replayIndex}
          onSeek={handleSeek}
          onExitReplay={handleExitReplay}
        />
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
