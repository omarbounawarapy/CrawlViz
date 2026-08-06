import { useState, useEffect } from "react";
import { fetchTemplates, fetchTemplate, runCrawl, stopCrawl, crawlStatus } from "../../api/client";
import { getTheme } from "../../theme";
import { createComponentStyles } from "../../theme/components";
import { formatDuration } from "../../utils/formatters";

const theme = getTheme();
const S = createComponentStyles(theme);

function BlueprintPreview({ blueprint }) {
  if (!blueprint) return null;
  const scoring = blueprint.scoring || {};
  const stop = blueprint.stop_conditions || {};
  return (
    <div style={S.sectionCard}>
      <div style={S.sectionCardTitle}>What this will run</div>
      <div style={{ fontSize: theme.typography.size.sm, color: theme.colors.text.primary, marginBottom: 8 }}>
        {blueprint.target_topic || "(no target topic set)"}
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 10 }}>
        {scoring.strategy && <span style={S.pill("purple")}>{scoring.strategy}</span>}
        {stop.priority_strategy && <span style={S.pill("blue")}>{stop.priority_strategy} priority</span>}
        {stop.max_nodes && <span style={S.pill("muted")}>max {stop.max_nodes} nodes</span>}
        {stop.max_depth != null && <span style={S.pill("muted")}>max depth {stop.max_depth}</span>}
      </div>
      <div style={{ fontSize: theme.typography.size.xxs, color: theme.colors.text.muted }}>
        {(blueprint.domains || []).length} seed domain{(blueprint.domains || []).length === 1 ? "" : "s"}
        {" · "}
        {(blueprint.extraction?.fields || []).length} extraction field{(blueprint.extraction?.fields || []).length === 1 ? "" : "s"}
      </div>
    </div>
  );
}

function SessionSummary({ state, metrics }) {
  if (!state || state.nodes.size === 0) {
    return (
      <div style={S.sectionCard}>
        <div style={S.sectionCardTitle}>This session</div>
        <div style={{ fontSize: theme.typography.size.xxs, color: theme.colors.text.muted }}>
          No crawl activity yet in this session.
        </div>
      </div>
    );
  }
  return (
    <div style={S.sectionCard}>
      <div style={S.sectionCardTitle}>This session{state.status === "RUNNING" ? " — live" : ""}</div>
      <div style={S.statTileGrid("110px")}>
        <div>
          <div style={S.statTileLabel}>Nodes</div>
          <div style={S.statTileValue()}>{state.nodes.size}</div>
        </div>
        <div>
          <div style={S.statTileLabel}>Elapsed</div>
          <div style={S.statTileValue()}>{formatDuration((metrics?.elapsed_seconds || 0) * 1000)}</div>
        </div>
        <div>
          <div style={S.statTileLabel}>Errors</div>
          <div style={S.statTileValue(state.errors.length ? theme.colors.accent.red : undefined)}>{state.errors.length}</div>
        </div>
      </div>
      {state.stop_reason && (
        <div style={{ fontSize: theme.typography.size.xxs, color: theme.colors.text.muted, marginTop: 8 }}>
          Stopped: {state.stop_reason}
        </div>
      )}
    </div>
  );
}

export default function RunPage({ onNavigate, state, metrics }) {
  const [templates, setTemplates] = useState([]);
  const [selected, setSelected] = useState("");
  const [blueprint, setBlueprint] = useState(null);
  const [running, setRunning] = useState(false);
  const [msg, setMsg] = useState(null); // { ok, text }
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const poll = async () => {
      try {
        const s = await crawlStatus();
        setRunning(s.running);
      } catch (err) {
        console.warn("Status poll failed:", err);
      }
    };
    poll();
    const id = setInterval(poll, 3000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    fetchTemplates()
      .then((d) => {
        setTemplates(d.templates);
        if (d.templates.length > 0) setSelected(d.templates[0]);
      })
      .catch((e) => setMsg({ ok: false, text: e.message }));
  }, []);

  useEffect(() => {
    if (!selected) { setBlueprint(null); return; }
    let cancelled = false;
    fetchTemplate(selected)
      .then(d => !cancelled && setBlueprint(d.content ?? d))
      .catch(() => !cancelled && setBlueprint(null));
    return () => { cancelled = true; };
  }, [selected]);

  const handleRun = async () => {
    if (!selected || loading) return;
    setLoading(true);
    setMsg(null);
    try {
      await runCrawl(selected);
      setRunning(true);
      setMsg({ ok: true, text: `Started "${selected}".` });
      if (onNavigate) setTimeout(() => onNavigate("overview"), 900);
    } catch (e) {
      setMsg({ ok: false, text: e.message });
    } finally {
      setLoading(false);
    }
  };

  const handleStop = async () => {
    setLoading(true);
    try {
      const res = await stopCrawl();
      setRunning(false);
      setMsg({ ok: true, text: res.stopped ? "Crawl stopped." : "No active crawl." });
    } catch (e) {
      setMsg({ ok: false, text: e.message });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={S.panel}>
      <div style={S.panelHeader}>
        <div>
          <div style={S.panelHeaderTitle}>Run</div>
          <div style={S.panelHeaderSubtitle}>What am I about to run, and what did the last run do?</div>
        </div>
      </div>

      <div style={{ ...S.panelScroll, display: "flex", justifyContent: "center" }}>
        <div style={{ width: "100%", maxWidth: 460, display: "flex", flexDirection: "column", gap: 16 }}>

          <div style={S.sectionCard}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 14 }}>
              <span style={{
                width: 6, height: 6, borderRadius: "50%",
                background: running ? theme.colors.accent.green : theme.colors.text.muted,
                boxShadow: running ? `0 0 6px ${theme.colors.accent.green}` : "none",
                animation: running ? "pulse 2s ease-in-out infinite" : "none",
              }} />
              <span style={{ fontSize: theme.typography.size.xs, letterSpacing: theme.typography.letterSpacing.wide, color: running ? theme.colors.accent.green : theme.colors.text.muted }}>
                {running ? "RUNNING" : "IDLE"}
              </span>
            </div>

            <div style={S.sectionCardTitle}>Blueprint</div>
            <select
              value={selected}
              onChange={(e) => setSelected(e.target.value)}
              style={{
                background: theme.colors.background.primary, border: `1px solid ${theme.colors.background.border}`,
                borderRadius: theme.radii.md, color: theme.colors.text.primary, fontFamily: theme.typography.fontMono,
                fontSize: theme.typography.size.sm, padding: "8px 10px", outline: "none", width: "100%", cursor: "pointer",
                marginBottom: 14,
              }}
            >
              {templates.length === 0 && <option value="">— no templates —</option>}
              {templates.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>

            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              <button
                onClick={handleRun}
                disabled={loading || running || !selected}
                style={{
                  background: (loading || running || !selected) ? theme.colors.background.border : theme.colors.accent.blue,
                  color: (loading || running || !selected) ? theme.colors.text.muted : "#fff",
                  border: "none", borderRadius: theme.radii.md, padding: "10px 0", fontSize: theme.typography.size.xs,
                  letterSpacing: theme.typography.letterSpacing.normal, textTransform: "uppercase",
                  cursor: (loading || running || !selected) ? "not-allowed" : "pointer",
                  fontFamily: theme.typography.fontMono, fontWeight: 600, width: "100%",
                }}
              >
                {loading ? "Starting…" : "Run Crawl"}
              </button>
              <button
                onClick={handleStop}
                disabled={loading || !running}
                style={{
                  background: (loading || !running) ? theme.colors.background.border : theme.colors.accent.red,
                  color: (loading || !running) ? theme.colors.text.muted : "#fff",
                  border: "none", borderRadius: theme.radii.md, padding: "10px 0", fontSize: theme.typography.size.xs,
                  letterSpacing: theme.typography.letterSpacing.normal, textTransform: "uppercase",
                  cursor: (loading || !running) ? "not-allowed" : "pointer",
                  fontFamily: theme.typography.fontMono, fontWeight: 600, width: "100%",
                }}
              >
                Stop
              </button>
            </div>

            {msg && (
              <div style={{ fontSize: theme.typography.size.xxs, color: msg.ok ? theme.colors.accent.green : theme.colors.accent.red, marginTop: 10 }}>
                {msg.text}
              </div>
            )}
          </div>

          <BlueprintPreview blueprint={blueprint} />
          <SessionSummary state={state} metrics={metrics} />
        </div>
      </div>
    </div>
  );
}
