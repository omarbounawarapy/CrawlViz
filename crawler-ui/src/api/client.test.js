import { describe, it, expect, vi, afterEach } from "vitest";
import { fetchTemplates, runCrawl, saveConfig, API_STATUS_EVENT } from "./client";

afterEach(() => vi.unstubAllGlobals());

describe("REST client errors", () => {
  it("says the backend is unreachable and announces it", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new TypeError("Failed to fetch"))));
    const seen = [];
    window.addEventListener(API_STATUS_EVENT, (e) => seen.push(e.detail.reachable));
    await expect(fetchTemplates()).rejects.toThrow(/Cannot reach the backend/);
    expect(seen.at(-1)).toBe(false);
  });

  it("explains a bare 404 as a missing endpoint", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve({
      ok: false, status: 404, statusText: "Not Found", json: () => Promise.resolve({ detail: "Not Found" }),
    })));
    await expect(fetchTemplates()).rejects.toThrow(/no endpoint \/templates/);
  });

  it("keeps a specific detail from the server", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve({
      ok: false, status: 409, statusText: "Conflict", json: () => Promise.resolve({ detail: "A crawl is already running" }),
    })));
    await expect(fetchTemplates()).rejects.toThrow("A crawl is already running");
  });

  it("turns structured validation errors into field paths", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve({
      ok: false, status: 422, statusText: "Unprocessable", json: () => Promise.resolve({
        detail: { errors: [{ path: "fetch.min_delay", message: "Input should be >= 0" }] },
      }),
    })));
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
      templateName: "a.json", overrides: { fetch: { min_delay: 2 } }, seed: 7,
    });
  });
});
