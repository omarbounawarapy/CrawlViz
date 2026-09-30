import { useState, useEffect } from "react";
import { fetchTemplates, fetchTemplate, runCrawl, stopCrawl, crawlStatus } from "../../api/client";
import { getTheme } from "../../theme";
import { formatDuration } from "../../utils/formatters";
import { Page, SectionTitle, Row } from "../common/Page";
import { buttonPrimary, buttonOutline } from "../common/buttons";

const theme = getTheme();

function BlueprintPreview({ blueprint }) {
  if (!blueprint) return null;
  const scoring = blueprint.scoring || {};
  const stop = blueprint.stop_conditions || {};
  // domains and extraction.fields are keyed objects in blueprints, not arrays
  const count = (x) => Array.isArray(x) ? x.length : Object.keys(x || {}).length;
  const seeds = count(blueprint.domains);
  const fields = count(blueprint.extraction?.fields);
  return (
    <section aria-label="What this will run">
      <SectionTitle>What this will run</SectionTitle>
      <p style={{ fontFamily: theme.typography.fontDisplay, fontSize: 18, lineHeight: 1.4, color: theme.colors.text.primary, marginBottom: 6, maxWidth: "52ch" }}>
        {blueprint.target_topic || "No target topic set."}
      </p>
      {scoring.strategy && <Row label="Scoring strategy">{scoring.strategy}</Row>}
      {stop.priority_strategy && <Row label="Priority strategy">{stop.priority_strategy}</Row>}
      {stop.max_nodes && <Row label="Stops after">{stop.max_nodes.toLocaleString()} pages</Row>}
      {stop.max_depth != null && <Row label="Maximum depth">{stop.max_depth.toLocaleString()} links from a seed</Row>}
      <Row label="Seed domains">{seeds}</Row>
      <Row label="Extraction fields">{fields}</Row>
    </section>
  );
}

function SessionSummary({ state, metrics }) {
  if (!state || state.nodes.size === 0) return null;
  return (
    <section aria-label="This session">
      <SectionTitle>{state.status === "RUNNING" ? "This session, live" : "This session"}</SectionTitle>
      <Row label="Pages discovered">{state.nodes.size}</Row>
      <Row label="Elapsed">{formatDuration((metrics?.elapsed_seconds || 0) * 1000)}</Row>
      <Row label="Errors">{state.errors.length}</Row>
      {state.stop_reason && <Row label="Ended because">{String(state.stop_reason).toLowerCase().replace(/_/g, " ")}</Row>}
    </section>
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
      if (onNavigate) setTimeout(() => onNavigate("graph"), 900);
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

  // The backend's own answer wins; the live stream covers the gap between polls.
  const isRunning = running || state?.status === "RUNNING";
  const blocked = loading || isRunning || !selected;

  return (
    <Page
      title="Run a crawl"
      lead={isRunning
        ? "A crawl is running. Watch it on the graph, or stop it here."
        : "Pick a blueprint, then start. The graph fills in as pages are scored and fetched."}
    >
      <label htmlFor="blueprint" style={{ display: "block", fontSize: 13, fontWeight: 600, marginBottom: 6, color: theme.colors.text.primary }}>
        Blueprint
      </label>
      <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
        <select
          id="blueprint"
          value={selected}
          onChange={(e) => setSelected(e.target.value)}
          style={{
            height: 38, minWidth: 260, padding: "0 10px", fontSize: 14,
            background: theme.colors.background.panel, border: `1px solid ${theme.colors.text.muted}`,
            borderRadius: theme.radii.md, color: theme.colors.text.primary,
          }}
        >
          {templates.length === 0 && <option value="">No blueprints found</option>}
          {templates.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
        <button onClick={handleRun} disabled={blocked} style={buttonPrimary(blocked)}>
          {loading && !isRunning ? "Starting…" : "Start crawl"}
        </button>
        <button onClick={handleStop} disabled={loading || !isRunning} style={buttonOutline(loading || !isRunning)}>
          Stop crawl
        </button>
      </div>

      {msg && (
        <p role="status" style={{ fontSize: 14, marginTop: 12, fontWeight: 500, color: msg.ok ? theme.colors.text.primary : theme.colors.accent.red }}>
          {msg.ok ? msg.text : `${msg.text} Check that the backend is running, then try again.`}
        </p>
      )}

      <BlueprintPreview blueprint={blueprint} />
      <SessionSummary state={state} metrics={metrics} />
    </Page>
  );
}
