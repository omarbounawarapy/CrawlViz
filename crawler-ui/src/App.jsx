import { useState, useReducer, useCallback } from "react";
import { deriveMetrics } from "./state/metrics";
import { INITIAL_STATE } from "./state/initialState";
import { crawlReducer } from "./state/reducer";
import { useCrawlStream } from "./hooks/useCrawlStream";
import { useDemoMode } from "./hooks/useDemoMode";
import { getTheme } from "./theme";

import Legend from "./components/common/Legend";
import GraphView from "./components/graph/GraphView";
import EventTimeline from "./components/timeline/EventTimeline";
import MetricsPanel from "./components/metrics/MetricsPanel";
import NodeDetailsPanel from "./components/graph/NodeDetailsPanel";

import TemplateManager from "./pages/TemplateManager";
import RunScreen from "./pages/RunScreen";
import ValidationView from "./pages/ValidationView";

const theme = getTheme();
const shell = theme.colors.shell;

const WS_URL = import.meta.env.VITE_WS_URL ?? "ws://localhost:8765";

// ── simple in-app router ─────────────────────────────────────────
function useRoute() {
  const [route, setRoute] = useState(
    window.location.hash.replace("#", "") || "/"
  );
  const navigate = useCallback((path) => {
    window.location.hash = path;
    setRoute(path);
  }, []);
  return [route, navigate];
}

function NavBtn({ label, active, onClick }) {
  return (
    <button
      onClick={onClick}
      style={{
        background: active ? shell.border : "transparent",
        border: "none",
        borderRadius: 4,
        padding: "4px 12px",
        fontSize: 9,
        color: active ? shell.textPrimary : shell.textMuted,
        cursor: "pointer",
        letterSpacing: "0.08em",
        fontFamily: theme.typography.fontMono,
        textTransform: "uppercase",
      }}
    >
      {label}
    </button>
  );
}

const GLOBAL_CSS = `
  @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;600&family=Syne:wght@400;500;700;800&display=swap');
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html, body, #root { height: 100%; width: 100%; background: ${shell.background}; }
  ::-webkit-scrollbar { width: 4px; }
  ::-webkit-scrollbar-track { background: ${shell.scrollTrack}; }
  ::-webkit-scrollbar-thumb { background: ${theme.colors.scrubber}; border-radius: 2px; }
  @keyframes pulse {
    0%, 100% { opacity: 1; box-shadow: 0 0 6px currentColor; }
    50% { opacity: 0.6; box-shadow: 0 0 2px currentColor; }
  }
`;

function Logo() {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
        <circle cx="12" cy="10" r="4" fill={theme.colors.accent.blue} opacity="0.9" />
        <path
          d="M12 14v6M8 16l-4 3M16 16l4 3M6 8L2 5M18 8l4-5M8 8L4 6M16 8l4-2"
          stroke={theme.colors.accent.blue} strokeWidth="1.5" strokeLinecap="round" opacity="0.7"
        />
      </svg>
      <span style={{ fontSize: 13, fontFamily: theme.typography.fontDisplay, fontWeight: 700, color: shell.textBright, letterSpacing: "0.04em" }}>
        CRAWL<span style={{ color: theme.colors.accent.blue }}>VIZ</span>
      </span>
    </div>
  );
}

export default function App() {
  const [route, navigate] = useRoute();

  const [state, dispatch] = useReducer(crawlReducer, INITIAL_STATE);
  const [demoMode] = useState(false);
  const [wsUrl] = useState(WS_URL);
  const [activeTab, setActiveTab] = useState("graph");

  const [selectedNodeId, setSelectedNodeId] = useState(null);
  const selectedNode = selectedNodeId ? state.nodes.get(selectedNodeId) ?? null : null;
  const handleNodeClick = useCallback((node) => setSelectedNodeId(node.node_id), []);
  const handlePanelClose = useCallback(() => setSelectedNodeId(null), []);

  const replayIndex = state._replayIndex ?? null;

  useCrawlStream(demoMode ? () => {} : dispatch, wsUrl);
  useDemoMode(dispatch, demoMode);

  const handleSeek = useCallback((index) => {
    dispatch({ type: "__REPLAY_SEEK", index });
  }, []);

  const handleExitReplay = useCallback(() => {
    dispatch({ type: "__REPLAY_EXIT" });
  }, []);

  const metrics = deriveMetrics(state);
  const safeMetrics = {
    total_links_found: metrics?.total_links_found ?? 0,
    elapsed_seconds: metrics?.elapsed_seconds ?? 0,
  };

  // full-page routes (templates, run, validation)
  const isFullPage = ["/templates", "/run", "/validation"].includes(route);

  if (isFullPage) {
    return (
      <>
        <style>{GLOBAL_CSS}</style>
        <div
          style={{
            display: "grid",
            gridTemplateRows: "44px 1fr",
            height: "100vh",
            background: shell.background,
            color: shell.textPrimary,
            fontFamily: theme.typography.fontMono,
            overflow: "hidden",
          }}
        >
          {/* Top bar */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              padding: "0 20px",
              borderBottom: `1px solid ${shell.border}`,
              background: shell.surface,
            }}
          >
            <Logo />
            <div style={{ display: "flex", gap: 2 }}>
              <NavBtn label="Graph"      active={false}                   onClick={() => navigate("/")} />
              <NavBtn label="Run"        active={route === "/run"}         onClick={() => navigate("/run")} />
              <NavBtn label="Templates"  active={route === "/templates"}   onClick={() => navigate("/templates")} />
              <NavBtn label="Validation" active={route === "/validation"}  onClick={() => navigate("/validation")} />
            </div>
          </div>

          {/* Page */}
          <div style={{ overflow: "hidden" }}>
            {route === "/templates"  && <TemplateManager />}
            {route === "/run"        && <RunScreen onNavigate={navigate} />}
            {route === "/validation" && <ValidationView />}
          </div>
        </div>
      </>
    );
  }

  // default: graph / timeline / metrics workspace
  return (
    <>
      <style>{GLOBAL_CSS + `input[type=range] { height: 4px; }`}</style>

      <div
        style={{
          display: "grid",
          gridTemplateRows: "44px 1fr",
          gridTemplateColumns: "1fr 280px",
          height: "100vh",
          background: shell.background,
          color: shell.textPrimary,
          fontFamily: theme.typography.fontMono,
          overflow: "hidden",
        }}
      >
        {/* Top bar */}
        <div
          style={{
            gridColumn: "1 / -1",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "0 20px",
            borderBottom: `1px solid ${shell.border}`,
            background: shell.surface,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
            <Logo />
            <Legend />
          </div>

          <div style={{ display: "flex", gap: 2 }}>
            {["graph", "timeline", "metrics"].map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                style={{
                  background: activeTab === tab ? shell.border : "transparent",
                  border: "none",
                  borderRadius: 4,
                  padding: "4px 12px",
                  fontSize: 9,
                  color: activeTab === tab ? shell.textPrimary : shell.textMuted,
                  cursor: "pointer",
                  letterSpacing: "0.08em",
                  fontFamily: theme.typography.fontMono,
                  textTransform: "uppercase",
                }}
              >
                {tab}
              </button>
            ))}

            <div style={{ width: 1, background: shell.border, margin: "8px 6px" }} />

            <NavBtn label="Run"        active={false} onClick={() => navigate("/run")} />
            <NavBtn label="Templates"  active={false} onClick={() => navigate("/templates")} />
            <NavBtn label="Validation" active={false} onClick={() => navigate("/validation")} />
          </div>
        </div>

        {/* Main panel */}
        <div
          style={{
            gridColumn: 1,
            gridRow: 2,
            position: "relative",
            overflow: "hidden",
            background: shell.surface,
            borderRight: `1px solid ${shell.border}`,
          }}
        >
          <div
            style={{
              position: "absolute",
              inset: 0,
              opacity: activeTab === "graph" ? 1 : 0,
              pointerEvents: activeTab === "graph" ? "auto" : "none",
              transition: "opacity 0.2s",
            }}
          >
            <GraphView
              nodes={state.nodes}
              edges={state.edges}
              replayIndex={replayIndex}
              onNodeClick={handleNodeClick}
              selectedNodeId={selectedNodeId}
            />
          </div>

          {activeTab === "timeline" && (
            <div style={{ position: "absolute", inset: 0 }}>
              <EventTimeline
                eventLog={state.eventLog}
                replayIndex={replayIndex}
                onSeek={handleSeek}
                onExitReplay={handleExitReplay}
              />
            </div>
          )}

          {activeTab === "metrics" && (
            <div style={{ position: "absolute", inset: 0 }}>
              <MetricsPanel
                metrics={metrics}
                nodes={state.nodes}
                edges={state.edges}
                status={state.status}
                stopReason={state.stop_reason}
                replayIndex={replayIndex}
              />
            </div>
          )}

          {selectedNode && (
            <NodeDetailsPanel node={selectedNode} onClose={handlePanelClose} />
          )}
        </div>

        {/* Right sidebar */}
        <div
          style={{
            gridColumn: 2,
            gridRow: 2,
            borderLeft: `1px solid ${shell.border}`,
            display: "flex",
            flexDirection: "column",
            overflow: "hidden",
            background: shell.surface,
          }}
        >
          <div
            style={{
              padding: "10px 14px",
              borderBottom: `1px solid ${shell.border}`,
              display: "grid",
              gridTemplateColumns: "1fr 1fr",
              gap: "6px 12px",
            }}
          >
            {[
              ["NODES",   state.nodes.size,                              theme.colors.accent.blue],
              ["EDGES",   state.edges.size,                              theme.colors.accent.blueDim],
              ["LINKS",   safeMetrics.total_links_found,                 shell.accentTeal],
              ["ELAPSED", `${safeMetrics.elapsed_seconds.toFixed(1)}s`,  theme.colors.accent.gold],
            ].map(([label, val, color]) => (
              <div key={label}>
                <div style={{ fontSize: 8, color: shell.textDim }}>{label}</div>
                <div style={{ fontSize: 18, color, fontWeight: 600 }}>{val}</div>
              </div>
            ))}
          </div>

          <div style={{ padding: "8px 14px", borderBottom: `1px solid ${shell.border}` }}>
            <span style={{ fontSize: 10 }}>{state.status}</span>
          </div>

          <div style={{ flex: 1, overflow: "hidden" }}>
            <EventTimeline
              eventLog={state.eventLog}
              replayIndex={replayIndex}
              onSeek={handleSeek}
              onExitReplay={handleExitReplay}
            />
          </div>
        </div>
      </div>
    </>
  );
}
