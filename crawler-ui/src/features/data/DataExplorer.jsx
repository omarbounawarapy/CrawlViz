// V2 note: moved into features/data/ (renamed from ValidationView to
// DataExplorer for the activity-bar label) and wired into the new app
// shell; internals unchanged this pass -- see docs/V2_ARCHITECTURE.md
// roadmap #14.
import { useState, useEffect, useCallback, useRef } from "react";
import {
  fetchValidationTables,
  fetchValidationCrawls,
  fetchValidationSample,
} from "../../api/client";

// ── design tokens ─────────────────────────────────────────────────────────────
const TRUNCATE_LEN = 140;
const MONO = "'JetBrains Mono', monospace";
const SANS = "'Syne', sans-serif";

// Three-level column classification
// Level 1 — metadata (muted)
// Level 2 — structured data (mid)
// Level 3 — content / extracted text (readable, prominent)
const META_COLS    = new Set(["id", "crawl_id", "created_at"]);
const CONTENT_COLS = new Set(["paragraphs", "headings", "lists", "categories", "infobox_items"]);

function colLevel(col) {
  if (META_COLS.has(col))    return 1;
  if (CONTENT_COLS.has(col)) return 3;
  return 2;
}

// ── parsing helpers ───────────────────────────────────────────────────────────

function tryParseJSON(raw) {
  try { return JSON.parse(raw); } catch { return null; }
}



// ── cell preview helpers ──────────────────────────────────────────────────────

function formatPreview(raw) {
  if (raw == null) return "—";
  const str = String(raw).replace(/\s+/g, " ").trim();
  return str.length > TRUNCATE_LEN ? str.slice(0, TRUNCATE_LEN) + "…" : str;
}

function isLong(raw) {
  if (raw == null) return false;
  return String(raw).replace(/\s+/g, " ").trim().length > TRUNCATE_LEN;
}

// ── expanded content renderers ────────────────────────────────────────────────

const P_STYLE = {
  margin: 0,
  color: "#c0cce0",
  fontFamily: SANS,
  fontSize: 13,
  lineHeight: 1.85,
  wordBreak: "break-word",
  textAlign: "left",
};

function renderParsedArray(arr) {
  if (!Array.isArray(arr)) {
    return (
      <pre style={{
        margin: 0,
        whiteSpace: "pre-wrap",
        wordBreak: "break-word",
        color: "#c0cce0",
        fontFamily: MONO,
        fontSize: 11,
        lineHeight: 1.7,
      }}>
        {String(arr)}
      </pre>
    );
  }

  if (arr.length === 0) {
    return (
      <span style={{
        color: "#3a4060",
        fontFamily: MONO,
        fontSize: 11,
      }}>
        empty
      </span>
    );
  }

  const first = arr[0];

  // OBJECT ARRAY → structured cards
  if (typeof first === "object" && first !== null) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        {arr.map((item, i) => (
          <div
            key={i}
            style={{
              padding: "10px 12px",
              background: "rgba(16,22,48,0.25)",
              border: "1px solid #111828",
              borderRadius: 6,
            }}
          >
            <pre style={{
              margin: 0,
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
              fontFamily: MONO,
              fontSize: 11,
              color: "#c0cce0",
              lineHeight: 1.6,
            }}>
              {JSON.stringify(item, null, 2)}
            </pre>
          </div>
        ))}
      </div>
    );
  }

  // STRING / SCALAR ARRAY → strict list rendering
  return (
    <ul style={{
      margin: 0,
      paddingLeft: 14,
      display: "flex",
      flexDirection: "column",
      gap: 6,
    }}>
      {arr.map((item, i) => (
        <li
          key={i}
          style={{
            color: "#c0cce0",
            fontFamily: SANS,
            fontSize: 12,
            lineHeight: 1.6,
            listStyle: "disc",
          }}
        >
          {String(item)}
        </li>
      ))}
    </ul>
  );
}
function formatExpandedValue(raw) {
  if (raw == null) {
    return (
      <span style={{
        color: "#3a4060",
        fontFamily: MONO,
        fontSize: 11,
      }}>
        null
      </span>
    );
  }

  const str = String(raw);

  // STRICT JSON ONLY (source of truth)
  const parsed = tryParseJSON(str);

  if (parsed !== null) {
    if (Array.isArray(parsed)) {
      return renderParsedArray(parsed);
    }

    if (typeof parsed === "object") {
      return (
        <pre style={{
          margin: 0,
          whiteSpace: "pre-wrap",
          wordBreak: "break-word",
          color: "#c0cce0",
          fontFamily: MONO,
          fontSize: 11,
          lineHeight: 1.7,
        }}>
          {JSON.stringify(parsed, null, 2)}
        </pre>
      );
    }

    return (
      <span style={{
        fontFamily: MONO,
        fontSize: 12,
        color: "#c0cce0",
      }}>
        {String(parsed)}
      </span>
    );
  }

  // PLAIN TEXT ONLY (no inference)
  const lines = str.split("\n").filter(Boolean);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      {lines.map((line, i) => (
        <p
          key={i}
          style={{
            margin: 0,
            color: "#c0cce0",
            fontFamily: SANS,
            fontSize: 13,
            lineHeight: 1.75,
            wordBreak: "break-word",
          }}
        >
          {line}
        </p>
      ))}
    </div>
  );
}

// ── sub-components ────────────────────────────────────────────────────────────

function Select({ label, value, onChange, options, placeholder, disabled }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <label style={{
        fontSize: 9, color: "#3a4060", letterSpacing: "0.1em",
        textTransform: "uppercase", fontFamily: MONO,
      }}>
        {label}
      </label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        style={{
          background: "#080c18", border: "1px solid #1a2040", borderRadius: 4,
          color: value ? "#c0cce0" : "#3a4060", fontFamily: MONO, fontSize: 11,
          padding: "6px 10px", cursor: disabled ? "not-allowed" : "pointer",
          outline: "none", minWidth: 220, opacity: disabled ? 0.5 : 1,
        }}
      >
        <option value="">{placeholder}</option>
        {options.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
    </div>
  );
}

function LimitControl({ value, onChange }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <label style={{
        fontSize: 9, color: "#3a4060", letterSpacing: "0.1em",
        textTransform: "uppercase", fontFamily: MONO,
      }}>
        Sample size: {value}
      </label>
      <input
        type="range" min={10} max={50} step={10} value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        style={{ accentColor: "#5a7aff", width: 120 }}
      />
    </div>
  );
}

function StatusBadge({ children, color = "#3a4060" }) {
  return (
    <span style={{
      fontSize: 9, letterSpacing: "0.1em", color,
      border: `1px solid ${color}`, borderRadius: 3,
      padding: "2px 6px", textTransform: "uppercase", fontFamily: MONO,
    }}>
      {children}
    </span>
  );
}

// ── Detail Modal ──────────────────────────────────────────────────────────────

function DetailModal({ value, field, crawlId, table, onClose }) {
  const ref = useRef(null);

  useEffect(() => {
    const handler = (e) => {
      if (ref.current && !ref.current.contains(e.target)) onClose();
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [onClose]);

  useEffect(() => {
    const handler = (e) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [onClose]);

  const shortCrawl = crawlId
    ? `${crawlId.slice(0, 14)}${crawlId.length > 14 ? "…" : ""}`
    : null;

  return (
    <div style={{
      position: "fixed", inset: 0,
      background: "rgba(4, 8, 18, 0.90)",
      display: "flex", alignItems: "center", justifyContent: "center",
      zIndex: 1000, backdropFilter: "blur(8px)",
    }}>
      <div ref={ref} style={{
        background: "#07101f",
        border: "1px solid #182038",
        borderRadius: 10,
        width: "min(780px, 92vw)",
        maxHeight: "84vh",
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
        boxShadow: "0 32px 80px rgba(0,0,0,0.65)",
      }}>

        {/* header */}
        <div style={{
          padding: "16px 22px 14px",
          borderBottom: "1px solid #101828",
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "space-between",
          gap: 12,
        }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {/* Primary: field name */}
            <span style={{
              fontFamily: SANS, fontWeight: 700, fontSize: 16,
              color: "#e0eaff", letterSpacing: "0.01em",
            }}>
              {field}
            </span>
            {/* Secondary: crawl + table context */}
            {(shortCrawl || table) && (
              <span style={{
                fontFamily: MONO, fontSize: 9, color: "#253050",
                letterSpacing: "0.09em", textTransform: "uppercase",
              }}>
                {[
                  shortCrawl && `crawl: ${shortCrawl}`,
                  table      && `table: ${table}`,
                ].filter(Boolean).join("  ·  ")}
              </span>
            )}
          </div>
          <button onClick={onClose} style={{
            background: "transparent", border: "none",
            color: "#2a3860", cursor: "pointer",
            fontSize: 20, lineHeight: 1, padding: "0 4px", marginTop: 2,
          }}>×</button>
        </div>

        {/* body */}
        <div style={{ flex: 1, overflow: "auto", padding: "22px 26px" }}>
          {formatExpandedValue(value)}
        </div>
      </div>
    </div>
  );
}

// ── DataTable ─────────────────────────────────────────────────────────────────

function DataTable({ rows, columns, table, crawlId }) {
  const [modal,     setModal]   = useState(null);
  const [hoveredCell, setHovered] = useState(null); // "ri-col"

  if (!rows.length) {
    return (
      <div style={{
        padding: 40, textAlign: "center",
        color: "#1e2840", fontSize: 11, fontFamily: MONO,
      }}>
        No records matched the current query.
      </div>
    );
  }

  const coreColumns    = ["id", "crawl_id", "url", "created_at"];
  const dynamicColumns = columns.filter((c) => !coreColumns.includes(c));
  const orderedColumns = [...coreColumns.filter((c) => columns.includes(c)), ...dynamicColumns];

  // Per-column typography config by level
  function cellCfg(col) {
    const lv = colLevel(col);
    if (lv === 1) return { color: "#263050", fontFamily: MONO, fontSize: 10, maxWidth: 160 };
    if (lv === 3) return { color: "#9ab0d0", fontFamily: SANS, fontSize: 11, maxWidth: 340 };
    return              { color: "#5a7090", fontFamily: MONO, fontSize: 10, maxWidth: 240 };
  }

  function thCfg(col) {
    const lv  = colLevel(col);
    const base = {
      fontSize: 9, letterSpacing: "0.1em", textTransform: "uppercase",
      fontFamily: MONO, padding: "8px 14px", textAlign: "left",
      borderBottom: "1px solid #0e1828", whiteSpace: "nowrap",
    };
    if (lv === 1) return { ...base, color: "#1c2440" };
    if (lv === 3) return { ...base, color: "#3d5aad" };
    return              { ...base, color: "#253050" };
  }

  return (
    <>
      {modal && (
        <DetailModal
         style={{ 
         flex: 1,
         overflow: "auto",
         padding: "22px 26px",
         textAlign: "left"   }}
          field={modal.field}
          value={modal.value}
          crawlId={crawlId}
          table={table}
          onClose={() => setModal(null)}
        />
      )}
      <div style={{ overflow: "auto", flex: 1 }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ background: "#060a14", position: "sticky", top: 0, zIndex: 10 }}>
              {orderedColumns.map((col) => (
                <th key={col} style={thCfg(col)}>{col}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, ri) => (
              <tr
                key={ri}
                style={{
                  background: ri % 2 === 0 ? "transparent" : "rgba(16,22,48,0.3)",
                  borderBottom: "1px solid #080c1a",
                }}
              >
                {orderedColumns.map((col) => {
                  const raw   = row[col];
                  const long  = isLong(raw);
                  const cfg   = cellCfg(col);
                  const hKey  = `${ri}-${col}`;
                  const hover = hoveredCell === hKey;

                  return (
                    <td
                      key={col}
                      style={{
                        padding: "9px 14px",
                        verticalAlign: "top",
                        maxWidth: cfg.maxWidth,
                        cursor: long ? "pointer" : "default",
                        transition: "background 0.1s",
                        background: long && hover ? "rgba(90,122,255,0.05)" : undefined,
                      }}
                      onClick={long ? () => setModal({ field: col, value: raw }) : undefined}
                      onMouseEnter={long ? () => setHovered(hKey) : undefined}
                      onMouseLeave={long ? () => setHovered(null)  : undefined}
                    >
                      <span style={{
                        display: "-webkit-box",
                        WebkitLineClamp: 2,
                        WebkitBoxOrient: "vertical",
                        overflow: "hidden",
                        whiteSpace: "normal",
                        maxWidth: cfg.maxWidth,
                        color: raw == null
                          ? "#131b30"
                          : hover && long ? "#b8cce8" : cfg.color,
                        fontFamily: cfg.fontFamily,
                        fontSize: cfg.fontSize,
                        lineHeight: 1.55,
                        transition: "color 0.1s",
                      }}
                        title={long ? "Click to inspect" : undefined}
                      >
                        {formatPreview(raw)}
                      </span>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function ValidationView() {
  const [tables,  setTables]  = useState([]);
  const [table,   setTable]   = useState("");
  const [crawls,  setCrawls]  = useState([]);
  const [crawlId, setCrawlId] = useState("");
  const [limit,   setLimit]   = useState(20);
  const [result,  setResult]  = useState(null);
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState(null);
  const [offset,  setOffset]  = useState(0);

  useEffect(() => {
    fetchValidationTables()
      .then((d) => setTables(d.tables || []))
      .catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    if (!table) { setCrawls([]); setCrawlId(""); setResult(null); return; }
    setCrawlId(""); setResult(null); setOffset(0);
    fetchValidationCrawls(table)
      .then((d) => setCrawls(d.crawls || []))
      .catch((e) => setError(e.message));
  }, [table]);

  const fetchSample = useCallback((currentOffset = 0) => {
    if (!table) return;
    setLoading(true);
    setError(null);
    fetchValidationSample(table, crawlId || null, limit, currentOffset)
      .then((d) => {
        const rows    = d.rows || [];
        const columns = rows.length ? Object.keys(rows[0]) : [];
        setResult({ rows, columns, count: d.count });
        setOffset(currentOffset);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [table, crawlId, limit]);

  const handleFetch = () => fetchSample(0);
  const handleNext  = () => fetchSample(offset + limit);
  const handlePrev  = () => fetchSample(Math.max(0, offset - limit));

  const tableOptions = tables.map((t) => ({ value: t, label: t }));
  const crawlOptions = crawls.map((c) => ({
    value: c.crawl_id,
    label: `${c.crawl_id}  ·  ${c.count} records  ·  ${c.last_seen?.slice(0, 19) ?? ""}`,
  }));

  return (
    <div style={{
      height: "100%", display: "flex", flexDirection: "column",
      background: "#060a14", color: "#c0cce0",
      fontFamily: MONO, overflow: "hidden",
    }}>

      {/* ── toolbar ── */}
      <div style={{
        padding: "14px 20px", borderBottom: "1px solid #0e1828",
        display: "flex", alignItems: "flex-end", gap: 20,
        flexWrap: "wrap", background: "#060a14",
      }}>
        <div style={{ marginRight: 8 }}>
          <div style={{
            fontSize: 9, color: "#1e2840", letterSpacing: "0.12em",
            textTransform: "uppercase", marginBottom: 3, fontFamily: MONO,
          }}>
            Validation Layer
          </div>
          <div style={{
            fontSize: 13, fontFamily: SANS, fontWeight: 700,
            color: "#dce8ff", letterSpacing: "0.02em",
          }}>
            Extracted Data<span style={{ color: "#5a7aff" }}> Inspector</span>
          </div>
        </div>

        <div style={{ width: 1, background: "#0e1828", alignSelf: "stretch" }} />

        <Select label="Dataset"   value={table}   onChange={setTable}
                options={tableOptions} placeholder="Select a dataset…"
                disabled={tables.length === 0} />

        <Select label="Execution" value={crawlId} onChange={setCrawlId}
                options={crawlOptions} placeholder="All executions"
                disabled={!table || crawls.length === 0} />

        <LimitControl value={limit} onChange={(v) => { setLimit(v); setOffset(0); }} />

        <button
          onClick={handleFetch}
          disabled={!table || loading}
          style={{
            background: table && !loading ? "#5a7aff" : "#0e1828",
            border: "none", borderRadius: 4,
            color: table && !loading ? "#fff" : "#2a3060",
            fontFamily: MONO, fontSize: 10, letterSpacing: "0.08em",
            padding: "7px 20px",
            cursor: table && !loading ? "pointer" : "not-allowed",
            textTransform: "uppercase", alignSelf: "flex-end",
            transition: "background 0.15s",
          }}
        >
          {loading ? "Loading…" : "Inspect"}
        </button>
      </div>

      {/* ── status bar ── */}
      {(result || error) && (
        <div style={{
          padding: "6px 20px", borderBottom: "1px solid #080c18",
          display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap",
        }}>
          {error && <StatusBadge color="#c04040">Error — {error}</StatusBadge>}
          {result && !error && (
            <>
              <StatusBadge color="#30b880">{result.count} records</StatusBadge>
              <StatusBadge color="#4060c0">{result.columns.length} fields</StatusBadge>
              {table   && <StatusBadge color="#1e2a50">{table}</StatusBadge>}
              {crawlId && (
                <StatusBadge color="#1e2a50">
                  {crawlId.slice(0, 14)}{crawlId.length > 14 ? "…" : ""}
                </StatusBadge>
              )}
              {offset > 0 && <StatusBadge color="#806020">offset {offset}</StatusBadge>}
            </>
          )}
        </div>
      )}

      {/* ── empty state ── */}
      {!result && !error && !loading && (
        <div style={{
          flex: 1, display: "flex", flexDirection: "column",
          alignItems: "center", justifyContent: "center",
          gap: 16, color: "#1a2240",
        }}>
          <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
            <rect x="6" y="10" width="36" height="30" rx="3"
                  stroke="#141e38" strokeWidth="1.5" />
            <path d="M6 20h36" stroke="#141e38" strokeWidth="1" />
            <path d="M18 20v20M30 20v20"
                  stroke="#141e38" strokeWidth="0.8" strokeDasharray="2 3" />
            <circle cx="24" cy="10" r="3.5" fill="#141e38" />
          </svg>
          <div style={{
            textAlign: "center", display: "flex",
            flexDirection: "column", gap: 5,
          }}>
            <span style={{
              fontSize: 13, color: "#253060", fontFamily: SANS,
              fontWeight: 600, letterSpacing: "0.02em",
            }}>
              No dataset loaded
            </span>
            <span style={{
              fontSize: 10, color: "#141e38", fontFamily: MONO,
              letterSpacing: "0.07em",
            }}>
              Select a dataset to inspect extracted records
            </span>
          </div>
        </div>
      )}

      {/* ── data table ── */}
      {result && !error && (
        <DataTable
          rows={result.rows}
          columns={result.columns}
          table={table}
          crawlId={crawlId}
        />
      )}

      {/* ── pagination ── */}
      {result && !error && (
        <div style={{
          padding: "10px 20px", borderTop: "1px solid #0e1828",
          display: "flex", gap: 10, alignItems: "center",
          background: "#060a14",
        }}>
          <button onClick={handlePrev} disabled={offset === 0 || loading}
                  style={pagerBtnStyle(offset > 0 && !loading)}>
            ← Previous
          </button>
          <span style={{ fontSize: 10, color: "#1e2840", fontFamily: MONO }}>
            records {offset + 1}–{offset + result.count}
          </span>
          <button onClick={handleNext} disabled={result.count < limit || loading}
                  style={pagerBtnStyle(result.count >= limit && !loading)}>
            Next →
          </button>
        </div>
      )}
    </div>
  );
}

function pagerBtnStyle(active) {
  return {
    background: "transparent",
    border: `1px solid ${active ? "#1a2040" : "#0c1020"}`,
    borderRadius: 4,
    color: active ? "#6070a0" : "#181e30",
    fontFamily: MONO,
    fontSize: 10,
    padding: "4px 14px",
    cursor: active ? "pointer" : "not-allowed",
    letterSpacing: "0.06em",
  };
}
