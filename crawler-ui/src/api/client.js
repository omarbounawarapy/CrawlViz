const BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export const API_STATUS_EVENT = "crawlviz:api-status";

function announce(reachable) {
  try { window.dispatchEvent(new CustomEvent(API_STATUS_EVENT, { detail: { reachable } })); } catch { /* no window */ }
}

// Error text a person can act on: what was asked, and what to check.
function describe(res, path, detail) {
  if (res.status === 404 && (!detail || detail === "Not Found")) {
    return `The backend has no endpoint ${path}. It may be running an older version; restart it from the repository root.`;
  }
  if (res.status >= 500) {
    return `The backend failed handling ${path} (${res.status}). ${detail && detail !== res.statusText ? detail : "See its log for the traceback."}`;
  }
  return detail ?? res.statusText;
}

async function req(method, path, body) {
  const opts = {
    method,
    headers: { "Content-Type": "application/json" },
  };
  if (body !== undefined) opts.body = JSON.stringify(body);
  let res;
  try {
    res = await fetch(`${BASE}${path}`, opts);
  } catch {
    announce(false);
    throw new Error(`Cannot reach the backend at ${BASE}.`);
  }
  announce(true);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: null }));
    const detail = typeof err.detail === "string" ? err.detail : err.detail ? JSON.stringify(err.detail) : null;
    throw new Error(describe(res, path, detail));
  }
  return res.json();
}

export const fetchTemplates  = ()             => req("GET",    "/templates");
export const fetchTemplate   = (name)         => req("GET",    `/templates/${name}`);
export const createTemplate  = (name, content)=> req("POST",   `/templates?name=${encodeURIComponent(name)}`, { content });
export const updateTemplate  = (name, content)=> req("PUT",    `/templates/${name}`, { content });
export const deleteTemplate  = (name)         => req("DELETE",  `/templates/${name}`);
export const runCrawl        = (templateName) => req("POST",   "/run",  { templateName });
export const stopCrawl       = ()             => req("POST",   "/stop");
export const crawlStatus     = ()             => req("GET",    "/status");

// ── Validation Layer ────────────────────────────────────────────────────────
export const fetchValidationTables = ()                        => req("GET", "/validation/tables");
export const fetchValidationCrawls = (table)                   => req("GET", `/validation/${encodeURIComponent(table)}/crawls`);
export const fetchValidationSample = (table, crawlId, limit = 20, offset = 0) => {
  const params = new URLSearchParams({ limit, offset });
  if (crawlId) params.set("crawl_id", crawlId);
  return req("GET", `/validation/${encodeURIComponent(table)}/sample?${params}`);
};

// ── Configuration (V2) ──────────────────────────────────────────────────────
// Read-only for now; see config/runtime_config.py.
export const fetchConfigSchema = () => req("GET", "/config/schema");
export const fetchConfig       = () => req("GET", "/config");

// ── Benchmark ───────────────────────────────────────────────────────────────
export const fetchBenchmarkOverview = ()                 => req("GET", "/benchmark/overview");
export const fetchBenchmarkRuns     = ()                 => req("GET", "/benchmark/runs");
export const fetchBenchmarkRun      = (name)             => req("GET", `/benchmark/runs/${encodeURIComponent(name)}`);
export const fetchBenchmarkCurves   = (minGrade = 1, budget) => {
  const p = new URLSearchParams({ min_grade: minGrade });
  if (budget) p.set("budget", budget);
  return req("GET", `/benchmark/curves?${p}`);
};
export const fetchBenchmarkGraph    = (name, maxDepth = 1, limit = 300) =>
  req("GET", `/benchmark/graph?name=${encodeURIComponent(name)}&max_depth=${maxDepth}&limit=${limit}`);
export const fetchBenchmarkPage     = (graph, page)      =>
  req("GET", `/benchmark/page?graph=${encodeURIComponent(graph)}&name=${encodeURIComponent(page)}`);
export const fetchAudit             = (annotator = "1")  => req("GET", `/benchmark/audit?annotator=${annotator}`);
export const putAuditLabel          = (id, humanLabel, annotator = "1") =>
  req("PUT", `/benchmark/audit/${encodeURIComponent(id)}?annotator=${annotator}`, { human_label: humanLabel });
export const fetchAuditScore        = (annotator = "1", source = "ui") =>
  req("POST", `/benchmark/audit/score?annotator=${annotator}&source=${source}`);
export const fetchBenchmarkEstimate = (budget)           => req("GET", `/benchmark/estimate?budget=${budget}`);
export const startBenchmarkJob      = (kind, args)       => req("POST", "/benchmark/jobs", { kind, args });
export const benchmarkJob           = ()                 => req("GET",  "/benchmark/jobs/current");
export const stopBenchmarkJob       = ()                 => req("POST", "/benchmark/jobs/stop");
