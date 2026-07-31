const BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

async function req(method, path, body) {
  const opts = {
    method,
    headers: { "Content-Type": "application/json" },
  };
  if (body !== undefined) opts.body = JSON.stringify(body);
  const res = await fetch(`${BASE}${path}`, opts);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? res.statusText);
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
// Read-only this pass -- see config/runtime_config.py and
// docs/V2_ARCHITECTURE.md roadmap #18 for the write-back path this sets up.
export const fetchConfigSchema = () => req("GET", "/config/schema");
export const fetchConfig       = () => req("GET", "/config");
