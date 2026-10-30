import { describe, it, expect, vi, afterEach, beforeEach } from "vitest";
import { fetchTemplates, runCrawl, saveConfig, API_STATUS_EVENT } from "./client";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("REST client errors", () => {
  beforeEach(() => vi.stubEnv("VITE_API_TOKEN", "build-token"));

  it("says the backend is unreachable and announces it", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.reject(new TypeError("Failed to fetch"))),
    );
    const seen = [];
    window.addEventListener(API_STATUS_EVENT, (e) => seen.push(e.detail.reachable));
    await expect(fetchTemplates()).rejects.toThrow(/Cannot reach the backend/);
    expect(seen.at(-1)).toBe(false);
  });

  it("explains a bare 404 as a missing endpoint", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve({
          ok: false,
          status: 404,
          statusText: "Not Found",
          json: () => Promise.resolve({ detail: "Not Found" }),
        }),
      ),
    );
    await expect(fetchTemplates()).rejects.toThrow(/no endpoint \/templates/);
  });

  it("keeps a specific detail from the server", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve({
          ok: false,
          status: 409,
          statusText: "Conflict",
          json: () => Promise.resolve({ detail: "A crawl is already running" }),
        }),
      ),
    );
    await expect(fetchTemplates()).rejects.toThrow("A crawl is already running");
  });

  it("turns structured validation errors into field paths", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve({
          ok: false,
          status: 422,
          statusText: "Unprocessable",
          json: () =>
            Promise.resolve({
              detail: { errors: [{ path: "fetch.min_delay", message: "Input should be >= 0" }] },
            }),
        }),
      ),
    );
    const err = await saveConfig({ fetch: { min_delay: -1 } }).catch((e) => e);
    expect(err.message).toBe("fetch.min_delay: Input should be >= 0");
    expect(err.errors[0].path).toBe("fetch.min_delay");
  });

  it("sends run overrides only when there are some", async () => {
    const fn = vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve({}) }));
    vi.stubGlobal("fetch", fn);
    await runCrawl("a.json");
    expect(JSON.parse(fn.mock.calls[0][1].body)).toEqual({ templateName: "a.json" });
    await runCrawl("a.json", { fetch: { min_delay: 2 } }, 7);
    expect(JSON.parse(fn.mock.calls[1][1].body)).toEqual({
      templateName: "a.json",
      overrides: { fetch: { min_delay: 2 } },
      seed: 7,
    });
  });
});

function reply(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: String(status),
    json: () => Promise.resolve(body),
  };
}

// A fresh module per test: the client keeps the session token in a module-level cache.
async function freshClient() {
  vi.resetModules();
  return import("./client");
}

const callsTo = (fn, path) => fn.mock.calls.filter(([url]) => url.endsWith(path));

describe("REST client session token", () => {
  beforeEach(() => vi.stubEnv("VITE_API_TOKEN", ""));

  it("uses the token the build was given and never asks /session", async () => {
    vi.stubEnv("VITE_API_TOKEN", "build-token");
    const fn = vi.fn(() => Promise.resolve(reply(200, {})));
    vi.stubGlobal("fetch", fn);
    const { fetchTemplates: list } = await freshClient();
    await list();
    expect(callsTo(fn, "/session")).toHaveLength(0);
    expect(fn.mock.calls[0][1].headers.Authorization).toBe("Bearer build-token");
  });

  it("fetches /session once, keeps the token, and sends it with a JSON content type on every call", async () => {
    const fn = vi.fn((url) =>
      Promise.resolve(url.endsWith("/session") ? reply(200, { token: "abc" }) : reply(200, {})),
    );
    vi.stubGlobal("fetch", fn);
    const { fetchTemplates: list, deleteTemplate: remove, stopCrawl: stop } = await freshClient();
    await Promise.all([list(), list()]);
    await remove("a.json");
    await stop();

    expect(callsTo(fn, "/session")).toHaveLength(1);
    for (const [url, opts] of fn.mock.calls.filter(([u]) => !u.endsWith("/session"))) {
      expect(opts.headers.Authorization, url).toBe("Bearer abc");
      expect(opts.headers["Content-Type"], url).toBe("application/json");
    }
  });

  it("on a 401 drops the token, asks /session again and retries the call once", async () => {
    let issued = 0;
    const fn = vi.fn((url, opts) => {
      if (url.endsWith("/session")) return Promise.resolve(reply(200, { token: `token-${++issued}` }));
      const fresh = opts.headers.Authorization === "Bearer token-2";
      return Promise.resolve(fresh ? reply(200, { templates: [] }) : reply(401, { detail: "The API token is wrong." }));
    });
    vi.stubGlobal("fetch", fn);
    const { fetchTemplates: list } = await freshClient();
    await expect(list()).resolves.toEqual({ templates: [] });
    expect(callsTo(fn, "/session")).toHaveLength(2);
    expect(callsTo(fn, "/templates")).toHaveLength(2);
  });

  it("shows the backend's message when the retry is refused too", async () => {
    const fn = vi.fn((url) =>
      Promise.resolve(
        url.endsWith("/session")
          ? reply(200, { token: "abc" })
          : reply(401, { detail: "The API token is missing or wrong." }),
      ),
    );
    vi.stubGlobal("fetch", fn);
    const { fetchTemplates: list } = await freshClient();
    await expect(list()).rejects.toThrow("The API token is missing or wrong.");
    expect(callsTo(fn, "/templates")).toHaveLength(2);
  });

  it("does not cache a failed /session lookup", async () => {
    let sessionCalls = 0;
    const fn = vi.fn((url) => {
      if (url.endsWith("/session")) {
        sessionCalls += 1;
        return Promise.resolve(
          sessionCalls === 1
            ? reply(404, { detail: "Token comes from the environment." })
            : reply(200, { token: "abc" }),
        );
      }
      return Promise.resolve(reply(200, {}));
    });
    vi.stubGlobal("fetch", fn);
    const { fetchTemplates: list } = await freshClient();
    await expect(list()).rejects.toThrow("Token comes from the environment.");
    await expect(list()).resolves.toEqual({});
  });
});
