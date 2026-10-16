import Spider from "../features/loading/Spider";
import { useState } from "react";
import { getTheme } from "../theme";
import { Hint } from "../features/common/Hint";

const theme = getTheme();
const { shell, typography: type } = theme;

// Flat, labelled navigation. The graph is the home view; the old Overview,
// Pipeline and Timeline sections now live inside it as the Measurements
// drawer and the timeline bar (see App.jsx).
const SECTIONS = [
  { id: "graph",      label: "Graph",      question: "Why did the crawler traverse here?" },
  { id: "run",        label: "Run",        question: "What am I about to run, and what did the last run do?" },
  { id: "blueprints", label: "Blueprints", question: "What is this crawl configured to do?" },
  { id: "data",       label: "Data",       question: "What did the crawler extract?" },
  { id: "config",     label: "Config",     question: "What assumptions is this crawl operating under?" },
  { id: "benchmark",  label: "Benchmark",  question: "Does the cascade beat the baselines, and at what cost?" },
];

function StatusMark({ status }) {
  // State is carried by shape and word, not colour alone.
  const size = 10;
  if (status === "RUNNING") {
    return (
      <svg width={size} height={size} viewBox="0 0 10 10" aria-hidden="true" className="breathe">
        <circle cx="5" cy="5" r="4" fill={theme.colors.text.primary} />
      </svg>
    );
  }
  if (status === "STOPPED") {
    return (
      <svg width={size} height={size} viewBox="0 0 10 10" aria-hidden="true">
        <rect x="1" y="1" width="8" height="8" fill={theme.colors.text.secondary} />
      </svg>
    );
  }
  return (
    <svg width={size} height={size} viewBox="0 0 10 10" aria-hidden="true">
      <circle cx="5" cy="5" r="3.5" fill="none" stroke={theme.colors.text.muted} strokeWidth="1.5" />
    </svg>
  );
}

const STATUS_WORD = { RUNNING: "Crawling", STOPPED: "Finished", CONNECTING: "Waiting for backend", IDLE: "Idle" };

// The wordmark is also the way back to the landing page.
function Wordmark() {
  return (
    <a href="#/" title="CrawlViz home" style={{
      display: "inline-flex", alignItems: "center", gap: 8, textDecoration: "none",
      fontFamily: type.fontDisplay, fontSize: 20, fontWeight: 600,
      color: shell.textBright, letterSpacing: "-0.01em",
    }}>
      <Spider size={26} className="wordmark-spider" />
      CrawlViz
    </a>
  );
}

function NavTab({ section, active, onClick, hasAlert }) {
  return (
    <button
      onClick={onClick}
      aria-current={active ? "page" : undefined}
      title={section.question}
      style={{
        position: "relative", minHeight: 48, padding: "0 14px", flexShrink: 0,
        background: "transparent", borderTop: "none", borderLeft: "none", borderRight: "none",
        borderBottom: `2px solid ${active ? shell.textBright : "transparent"}`,
        color: active ? shell.textBright : shell.textPrimary,
        fontSize: 14, fontWeight: active ? 600 : 500,
      }}
    >
      {section.label}
      {hasAlert && <span role="img" aria-label="has errors" style={{
        position: "absolute", top: 12, right: 4, width: 6, height: 6, background: theme.colors.accent.red,
      }} />}
    </button>
  );
}

/**
 * Shell -- the persistent frame: one top rule, the content, and an optional
 * docked annotation panel.
 *
 * Props:
 *   activeSection, onNavigate(sectionId)
 *   status, connectionStatus, stopReason, summary (short right-aligned fact line)
 *   errorCount: lights a mark on the Run tab
 *   measuresOpen, onToggleMeasures: the Measurements drawer toggle
 *   banner: optional full-width strip under the top rule (sample-mode notice)
 *   children: the active section's content
 *   inspector: optional docked right-hand annotation panel
 */
export default function Shell({
  activeSection, onNavigate, status, connectionStatus, stopReason, summary,
  errorCount = 0, measuresOpen, onToggleMeasures, onShowErrors, onStop, banner, children, inspector,
}) {
  // Crawl status and the WebSocket only mean something on the live pages; the
  // others talk to the REST API, which this indicator says nothing about.
  const live = activeSection === "graph" || activeSection === "run";
  const sample = connectionStatus === "SAMPLE";
  const connected = connectionStatus === "CONNECTED";
  // Stopping a crawl is not undoable: the first click arms it, the second confirms. It stays
  // armed until pressed, blurred or cancelled with Escape: no timer to race (WCAG 2.2.1).
  const [armed, setArmed] = useState(false);
  const handleStop = () => {
    if (!armed) { setArmed(true); return; }
    setArmed(false);
    onStop();
  };

  return (
    <div style={{
      display: "flex", flexDirection: "column", width: "100%", height: "100%",
      background: shell.background, fontFamily: type.fontMono, overflow: "hidden",
    }}>
      <a className="skip-link" href="#main" onClick={(e) => { e.preventDefault(); document.getElementById("main")?.focus(); }}>
        Skip to content
      </a>
      <header className="shell-header" style={{
        display: "flex", alignItems: "center", gap: 28, height: 48, flexShrink: 0,
        padding: "0 20px", background: shell.surface, borderBottom: `1px solid ${shell.border}`,
      }}>
        <Wordmark />
        <nav aria-label="Sections" className="shell-nav" style={{ display: "flex", alignItems: "stretch", height: 48 }}>
          {SECTIONS.map(section => (
            <NavTab
              key={section.id}
              section={section}
              active={section.id === activeSection}
              onClick={() => onNavigate(section.id)}
              hasAlert={section.id === "run" && errorCount > 0}
            />
          ))}
        </nav>

        <div className="shell-spacer" style={{ flex: 1 }} />

        <div className="shell-status" style={{ display: live ? "flex" : "none", alignItems: "center", gap: 18, minWidth: 0 }}>
          {summary && (
            <span className="num shell-detail" style={{ fontSize: 13, color: shell.textPrimary, whiteSpace: "nowrap" }}>{summary}</span>
          )}
          <span style={{ display: "inline-flex", alignItems: "center", gap: 8, fontSize: 13, color: shell.textBright, fontWeight: 500 }}>
            <StatusMark status={status} />
            {sample ? "Sample playback" : (STATUS_WORD[status] ?? String(status).toLowerCase())}
            {stopReason && <span style={{ color: shell.textMuted, fontWeight: 400 }}>· {String(stopReason).toLowerCase().replace(/_/g, " ")}</span>}
          </span>
          <span className="shell-detail" style={{ fontSize: 12, color: shell.textMuted }}>
            <Hint text={connected || sample
              ? "The live feed of crawl updates (WebSocket) is open."
              : "No live feed of crawl updates. The graph and the run status stop updating. Settings pages still work."}>
              {sample ? "Live feed: simulated" : connected ? "Live feed: connected" : connectionStatus === "CONNECTING" ? "Live feed: connecting…" : "Live feed: disconnected"}
            </Hint>
          </span>
          {errorCount > 0 && onShowErrors && (
            <button onClick={onShowErrors} style={{ background: "none", border: "none", padding: 0, fontSize: 13, fontWeight: 600, color: theme.colors.accent.red, textDecoration: "underline" }}>
              {errorCount} {errorCount === 1 ? "error" : "errors"}
            </button>
          )}
          {status === "RUNNING" && onStop && (
            <button
              onClick={handleStop}
              onBlur={() => setArmed(false)}
              onKeyDown={(e) => { if (e.key === "Escape" && armed) { e.preventDefault(); setArmed(false); } }}
              aria-label={armed ? "Confirm stop. Press again to stop the crawl, Escape to cancel" : undefined}
              style={{
                minHeight: 30, padding: "0 12px", borderRadius: theme.radii.md, fontSize: 13, fontWeight: 600,
                background: armed ? theme.colors.accent.red : "transparent",
                color: armed ? "#fff" : theme.colors.text.secondary,
                border: `1px solid ${armed ? theme.colors.accent.red : theme.colors.text.muted}`,
              }}
            >
              {armed ? "Confirm stop" : "Stop crawl"}
            </button>
          )}
          {onToggleMeasures && (
            <button
              onClick={onToggleMeasures}
              aria-pressed={measuresOpen}
              style={{
                minHeight: 30, padding: "0 12px", borderRadius: theme.radii.md, fontSize: 13, fontWeight: 500,
                background: measuresOpen ? shell.textBright : "transparent",
                color: measuresOpen ? shell.surface : shell.textBright,
                border: `1px solid ${shell.textBright}`,
              }}
            >
              Measurements
            </button>
          )}
        </div>
      </header>

      {banner}

      <main id="main" tabIndex={-1} style={{ outline: "none", flex: 1, minHeight: 0, display: "flex", overflow: "hidden", position: "relative" }}>
        <div style={{ flex: 1, minWidth: 0, overflow: "hidden", position: "relative", background: shell.background }}>
          {children}
        </div>
        {inspector}
      </main>
    </div>
  );
}
