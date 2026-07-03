import { useState, useEffect } from "react";
import { fetchTemplates, runCrawl, stopCrawl, crawlStatus } from "../api/client";

const S = {
  root: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    height: "100%",
    background: "#060a14",
    color: "#c0cce0",
    fontFamily: "'JetBrains Mono', monospace",
    gap: 24,
  },
  card: {
    background: "#080c18",
    border: "1px solid #111828",
    borderRadius: 8,
    padding: "32px 40px",
    width: 380,
    display: "flex",
    flexDirection: "column",
    gap: 20,
  },
  title: {
    fontSize: 10,
    letterSpacing: "0.14em",
    color: "#3a4060",
    textTransform: "uppercase",
    marginBottom: 4,
  },
  select: {
    background: "#0a0e1a",
    border: "1px solid #1a2040",
    borderRadius: 4,
    color: "#e0eaff",
    fontFamily: "'JetBrains Mono', monospace",
    fontSize: 12,
    padding: "8px 10px",
    outline: "none",
    width: "100%",
    cursor: "pointer",
  },
  btn: (variant, disabled) => ({
    background: disabled
      ? "#0d1422"
      : variant === "run"
      ? "#5a7aff"
      : "#ff4a6a",
    color: disabled ? "#3a4060" : "#fff",
    border: "none",
    borderRadius: 4,
    padding: "10px 0",
    fontSize: 10,
    letterSpacing: "0.1em",
    textTransform: "uppercase",
    cursor: disabled ? "not-allowed" : "pointer",
    fontFamily: "'JetBrains Mono', monospace",
    fontWeight: 600,
    width: "100%",
    transition: "opacity 0.15s",
  }),
  statusRow: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    fontSize: 10,
  },
  dot: (running) => ({
    width: 6,
    height: 6,
    borderRadius: "50%",
    background: running ? "#40d9a0" : "#3a4060",
    boxShadow: running ? "0 0 6px #40d9a0" : "none",
    animation: running ? "pulse 2s ease-in-out infinite" : "none",
  }),
  msg: (ok) => ({
    fontSize: 10,
    color: ok ? "#40d9a0" : "#ff4a6a",
    minHeight: 14,
  }),
};

export default function RunScreen({ onNavigate }) {
  const [templates, setTemplates] = useState([]);
  const [selected, setSelected] = useState("");
  const [running, setRunning] = useState(false);
  const [msg, setMsg] = useState(null); // { ok, text }
  const [loading, setLoading] = useState(false);

  // Poll status
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

  const handleRun = async () => {
    if (!selected || loading) return;
    setLoading(true);
    setMsg(null);
    try {
      await runCrawl(selected);
      setRunning(true);
      setMsg({ ok: true, text: `Started "${selected}" — redirecting…` });
      setTimeout(() => onNavigate("/"), 1200);
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
    <div style={S.root}>
      <div style={S.card}>
        <div>
          <div style={S.title}>Crawl Control</div>
          <div style={S.statusRow}>
            <div style={S.dot(running)} />
            <span style={{ color: running ? "#40d9a0" : "#3a4060" }}>
              {running ? "RUNNING" : "IDLE"}
            </span>
          </div>
        </div>

        <div>
          <div style={{ ...S.title, marginBottom: 8 }}>Template</div>
          <select
            style={S.select}
            value={selected}
            onChange={(e) => setSelected(e.target.value)}
          >
            {templates.length === 0 && (
              <option value="">— no templates —</option>
            )}
            {templates.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <button
            style={S.btn("run", loading || running || !selected)}
            onClick={handleRun}
            disabled={loading || running || !selected}
          >
            {loading ? "Starting…" : "Run Crawl"}
          </button>
          <button
            style={S.btn("stop", loading || !running)}
            onClick={handleStop}
            disabled={loading || !running}
          >
            Stop
          </button>
        </div>

        {msg && <div style={S.msg(msg.ok)}>{msg.text}</div>}
      </div>
    </div>
  );
}
