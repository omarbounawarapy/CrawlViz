import { getTheme } from "../theme";
import {
  OverviewIcon, GraphIcon, PipelineIcon, TimelineIcon,
  RunIcon, BlueprintIcon, DataIcon, ConfigIcon,
} from "./Icons";

const theme = getTheme();
const shell = theme.shell;

// Single registry for the whole app's information architecture -- every
// section is one click away from every other, none of them unmount the
// WebSocket connection or drop the selected node the way V1's full-page
// route exile did (see docs/V2_ARCHITECTURE.md §A.2.1 / §B.3.1).
const SECTIONS = [
  { id: "overview", label: "Overview",   icon: OverviewIcon,   question: "What is this crawl doing right now?" },
  { id: "graph",     label: "Graph",     icon: GraphIcon,      question: "Why did the crawler traverse here?" },
  { id: "pipeline",  label: "Pipeline",  icon: PipelineIcon,   question: "Where is the bottleneck?" },
  { id: "timeline",  label: "Timeline",  icon: TimelineIcon,   question: "What sequence of decisions produced this outcome?" },
  { id: "run",       label: "Run",       icon: RunIcon,        question: "What am I about to run, and what did the last run do?" },
  { id: "blueprints",label: "Blueprints",icon: BlueprintIcon,  question: "What is this crawl configured to do?" },
  { id: "data",      label: "Data",      icon: DataIcon,       question: "What did we actually extract?" },
  { id: "config",    label: "Config",    icon: ConfigIcon,     question: "What assumptions is this crawl operating under?" },
];

const GLOBAL_CSS = `
  @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;600&family=Syne:wght@400;500;700;800&display=swap');
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html, body, #root { height: 100%; width: 100%; background: ${shell.background}; }
  ::-webkit-scrollbar { width: 4px; height: 4px; }
  ::-webkit-scrollbar-track { background: ${shell.scrollTrack}; }
  ::-webkit-scrollbar-thumb { background: ${theme.colors.scrubber}; border-radius: 2px; }
  input[type=range] { height: 4px; }
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

function ActivityBarBtn({ section, active, onClick, hasAlert }) {
  const Icon = section.icon;
  return (
    <button
      onClick={onClick}
      title={`${section.label} — ${section.question}`}
      style={{
        width: 38, height: 38, margin: "2px 7px",
        display: "flex", alignItems: "center", justifyContent: "center",
        borderRadius: theme.radii.md,
        background: active ? "rgba(90,122,255,0.14)" : "transparent",
        border: active ? `1px solid ${theme.colors.accent.blueDim}` : "1px solid transparent",
        color: active ? theme.colors.accent.blue : shell.textMuted,
        cursor: "pointer",
        position: "relative",
      }}
    >
      <Icon />
      {hasAlert && (
        <span style={{
          position: "absolute", top: 4, right: 4, width: 6, height: 6,
          borderRadius: "50%", background: theme.colors.accent.red,
        }} />
      )}
    </button>
  );
}

function ConnectionIndicator({ connectionStatus }) {
  const connected = connectionStatus === "CONNECTED";
  const label = connected ? "Live" : connectionStatus === "CONNECTING" ? "Connecting…" : "Disconnected";
  const color = connected ? theme.colors.accent.green : theme.colors.accent.red;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6 }} title={`WebSocket: ${label}`}>
      <span style={{
        width: 6, height: 6, borderRadius: "50%",
        background: color,
        animation: connected ? "none" : "pulse 1.4s ease-in-out infinite",
      }} />
      <span style={{ fontSize: 9, color: shell.textMuted, letterSpacing: "0.06em" }}>{label.toUpperCase()}</span>
    </div>
  );
}

function CrawlStatusBadge({ status }) {
  const map = {
    RUNNING:    { bg: "rgba(64,255,128,0.12)", border: "rgba(64,255,128,0.35)", dot: theme.colors.accent.green },
    STOPPED:    { bg: "rgba(255,80,80,0.12)",  border: "rgba(255,80,80,0.35)",  dot: theme.colors.accent.red },
    CONNECTING: { bg: "rgba(120,120,160,0.12)",border: "rgba(120,120,160,0.3)", dot: "#8080a0" },
  };
  const s = map[status] || map.CONNECTING;
  return (
    <div style={{
      display: "inline-flex", alignItems: "center", gap: 6,
      padding: "3px 10px", borderRadius: 20,
      background: s.bg, border: `1px solid ${s.border}`,
    }}>
      <span style={{
        width: 6, height: 6, borderRadius: "50%", background: s.dot,
        animation: status === "RUNNING" ? "pulse 1.4s ease-in-out infinite" : "none",
      }} />
      <span style={{ fontSize: 9, letterSpacing: "0.08em", color: s.dot }}>{status}</span>
    </div>
  );
}

/**
 * Shell — the persistent IDE-style layout every section renders inside.
 *
 * Props:
 *   activeSection, onNavigate(sectionId): activity-bar routing
 *   status, connectionStatus, stopReason: for the top-bar status cluster
 *   errorCount: unread-ish count that lights a red dot on the section
 *     that surfaces errors most directly (kept simple: Pipeline)
 *   subtitle: optional short right-aligned context string (e.g. blueprint name)
 *   children: the active section's content
 *   inspector: optional docked right-hand panel (Node Inspector)
 */
export default function Shell({
  activeSection, onNavigate, status, connectionStatus, stopReason,
  errorCount = 0, subtitle, children, inspector,
}) {
  const active = SECTIONS.find(s => s.id === activeSection) || SECTIONS[0];

  return (
    <>
      <style>{GLOBAL_CSS}</style>
      <div style={{
        display: "flex", width: "100vw", height: "100vh",
        background: shell.background, fontFamily: theme.typography.fontMono, overflow: "hidden",
      }}>
        {/* Activity bar */}
        <div style={{
          display: "flex", flexDirection: "column", alignItems: "center",
          width: 52, flexShrink: 0, background: shell.surface,
          borderRight: `1px solid ${shell.border}`, paddingTop: 12, paddingBottom: 12,
          justifyContent: "space-between",
        }}>
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 2, width: "100%" }}>
            <div style={{ marginBottom: 10 }}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                <circle cx="12" cy="10" r="4" fill={theme.colors.accent.blue} opacity="0.9" />
                <path d="M12 14v6M8 16l-4 3M16 16l4 3M6 8L2 5M18 8l4-5M8 8L4 6M16 8l4-2"
                  stroke={theme.colors.accent.blue} strokeWidth="1.5" strokeLinecap="round" opacity="0.7" />
              </svg>
            </div>
            {SECTIONS.map(section => (
              <ActivityBarBtn
                key={section.id}
                section={section}
                active={section.id === activeSection}
                onClick={() => onNavigate(section.id)}
                hasAlert={section.id === "pipeline" && errorCount > 0}
              />
            ))}
          </div>
        </div>

        {/* Content column */}
        <div style={{ display: "flex", flexDirection: "column", flex: 1, minWidth: 0, height: "100%" }}>
          {/* Top bar */}
          <div style={{
            display: "flex", alignItems: "center", justifyContent: "space-between",
            height: 42, flexShrink: 0, padding: "0 16px",
            borderBottom: `1px solid ${shell.border}`, background: shell.surface,
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 14, minWidth: 0 }}>
              <Logo />
              <div style={{ width: 1, height: 18, background: shell.border }} />
              <div style={{ minWidth: 0 }}>
                <div style={{
                  fontFamily: theme.typography.fontDisplay, fontSize: 12, fontWeight: 600,
                  color: shell.textBright, whiteSpace: "nowrap",
                }}>
                  {active.label}
                </div>
                {subtitle && (
                  <div style={{
                    fontSize: 9, color: shell.textMuted, whiteSpace: "nowrap",
                    overflow: "hidden", textOverflow: "ellipsis", maxWidth: "48ch",
                  }}>
                    {subtitle}
                  </div>
                )}
              </div>
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
              {stopReason && (
                <span style={{ fontSize: 9, color: shell.textMuted }}>{stopReason}</span>
              )}
              <CrawlStatusBadge status={status} />
              <ConnectionIndicator connectionStatus={connectionStatus} />
            </div>
          </div>

          {/* Main area */}
          <div style={{ flex: 1, minHeight: 0, display: "flex", overflow: "hidden" }}>
            <div style={{ flex: 1, minWidth: 0, overflow: "hidden", position: "relative", background: shell.surface }}>
              {children}
            </div>
            {inspector}
          </div>
        </div>
      </div>
    </>
  );
}
