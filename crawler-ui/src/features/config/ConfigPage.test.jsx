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
  previewPrompt: vi.fn(() => Promise.resolve({ blocks: [], prompt: "" })),
}));

import * as api from "../../api/client";
import ConfigPage from "./ConfigPage";

beforeEach(() => { vi.clearAllMocks(); window.location.hash = ""; });
afterEach(cleanup);

const at = (slug) => { window.location.hash = `#/config/${slug}`; };

const type = (el, v) => fireEvent.change(el, { target: { value: v } });

describe("ConfigPage", () => {
  it("edits a setting and saves only the changed value", async () => {
    at("fetch");
    render(<ConfigPage />);
    const delay = await screen.findByLabelText(/^Min delay/);
    type(delay, "2.5");
    expect(screen.getAllByText("unsaved").length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(api.saveConfig).toHaveBeenCalledWith({ fetch: { min_delay: 2.5 } }));
    expect(await screen.findByText(/^Saved\. New values apply/)).toBeTruthy();
  });

  it("keeps worker counts inside the schema bounds", async () => {
    at("pipelines");
    render(<ConfigPage />);
    const table = await screen.findByRole("table");
    const workers = within(table).getByLabelText("filtering workers");
    expect(workers.getAttribute("aria-valuemin")).toBe("1");
    expect(workers.getAttribute("aria-valuemax")).toBe("64");
    fireEvent.keyDown(workers, { key: "Home" });
    expect(workers.getAttribute("aria-valuenow")).toBe("1");
    expect(within(table).getByLabelText("Decrease filtering workers").disabled).toBe(true);
    fireEvent.keyDown(workers, { key: "ArrowUp" });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(api.saveConfig).toHaveBeenCalledWith({ pipelines: { filtering: { workers: 2 } } }));
  });

  it("stores no queue limit as null and a limit as a number", async () => {
    at("pipelines");
    render(<ConfigPage />);
    const table = await screen.findByRole("table");
    const none = within(table).getByLabelText("filtering max queue size no limit");
    expect(none.checked).toBe(true);
    fireEvent.click(none);
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(api.saveConfig).toHaveBeenCalledWith({ pipelines: { filtering: { max_queue_size: 100 } } }));
  });

  it("shows one section at a time and marks it current", async () => {
    at("fetch");
    render(<ConfigPage />);
    await screen.findByLabelText(/^Min delay/);
    expect(screen.queryByLabelText("System prompt")).toBeNull();
    const nav = screen.getByRole("navigation", { name: "Configuration sections" });
    expect(within(nav).getByText("Fetch").getAttribute("aria-current")).toBe("page");
    expect(within(nav).getByText("Prompts").getAttribute("aria-current")).toBeNull();
    fireEvent.click(within(nav).getByText("Prompts"));
    expect(await screen.findByLabelText("System prompt")).toBeTruthy();
    expect(window.location.hash).toBe("#/config/prompts");
  });

  it("opens on the first section in workflow order", async () => {
    render(<ConfigPage />);
    expect(await screen.findByText(/Decides which links the cheap NLP score settles/)).toBeTruthy();
    const nav = screen.getByRole("navigation", { name: "Configuration sections" });
    const names = within(nav).getAllByRole("link").map((a) => a.textContent);
    expect(names.slice(0, 3)).toEqual(["Scoring cascade", "Fetch", "Priority"]);
  });

  it("dims the cut-off pair that percentile mode is not using", async () => {
    render(<ConfigPage />);
    const thresholds = await screen.findAllByRole("slider", { name: /threshold/i });
    expect(thresholds).toHaveLength(2);
    const opacity = () => thresholds[0].closest("div[style*='opacity']").style.opacity;
    const percentiles = screen.getByRole("radio", { name: "Per-page percentiles" });
    expect(percentiles.getAttribute("aria-checked")).toBe("true");
    expect(opacity()).toBe("0.45");
    fireEvent.click(screen.getByRole("radio", { name: "Fixed score cut-offs" }));
    await waitFor(() => expect(opacity()).toBe("1"));
  });

  it("filters settings by search across sections", async () => {
    render(<ConfigPage />);
    await screen.findByText("Scoring cascade", { selector: "h2" });
    type(screen.getByLabelText("Search settings"), "user agent");
    expect(screen.getByLabelText(/^User agent/)).toBeTruthy();
    expect(screen.queryByLabelText(/^Min delay/)).toBeNull();
  });

  it("lists masked keys and adds one", async () => {
    at("api-keys");
    render(<ConfigPage />);
    expect(await screen.findByText("••••1234")).toBeTruthy();
    type(screen.getByLabelText("API key"), "sk-new-key");
    fireEvent.click(screen.getByRole("button", { name: "Add key" }));
    await waitFor(() => expect(api.addKey).toHaveBeenCalledWith("groq", "sk-new-key"));
  });

  it("pushes only live fields to a running crawl", async () => {
    at("fetch");
    render(<ConfigPage />);
    type(await screen.findByLabelText(/^Min delay/), "0.4");
    const apply = await screen.findByRole("button", { name: "Apply live" });
    await waitFor(() => expect(apply.disabled).toBe(false));
    fireEvent.click(apply);
    await waitFor(() => expect(api.patchLiveConfig).toHaveBeenCalledWith({ fetch: { min_delay: 0.4 } }));
    await waitFor(() => expect(api.saveConfig).toHaveBeenCalled());
  });

  it("applies and deletes presets", async () => {
    at("presets");
    render(<ConfigPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Apply preset polite" }));
    await waitFor(() => expect(api.applyPreset).toHaveBeenCalledWith("polite"));
    fireEvent.click(await screen.findByRole("button", { name: "Delete preset mine" }));
    await waitFor(() => expect(api.deletePreset).toHaveBeenCalledWith("mine"));
  });

  it("edits a prompt in a textarea", async () => {
    at("prompts");
    render(<ConfigPage />);
    const box = await screen.findByLabelText("System prompt");
    expect(box.tagName).toBe("TEXTAREA");
  });

  it("shows what a preset changes before applying it", async () => {
    api.fetchPresets.mockResolvedValueOnce({
      builtin: { gentle: { fetch: { min_delay: 5 } } }, descriptions: { gentle: "Slow and kind." }, user: {},
    });
    at("presets");
    render(<ConfigPage />);
    expect(await screen.findByText("Slow and kind.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Show what preset gentle changes" }));
    const list = await screen.findByLabelText("Changes made by gentle");
    expect(list.textContent).toMatch(/Min delay.*→.*5/);
  });

  it("suggests a fix for a risky value and applies it with one click", async () => {
    const risky = JSON.parse(JSON.stringify(defaults));
    risky.fetch.min_delay = 0.2;
    risky.pipelines.requests.workers = 8;
    api.fetchConfig.mockResolvedValueOnce(risky);
    at("fetch");
    render(<ConfigPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Set the pause to 1 s" }));
    await waitFor(() => expect(screen.queryByRole("button", { name: "Set the pause to 1 s" })).toBeNull());
    expect(screen.getByLabelText(/^Min delay/).value).toBe("1");
  });
});
