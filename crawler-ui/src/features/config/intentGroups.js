/**
 * Fields of a section grouped by what the person is trying to do. Each group
 * has a heading and one line saying when to reach for it. Fields not listed
 * here fall under "Other settings".
 */
export const FETCH_GROUPS = [
  {
    title: "Be gentler",
    hint: "Slow every request down, and back off further when a site says too many requests.",
    paths: ["fetch.min_delay", "fetch.jitter_max", "fetch.backoff_start", "fetch.backoff_max", "fetch.backoff_growth"],
  },
  {
    title: "Go faster once a site allows it",
    hint: "How quickly the shared backoff is given back after requests succeed or fail for other reasons.",
    paths: ["fetch.backoff_success_decay", "fetch.backoff_failure_decay"],
  },
  {
    title: "Wait for slow responses",
    hint: "How long a page or LLM reply may take before it counts as a failure.",
    paths: ["fetch.http_total_timeout", "fetch.http_connect_timeout"],
  },
  {
    title: "Look like a browser",
    hint: "What the crawler says about itself on each request.",
    paths: [
      "fetch.user_agent",
      "fetch.accept",
      "fetch.accept_encoding",
      "fetch.accept_language",
      "fetch.extra_headers",
    ],
  },
  {
    title: "Robots.txt",
    hint: "Whether pages a site disallows are skipped, and how long its rules are kept.",
    paths: ["fetch.respect_robots", "fetch.robots_ttl_seconds"],
  },
];

export const SECTION_GROUPS = { Fetch: FETCH_GROUPS };
