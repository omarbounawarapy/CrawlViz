import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, within, fireEvent, cleanup, configure } from "@testing-library/react";

configure({ asyncUtilTimeout: 8000 }); // the page renders ~150 controls; slow CI needs headroom
import schema from "./fixtures/schema.json";
import defaults from "./fixtures/defaults.json";

vi.mock("../../api/client", () => ({
  fetchConfigSchema: vi.fn(() => Promise.resolve(schema)),
  fetchConfig: vi.fn(() => Promise.resolve(defaults)),
  fetchConfigDefaults: vi.fn(() => Promise.resolve(defaults)),
  saveConfig: vi.fn((patch) => Promise.resolve({ ...defaults, ...patch })),
  resetConfig: vi.fn(() => Promise.resolve(defaults)),
  fetchKeys: vi.fn(() => Promise.resolve({ groq: [{ id: "abc", last4: "1234", last_used: null }] })),
  fetchProviders: vi.fn(() => Promise.resolve({ groq: { models: ["m1"], keys: 1 }, openai: { models: [], keys: 0 } })),
  addKey: vi.fn(() => Promise.resolve({ id: "new" })),
  removeKey: vi.fn(() => Promise.resolve({ removed: "abc" })),
  crawlStatus: vi.fn(() => Promise.resolve({ running: true })),
  patchLiveConfig: vi.fn(() => Promise.resolve({})),
  fetchPresets: vi.fn(() => Promise.resolve({ builtin: { polite: {} }, user: { mine: {} } })),
  applyPreset: vi.fn(() => Promise.resolve({ ...defaults, fetch: { ...defaults.fetch, min_delay: 2 } })),
  savePreset: vi.fn(() => Promise.resolve({ saved: "x" })),
  deletePreset: vi.fn(() => Promise.resolve({ removed: "mine" })),
  exportConfig: vi.fn(() => Promise.resolve({})),
  validateConfig: vi.fn(() => Promise.resolve({ valid: true, errors: [] })),
  replaceConfig: vi.fn(() => Promise.resolve(defaults)),
}));

import * as api from "../../api/client";
import ConfigPage from "./ConfigPage";

beforeEach(() => vi.clearAllMocks());
afterEach(cleanup);

const type = (el, v) => fireEvent.change(el, { target: { value: v } });

describe("ConfigPage", () => {
  it("edits a setting and saves only the changed value", async () => {
    render(<ConfigPage />);
    const delay = await screen.findByLabelText(/^Min delay/);
    type(delay, "2.5");
    expect(screen.getAllByText("unsaved").length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(api.saveConfig).toHaveBeenCalledWith({ fetch: { min_delay: 2.5 } }));
    expect(await screen.findByText(/^Saved\. New values apply/)).toBeTruthy();
  });

  it("blocks saving a value outside the schema bounds", async () => {
    render(<ConfigPage />);
    const table = await screen.findByRole("table");
    const workers = within(table).getByLabelText("filtering workers");
    type(workers, "0");
    expect(screen.getByRole("button", { name: "Save changes" }).disabled).toBe(true);
  });

  it("filters settings by search", async () => {
    render(<ConfigPage />);
    await screen.findByLabelText(/^Min delay/);
    type(screen.getByLabelText("Search settings"), "user agent");
    expect(screen.getByLabelText(/^User agent/)).toBeTruthy();
    expect(screen.queryByLabelText(/^Min delay/)).toBeNull();
  });

  it("lists masked keys and adds one", async () => {
    render(<ConfigPage />);
    expect(await screen.findByText("••••1234")).toBeTruthy();
    type(screen.getByLabelText("API key"), "sk-new-key");
    fireEvent.click(screen.getByRole("button", { name: "Add key" }));
    await waitFor(() => expect(api.addKey).toHaveBeenCalledWith("groq", "sk-new-key"));
  });

  it("pushes only live fields to a running crawl", async () => {
    render(<ConfigPage />);
    type(await screen.findByLabelText(/^Min delay/), "0.4");
    const apply = await screen.findByRole("button", { name: "Apply live" });
    await waitFor(() => expect(apply.disabled).toBe(false));
    fireEvent.click(apply);
    await waitFor(() => expect(api.patchLiveConfig).toHaveBeenCalledWith({ fetch: { min_delay: 0.4 } }));
    await waitFor(() => expect(api.saveConfig).toHaveBeenCalled());
  });

  it("applies and deletes presets", async () => {
    render(<ConfigPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Apply preset polite" }));
    await waitFor(() => expect(api.applyPreset).toHaveBeenCalledWith("polite"));
    fireEvent.click(await screen.findByRole("button", { name: "Delete preset mine" }));
    await waitFor(() => expect(api.deletePreset).toHaveBeenCalledWith("mine"));
  });

  it("edits a prompt in a textarea", async () => {
    render(<ConfigPage />);
    const box = await screen.findByLabelText(/^Scoring system/);
    expect(box.tagName).toBe("TEXTAREA");
  });
});
