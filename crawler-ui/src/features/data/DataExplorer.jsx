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
const SANS = "'Public Sans', system-ui, sans-serif";

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
  color: "#0f1b2d",
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
        color: "#0f1b2d",
        fontFamily: MONO,
        fontSize: 13,
        lineHeight: 1.7,
      }}>
        {String(arr)}
      </pre>
    );
  }

  if (arr.length === 0) {
    return (
      <span style={{
        color: "#566478",
        fontFamily: MONO,
        fontSize: 13,
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
              background: "rgba(15,27,45,0.04)",
              border: "1px solid #d3d9e0",
              borderRadius: 6,
            }}
          >
            <pre style={{
              margin: 0,
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
              fontFamily: MONO,
              fontSize: 13,
              color: "#0f1b2d",
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
            color: "#0f1b2d",
            fontFamily: SANS,
            fontSize: 13,
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
        color: "#566478",
        fontFamily: MONO,
        fontSize: 13,
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
          color: "#0f1b2d",
          fontFamily: MONO,
          fontSize: 13,
          lineHeight: 1.7,
        }}>
          {JSON.stringify(parsed, null, 2)}
        </pre>
      );
    }

    return (
      <span style={{
        fontFamily: MONO,
        fontSize: 13,
        color: "#0f1b2d",
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
            color: "#0f1b2d",
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
        fontSize: 13, fontWeight: 600, color: "#0f1b2d", letterSpacing: "0",
        textTransform: "none", fontFamily: SANS,
      }}>
        {label}
      </label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        style={{
          background: "#fbfcfd", border: "1px solid #566478", borderRadius: 3,
          color: value ? "#0f1b2d" : "#566478", fontFamily: SANS, fontSize: 14,
          padding: "7px 10px", cursor: disabled ? "not-allowed" : "pointer",
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
        fontSize: 13, fontWeight: 600, color: "#0f1b2d", letterSpacing: "0",
        textTransform: "none", fontFamily: SANS,
      }}>
        Records to show: {value}
      </label>
      <input
        type="range" min={10} max={50} step={10} value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        style={{ accentColor: "#0f1b2d", width: 120 }}
      />
    </div>
  );
}

function StatusBadge({ children, color = "#566478" }) {
  return (
    <span style={{
      fontSize: 11, letterSpacing: "0", color,
      border: `1px solid ${color}`, borderRadius: 3,
      padding: "2px 6px", textTransform: "none", fontFamily: MONO,
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
      background: "rgba(243,245,247,0.94)",
      display: "flex", alignItems: "center", justifyContent: "center",
      zIndex: 1000, backdropFilter: "blur(8px)",
    }}>
      <div ref={ref} style={{
        background: "#fbfcfd",
        border: "1px solid #d3d9e0",
        borderRadius: 10,
        width: "min(780px, 92vw)",
        maxHeight: "84vh",
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
        boxShadow: "0 32px 80px rgba(15,27,45,0.30)",
      }}>

        {/* header */}
        <div style={{
          padding: "16px 22px 14px",
          borderBottom: "1px solid #d3d9e0",
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "space-between",
          gap: 12,
        }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {/* Primary: field name */}
            <span style={{
              fontFamily: SANS, fontWeight: 700, fontSize: 16,
              color: "#0f1b2d", letterSpacing: "0",
            }}>
              {field}
            </span>
            {/* Secondary: crawl + table context */}
            {(shortCrawl || table) && (
              <span style={{
                fontFamily: MONO, fontSize: 11, color: "#566478",
                letterSpacing: "0", textTransform: "none",
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
            color: "#566478", cursor: "pointer",
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
        color: "#566478", fontSize: 13, fontFamily: MONO,
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
    if (lv === 1) return { color: "#566478", fontFamily: MONO, fontSize: 12, maxWidth: 160 };
    if (lv === 3) return { color: "#0f1b2d", fontFamily: SANS, fontSize: 13, maxWidth: 340 };
    return              { color: "#566478", fontFamily: MONO, fontSize: 12, maxWidth: 240 };
  }

  function thCfg(col) {
    const lv  = colLevel(col);
    const base = {
      fontSize: 11, letterSpacing: "0", textTransform: "none",
      fontFamily: MONO, padding: "8px 14px", textAlign: "left",
      borderBottom: "1px solid #d3d9e0", whiteSpace: "nowrap",
    };
    if (lv === 1) return { ...base, color: "#566478" };
    if (lv === 3) return { ...base, color: "#566478" };
    return              { ...base, color: "#566478" };
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
            <tr style={{ background: "#f3f5f7", position: "sticky", top: 0, zIndex: 10 }}>
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
                  background: ri % 2 === 0 ? "transparent" : "rgba(15,27,45,0.04)",
                  borderBottom: "1px solid #d3d9e0",
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
                        background: long && hover ? "rgba(15,27,45,0.04)" : undefined,
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
                          ? "#d3d9e0"
                          : hover && long ? "#0f1b2d" : cfg.color,
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

  const handleTableChange = (newTable) => {
    setTable(newTable);
    setCrawlId("");
    setResult(null);
    setOffset(0);
    if (!newTable) { setCrawls([]); return; }
    fetchValidationCrawls(newTable)
      .then((d) => setCrawls(d.crawls || []))
      .catch((e) => setError(e.message));
  };

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
      background: "#f3f5f7", color: "#0f1b2d",
      fontFamily: MONO, overflow: "hidden",
    }}>

      {/* ── header + query controls ── */}
      <div style={{ padding: "32px 40px 20px", borderBottom: "1px solid #d3d9e0" }}>
        <h1 style={{
          fontFamily: "'Source Serif 4', Georgia, serif", fontWeight: 600, fontSize: 32, lineHeight: 1.15,
          color: "#0f1b2d", marginBottom: 8,
        }}>
          Extracted data
        </h1>
        <p style={{ fontFamily: SANS, fontSize: 15, lineHeight: 1.55, color: "#33435a", maxWidth: "62ch", marginBottom: 20 }}>
          Check what the crawler actually stored. Pick a dataset and, if you want, one run of it.
        </p>
        <div style={{ display: "flex", alignItems: "flex-end", gap: 20, flexWrap: "wrap" }}>
          <Select label="Dataset"   value={table}   onChange={handleTableChange}
                  options={tableOptions} placeholder="Choose a dataset"
                  disabled={tables.length === 0} />
          <Select label="Run" value={crawlId} onChange={setCrawlId}
                  options={crawlOptions} placeholder="All runs"
                  disabled={!table || crawls.length === 0} />
          <LimitControl value={limit} onChange={(v) => { setLimit(v); setOffset(0); }} />
          <button
            onClick={handleFetch}
            disabled={!table || loading}
            style={{
              height: 38, padding: "0 20px", borderRadius: 3, fontFamily: SANS, fontSize: 14, fontWeight: 600,
              background: table && !loading ? "#0f1b2d" : "#d3d9e0", border: "none",
              color: table && !loading ? "#fbfcfd" : "#566478",
              cursor: table && !loading ? "pointer" : "not-allowed",
            }}
          >
            {loading ? "Loading…" : "Show records"}
          </button>
        </div>
        {(result || error) && (
          <p role="status" style={{ fontFamily: SANS, fontSize: 14, marginTop: 16, color: error ? "#7a1f5c" : "#33435a" }}>
            {error
              ? `Could not load records: ${error}. Check that the backend is running, then try again.`
              : `${result.count} records, ${result.columns.length} fields${table ? ` from ${table}` : ""}${offset > 0 ? `, starting at record ${offset + 1}` : ""}.`}
          </p>
        )}
      </div>

      {/* ── empty state ── */}
      {!result && !error && !loading && (
        <div style={{ flex: 1, padding: "40px" }}>
          <p style={{ fontFamily: "'Source Serif 4', Georgia, serif", fontSize: 20, color: "#0f1b2d", marginBottom: 6 }}>
            No dataset chosen.
          </p>
          <p style={{ fontFamily: SANS, fontSize: 14, color: "#566478", maxWidth: "52ch" }}>
            Records appear here once you choose a dataset above.
          </p>
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
          padding: "10px 20px", borderTop: "1px solid #d3d9e0",
          display: "flex", gap: 10, alignItems: "center",
          background: "#f3f5f7",
        }}>
          <button onClick={handlePrev} disabled={offset === 0 || loading}
                  style={pagerBtnStyle(offset > 0 && !loading)}>
            Previous
          </button>
          <span style={{ fontSize: 12, color: "#566478", fontFamily: MONO }}>
            records {offset + 1}–{offset + result.count}
          </span>
          <button onClick={handleNext} disabled={result.count < limit || loading}
                  style={pagerBtnStyle(result.count >= limit && !loading)}>
            Next
          </button>
        </div>
      )}
    </div>
  );
}

function pagerBtnStyle(active) {
  return {
    background: "transparent",
    border: `1px solid ${active ? "#d3d9e0" : "#d3d9e0"}`,
    borderRadius: 4,
    color: active ? "#566478" : "#566478",
    fontFamily: MONO,
    fontSize: 12,
    padding: "4px 14px",
    cursor: active ? "pointer" : "not-allowed",
    letterSpacing: "0",
  };
}
