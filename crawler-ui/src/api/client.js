const BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export const API_STATUS_EVENT = "crawlviz:api-status";

function announce(reachable) {
  try {
    window.dispatchEvent(new CustomEvent(API_STATUS_EVENT, { detail: { reachable } }));
  } catch {
    /* no window */
  }
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

const SESSION_PATH = "/session";
const STATUS_UNAUTHORIZED = 401;

// Every route but /session wants `Authorization: Bearer <token>`. A build that knows the token
// (VITE_API_TOKEN, matching CRAWLVIZ_API_TOKEN) uses it; otherwise the backend hands out the one
// it generated at start-up, fetched once and kept as a promise so concurrent first calls share it.
const configuredToken = () => import.meta.env.VITE_API_TOKEN || null;
let sessionTokenRequest = null;

async function send(method, path, { headers, body } = {}) {
  const opts = { method, headers };
  if (body !== undefined) opts.body = JSON.stringify(body);
  let res;
  try {
    res = await fetch(`${BASE}${path}`, opts);
  } catch {
    announce(false);
    throw new Error(`Cannot reach the backend at ${BASE}.`);
  }
  announce(true);
  return res;
}

// The error for a reply that is not ok: the backend's own message when it sent one.
async function failureOf(res, path) {
  const err = await res.json().catch(() => ({ detail: null }));
  const detail =
    typeof err.detail === "string"
      ? err.detail
      : Array.isArray(err.detail?.errors)
        ? err.detail.errors.map((e) => `${e.path}: ${e.message}`).join("; ")
        : err.detail
          ? JSON.stringify(err.detail)
          : null;
  return Object.assign(new Error(describe(res, path, detail)), { errors: err.detail?.errors });
}

function fetchSessionToken() {
  if (!sessionTokenRequest) {
    sessionTokenRequest = (async () => {
      const res = await send("GET", SESSION_PATH);
      if (!res.ok) throw await failureOf(res, SESSION_PATH);
      return (await res.json()).token;
    })().catch((e) => {
      sessionTokenRequest = null; // a failed lookup must not be cached
      throw e;
    });
  }
  return sessionTokenRequest;
}

async function authorizedSend(method, path, body) {
  const token = configuredToken() ?? (await fetchSessionToken());
  // Content-Type stays on every call, DELETE and bodyless POST included: the backend answers
  // 415 to a request without it.
  const headers = { "Content-Type": "application/json", Authorization: `Bearer ${token}` };
  return send(method, path, { headers, body });
}

async function req(method, path, body) {
  let res = await authorizedSend(method, path, body);
  // The backend restarted and made a new token: drop ours, ask again, retry once.
  if (res.status === STATUS_UNAUTHORIZED && configuredToken() === null) {
    sessionTokenRequest = null;
    res = await authorizedSend(method, path, body);
  }
  if (!res.ok) throw await failureOf(res, path);
  return res.json();
}

export const fetchTemplates = () => req("GET", "/templates");
export const fetchTemplate = (name) => req("GET", `/templates/${name}`);
export const createTemplate = (name, content) =>
  req("POST", `/templates?name=${encodeURIComponent(name)}`, { content });
export const updateTemplate = (name, content) => req("PUT", `/templates/${name}`, { content });
export const deleteTemplate = (name) => req("DELETE", `/templates/${name}`);
export const runCrawl = (templateName, overrides, seed) =>
  req("POST", "/run", {
    templateName,
    ...(overrides && Object.keys(overrides).length ? { overrides } : {}),
    ...(seed != null ? { seed } : {}),
  });
export const stopCrawl = () => req("POST", "/stop");
export const crawlStatus = () => req("GET", "/status");

// ── Validation Layer ────────────────────────────────────────────────────────
export const fetchValidationTables = () => req("GET", "/validation/tables");
export const fetchValidationCrawls = (table) => req("GET", `/validation/${encodeURIComponent(table)}/crawls`);
export const fetchValidationSample = (table, crawlId, limit = 20, offset = 0) => {
  const params = new URLSearchParams({ limit, offset });
  if (crawlId) params.set("crawl_id", crawlId);
  return req("GET", `/validation/${encodeURIComponent(table)}/sample?${params}`);
};

// ── Configuration (V2) ──────────────────────────────────────────────────────
// Schema-driven; see config/runtime_config.py. Saves apply from the next crawl.
export const fetchConfigSchema = () => req("GET", "/config/schema");
export const fetchConfig = () => req("GET", "/config");
export const fetchConfigDefaults = () => req("GET", "/config/defaults");
export const saveConfig = (values) => req("PUT", "/config", { values });
export const replaceConfig = (values) => req("PUT", "/config/replace", { values });
export const validateConfig = (values) => req("POST", "/config/validate", { values });
export const exportConfig = () => req("GET", "/config/export");
export const fetchPresets = () => req("GET", "/config/presets");
export const savePreset = (name, values) =>
  req("PUT", `/config/presets/${encodeURIComponent(name)}`, values ? { values } : undefined);
export const deletePreset = (name) => req("DELETE", `/config/presets/${encodeURIComponent(name)}`);
export const applyPreset = (name) => req("POST", `/config/presets/${encodeURIComponent(name)}/apply`);
export const patchLiveConfig = (values) => req("PATCH", "/config/live", { values });
export const resetConfig = (section) =>
  req("POST", `/config/reset${section ? `?section=${encodeURIComponent(section)}` : ""}`);
export const fetchProviders = () => req("GET", "/config/providers");
export const fetchKeys = () => req("GET", "/keys");
export const addKey = (provider, key) => req("POST", "/keys", { provider, key });
export const removeKey = (provider, id) =>
  req("DELETE", `/keys/${encodeURIComponent(provider)}/${encodeURIComponent(id)}`);

// ── Benchmark ───────────────────────────────────────────────────────────────
export const fetchBenchmarkOverview = () => req("GET", "/benchmark/overview");
export const fetchBenchmarkRuns = () => req("GET", "/benchmark/runs");
export const fetchBenchmarkRun = (name) => req("GET", `/benchmark/runs/${encodeURIComponent(name)}`);
export const fetchBenchmarkCurves = (minGrade = 1, budget) => {
  const p = new URLSearchParams({ min_grade: minGrade });
  if (budget) p.set("budget", budget);
  return req("GET", `/benchmark/curves?${p}`);
};
export const fetchBenchmarkGraph = (name, maxDepth = 1, limit = 300) =>
  req("GET", `/benchmark/graph?name=${encodeURIComponent(name)}&max_depth=${maxDepth}&limit=${limit}`);
export const fetchBenchmarkPage = (graph, page) =>
  req("GET", `/benchmark/page?graph=${encodeURIComponent(graph)}&name=${encodeURIComponent(page)}`);
export const fetchAudit = (annotator = "1") => req("GET", `/benchmark/audit?annotator=${annotator}`);
export const putAuditLabel = (id, humanLabel, annotator = "1") =>
  req("PUT", `/benchmark/audit/${encodeURIComponent(id)}?annotator=${annotator}`, { human_label: humanLabel });
export const fetchAuditScore = (annotator = "1", source = "ui") =>
  req("POST", `/benchmark/audit/score?annotator=${annotator}&source=${source}`);
export const fetchBenchmarkEstimate = (budget) => req("GET", `/benchmark/estimate?budget=${budget}`);
export const startBenchmarkJob = (kind, args) => req("POST", "/benchmark/jobs", { kind, args });
export const benchmarkJob = () => req("GET", "/benchmark/jobs/current");
export const stopBenchmarkJob = () => req("POST", "/benchmark/jobs/stop");
export const previewPrompt = (body) => req("POST", "/config/prompts/preview", body);
