/**
 * Data: what the crawler actually stored, as a specimen sheet.
 *
 * Each extracted page is an entry: serif title, its URL, a short excerpt, a
 * one-line census of the fields it holds, and every field on demand. When the
 * page also exists in the current graph, its LLM score (the one place
 * vermilion means "promising") and an "Open in graph" link appear beside it.
 */
import { useState, useEffect, useMemo } from "react";
import { fetchValidationTables, fetchValidationCrawls, fetchValidationSample } from "../../api/client";
import { getTheme } from "../../theme";
import { Page } from "../common/Page";
import { Field, Select, Button } from "../common/Form";

const theme = getTheme();
const { text, background, accent, relevance } = theme.colors;

const CORE = new Set(["id", "crawl_id", "url", "created_at", "title"]);
const LIMITS = [10, 25, 50];

const plural = (n, one, many) => `${n.toLocaleString()} ${n === 1 ? one : many}`;
const when = (iso) => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? (iso || "") : d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
};

function tryParse(raw) {
  if (typeof raw !== "string") return null;
  try { return JSON.parse(raw); } catch { return null; }
}

/** Parsed array for a stored cell, or null when it is not a JSON array. */
const asArray = (raw) => { const v = tryParse(raw); return Array.isArray(v) ? v : null; };

/** First paragraph long enough to read as prose (skips bylines and headers). */
function excerptOf(row) {
  const paras = asArray(row.paragraphs);
  if (!paras) return null;
  const best = paras.map(String).find((p) => p.replace(/\s+/g, " ").trim().length > 80);
  const s = (best ?? paras.map(String).find((p) => p.trim()) ?? "").replace(/\s+/g, " ").trim();
  return s || null;
}

/** "12 paragraphs · 5 headings": counts for each stored list field. */
function censusOf(row, fields) {
  return fields
    .map((f) => [f, asArray(row[f])])
    .filter(([, arr]) => arr && arr.length)
    .map(([f, arr]) => {
      const name = f.replace(/_/g, " ");
      const one = name === "categories" ? "category" : name.replace(/s$/, "");
      return `${arr.length.toLocaleString()} ${arr.length === 1 ? one : name}`;
    })
    .join(" · ");
}

// ── one field's value, read-only ─────────────────────────────────────────────

function FieldValue({ raw }) {
  if (raw == null || raw === "") return <span style={{ color: text.muted }}>Empty</span>;
  const parsed = tryParse(String(raw));
  const base = { margin: 0, fontSize: 14, lineHeight: 1.6, color: text.primary, wordBreak: "break-word" };
  if (Array.isArray(parsed)) {
    if (parsed.length === 0) return <span style={{ color: text.muted }}>Empty</span>;
    if (typeof parsed[0] === "object" && parsed[0] !== null) {
      return <pre style={{ ...base, fontFamily: theme.typography.fontMono, fontSize: 13, whiteSpace: "pre-wrap" }}>{JSON.stringify(parsed, null, 2)}</pre>;
    }
    return (
      <ul style={{ margin: 0, paddingLeft: 18, display: "flex", flexDirection: "column", gap: 6 }}>
        {parsed.map((item, i) => <li key={i} style={base}>{String(item)}</li>)}
      </ul>
    );
  }
  if (parsed && typeof parsed === "object") {
    return <pre style={{ ...base, fontFamily: theme.typography.fontMono, fontSize: 13, whiteSpace: "pre-wrap" }}>{JSON.stringify(parsed, null, 2)}</pre>;
  }
  return <p style={base}>{String(raw)}</p>;
}

// ── one extracted page ───────────────────────────────────────────────────────

function Specimen({ row, fields, node, onOpenNode }) {
  const title = row.title || row.name || row.url || row.id;
  const excerpt = excerptOf(row);
  const census = censusOf(row, fields);
  const score = node && (node.llm_score || node.llm_score === 0) ? node.llm_score : null;

  return (
    <article style={{ borderTop: `1px solid ${background.border}`, padding: "18px 0 6px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 16 }}>
        <h2 style={{ fontFamily: theme.typography.fontDisplay, fontWeight: 600, fontSize: 21, lineHeight: 1.25, color: text.primary, textWrap: "balance" }}>
          {title}
        </h2>
        {score !== null && (
          <span className="num" title="The LLM's relevance score for this page in the current graph" style={{ fontWeight: 600, fontSize: 18, color: relevance.mark, flexShrink: 0 }}>
            {score}<span style={{ fontSize: 12, fontWeight: 400, color: text.muted }}> / 100</span>
          </span>
        )}
      </div>

      {row.url && (
        <p style={{ marginTop: 4, fontFamily: theme.typography.fontMono, fontSize: 13, wordBreak: "break-all" }}>
          <a href={row.url} target="_blank" rel="noopener noreferrer" style={{ color: text.secondary }}>{row.url}</a>
        </p>
      )}

      {excerpt && (
        <p style={{
          marginTop: 10, fontSize: 15, lineHeight: 1.55, color: text.primary, maxWidth: "68ch",
          display: "-webkit-box", WebkitLineClamp: 3, WebkitBoxOrient: "vertical", overflow: "hidden",
        }}>
          {excerpt}
        </p>
      )}

      <p style={{ marginTop: 10, fontSize: 13, color: text.muted }}>
        {[census, row.created_at && `Saved ${when(row.created_at)}`].filter(Boolean).join(" · ")}
      </p>

      <div style={{ display: "flex", alignItems: "center", gap: 14, margin: "6px 0 12px" }}>
        {node && <Button variant="outline" onClick={() => onOpenNode(node)}>Open in graph</Button>}
      </div>

      {fields.length > 0 && (
        <details style={{ marginBottom: 14 }}>
          <summary style={{ cursor: "pointer", fontSize: 14, fontWeight: 600, color: text.primary, minHeight: 32, display: "flex", alignItems: "center" }}>
            All {fields.length} fields
          </summary>
          <dl style={{ marginTop: 6 }}>
            {fields.map((f) => (
              <div key={f} style={{ display: "grid", gridTemplateColumns: "150px minmax(0, 1fr)", gap: "4px 20px", padding: "12px 0", borderTop: `1px solid ${theme.colors.rowBorder}` }} className="spec-field">
                <dt style={{ fontFamily: theme.typography.fontDisplay, fontSize: 15, color: text.secondary }}>{f.replace(/_/g, " ")}</dt>
                <dd style={{ margin: 0, maxHeight: 360, overflowY: "auto" }}><FieldValue raw={row[f]} /></dd>
              </div>
            ))}
          </dl>
        </details>
      )}
    </article>
  );
}

// ── page ─────────────────────────────────────────────────────────────────────

export default function DataExplorer({ graphNodes, onOpenNode }) {
  const [tables, setTables] = useState([]);
  const [table, setTable] = useState("");
  const [crawls, setCrawls] = useState([]);
  const [crawlId, setCrawlId] = useState("");
  const [limit, setLimit] = useState(25);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [offset, setOffset] = useState(0);

  useEffect(() => {
    let cancelled = false;
    fetchValidationTables()
      .then((d) => !cancelled && setTables(d.tables || []))
      .catch((e) => !cancelled && setError(e.message));
    return () => { cancelled = true; };
  }, []);

  // page URL -> node, so a stored page can point back at the graph.
  const nodeByUrl = useMemo(() => {
    const m = new Map();
    if (graphNodes) for (const n of graphNodes.values()) if (n.url) m.set(n.url, n);
    return m;
  }, [graphNodes]);

  const load = (t, c, l, o = 0) => {
    if (!t) { setResult(null); return; }
    setLoading(true); setError(null);
    fetchValidationSample(t, c || null, l, o)
      .then((d) => { setResult({ rows: d.rows || [], count: d.count }); setOffset(o); })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  };

  const onTable = (t) => {
    setTable(t); setCrawlId(""); setCrawls([]); setResult(null); setOffset(0); setError(null);
    if (!t) return;
    fetchValidationCrawls(t).then((d) => setCrawls(d.crawls || [])).catch((e) => setError(e.message));
    load(t, "", limit, 0);
  };
  const onCrawl = (c) => { setCrawlId(c); load(table, c, limit, 0); };
  const onLimit = (l) => { setLimit(l); load(table, crawlId, l, 0); };

  const rows = result?.rows ?? [];
  const fields = rows.length ? Object.keys(rows[0]).filter((c) => !CORE.has(c)) : [];
  const first = offset + 1;

  return (
    <Page title="Extracted data" lead="What the crawler actually stored. Choose a dataset, and one run of it if you want." width={820}>
      <div className="form-grid form-grid-3" style={{ marginBottom: 4 }}>
        <Field label="Dataset">
          <Select value={table} onChange={(e) => onTable(e.target.value)} disabled={tables.length === 0}>
            <option value="">{tables.length === 0 && !error ? "No datasets yet" : "Choose a dataset"}</option>
            {tables.map((t) => <option key={t} value={t}>{t}</option>)}
          </Select>
        </Field>
        <Field label="Run">
          <Select value={crawlId} onChange={(e) => onCrawl(e.target.value)} disabled={!table || crawls.length === 0}>
            <option value="">All runs</option>
            {crawls.map((c) => (
              <option key={c.crawl_id} value={c.crawl_id}>
                {[when(c.last_seen), plural(c.count, "record", "records"), c.crawl_id].join(" · ")}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Per page">
          <Select value={limit} onChange={(e) => onLimit(Number(e.target.value))} disabled={!table}>
            {LIMITS.map((l) => <option key={l} value={l}>{l}</option>)}
          </Select>
        </Field>
      </div>
      {error && (
        <div role="alert" style={{ maxWidth: "60ch", margin: "8px 0 20px" }}>
          <p style={{ fontSize: 14, color: accent.red, marginBottom: 12 }}>
            Could not load records: {error}. Check that the backend is running (make dev-backend), then try again.
          </p>
          <Button onClick={() => (table ? load(table, crawlId, limit, offset) : window.location.reload())}>Try again</Button>
        </div>
      )}

      {loading && <p role="status" style={{ fontSize: 14, color: text.muted, margin: "16px 0" }}>Loading records…</p>}

      {!table && !error && (
        <div style={{ marginTop: 24 }}>
          <p style={{ fontFamily: theme.typography.fontDisplay, fontSize: 20, color: text.primary, marginBottom: 6 }}>No dataset chosen.</p>
          <p style={{ fontSize: 14, color: text.muted, maxWidth: "52ch" }}>Records appear here once you choose a dataset above.</p>
        </div>
      )}

      {result && !error && !loading && (
        <section aria-label="Extracted records" style={{ marginTop: 16 }}>
          <p role="status" style={{ fontSize: 14, color: text.secondary, marginBottom: 12 }}>
            {rows.length === 0
              ? "No records matched."
              : `${plural(rows.length, "page", "pages")} from ${table}${offset > 0 ? `, starting at ${first}` : ""}.`}
          </p>
          {rows.map((row) => (
            <Specimen key={row.id ?? row.url} row={row} fields={fields} node={nodeByUrl.get(row.url)} onOpenNode={onOpenNode} />
          ))}
          <div style={{ display: "flex", gap: 12, alignItems: "center", borderTop: `1px solid ${background.border}`, padding: "14px 0 0" }}>
            <Button onClick={() => load(table, crawlId, limit, Math.max(0, offset - limit))} disabled={offset === 0}>Previous</Button>
            <span className="num" style={{ fontSize: 13, color: text.muted }}>{rows.length ? `${first}–${offset + rows.length}` : "0"}</span>
            <Button onClick={() => load(table, crawlId, limit, offset + limit)} disabled={rows.length < limit}>Next</Button>
          </div>
        </section>
      )}
    </Page>
  );
}
