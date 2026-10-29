// Complete header sets for the Fetch section. Each one fills every header field at once.
// Browser-like sets send what that browser sends; the crawler still identifies itself
// through robots.txt rules only if a site checks the user agent, so pick one honestly.

export const HEADER_FIELDS = ["user_agent", "accept", "accept_encoding", "accept_language", "extra_headers"];

export const HEADER_PRESETS = [
  {
    name: "Polite research bot",
    about: "Says who it is and why. Best for sites that welcome crawlers.",
    values: {
      user_agent: "CrawlViz/1.0 (research crawler; contact: you@example.org)",
      accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
      accept_encoding: "gzip, deflate",
      accept_language: "",
      extra_headers: {},
    },
  },
  {
    name: "Desktop Chrome",
    about: "Looks like Chrome on Windows. Fewer pages refuse it.",
    values: {
      user_agent:
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
      accept: "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
      accept_encoding: "gzip, deflate",
      accept_language: "en-US,en;q=0.9",
      extra_headers: { "Upgrade-Insecure-Requests": "1" },
    },
  },
  {
    name: "Desktop Firefox",
    about: "Looks like Firefox on Linux.",
    values: {
      user_agent: "Mozilla/5.0 (X11; Linux x86_64; rv:131.0) Gecko/20100101 Firefox/131.0",
      accept: "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
      accept_encoding: "gzip, deflate",
      accept_language: "en-US,en;q=0.5",
      extra_headers: { "Upgrade-Insecure-Requests": "1" },
    },
  },
  {
    name: "Mobile Safari",
    about: "Looks like an iPhone. Some sites serve a lighter page.",
    values: {
      user_agent:
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
      accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
      accept_encoding: "gzip, deflate",
      accept_language: "en-US,en;q=0.9",
      extra_headers: {},
    },
  },
  {
    name: "Minimal",
    about: "A bare client that asks for anything. Useful for testing a site's reaction.",
    values: {
      user_agent: "python-requests/2.32",
      accept: "*/*",
      accept_encoding: "gzip, deflate",
      accept_language: "",
      extra_headers: {},
    },
  },
];

const same = (a, b) => JSON.stringify(a ?? "") === JSON.stringify(b ?? "");

/** The preset whose values the draft's `fetch` currently holds, if any. */
export function activePreset(fetch) {
  return HEADER_PRESETS.find((p) => HEADER_FIELDS.every((k) => same(p.values[k], fetch?.[k]))) ?? null;
}
