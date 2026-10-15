import { describe, it, expect, vi, afterEach } from "vitest";
import { fetchTemplates, API_STATUS_EVENT } from "./client";

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
});
