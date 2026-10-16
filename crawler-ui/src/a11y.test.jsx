// WCAG 2.1 AA checks across the app: axe-core on every page and panel (contrast is checked
// separately, jsdom does no layout), plus the keyboard and labelling behaviour axe cannot see.
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup, waitFor, within, act, configure } from "@testing-library/react";
import { axeViolations, orphanLabels } from "./test/axe";
import schema from "./features/config/fixtures/schema.json";
import defaults from "./features/config/fixtures/defaults.json";

configure({ asyncUtilTimeout: 8000 });

vi.mock("./api/client", () => {
  const ok = (v) => vi.fn(() => Promise.resolve(v));
  return {
    API_STATUS_EVENT: "crawlviz:api-status",
    fetchTemplates: ok({ templates: ["wikiMD.json", "isi.json"] }),
    fetchTemplate: ok({ content: { blueprint_id: "wiki", id: "run_1", target_topic: "Type 2 diabetes", scoring: { strategy: "TOPICAL" }, stop_conditions: { max_nodes: 100 }, domains: {}, extraction: { fields: {} } } }),
    createTemplate: ok({}), updateTemplate: ok({}), deleteTemplate: ok({}),
    runCrawl: ok({}), stopCrawl: ok({ stopped: true }),
    crawlStatus: ok({ running: false, llm_calls: null }),
    fetchValidationTables: ok({ tables: ["pages"] }),
    fetchValidationCrawls: ok({ crawls: [{ crawl_id: "c1", last_seen: "2026-10-01T10:00:00Z", count: 1 }] }),
    fetchValidationSample: ok({ rows: [{ id: 1, url: "https://example.org/a", title: "Page A", body: "Some text." }], count: 1 }),
    fetchConfigSchema: ok(schema), fetchConfig: ok(defaults), fetchConfigDefaults: ok(defaults),
    saveConfig: ok(defaults), replaceConfig: ok(defaults), validateConfig: ok({ valid: true, errors: [] }),
    exportConfig: ok({}), resetConfig: ok(defaults), patchLiveConfig: ok({}),
    fetchPresets: ok({
      builtin: { polite: {} }, user: { mine: {} }, descriptions: { polite: "Slow." },
      goals: { gentler: { label: "Gentler on a site", description: "Waits longer.", values: { fetch: { min_delay: 2 } } } },
    }),
    savePreset: ok({}), deletePreset: ok({}), applyPreset: ok(defaults),
    fetchProviders: ok({ groq: { models: ["m1"], keys: 1 } }),
    fetchKeys: ok({ groq: [{ id: "k1", last4: "1234" }] }), addKey: ok({}), removeKey: ok({}),
    fetchBenchmarkOverview: ok({
      protocol: { hypotheses: [{ id: "H1", text: "Cascade beats bfs.", comparison: "x" }], primary_metric: "harvest@30", budgets: [50], arms: [], models: [], amendments: [] },
      graphs: { "isi.json": { pages: 3, edges: 2, labels: { 0: 1, 1: 1, 2: 1 }, out_degree: { mean: 1, median: 1, max: 2 }, absent_links: 0, relevant_unreachable: 0, depth: [{ depth: 0, pages: 1, label1: 0, label2: 1 }] } },
      audit: null, runs: 1,
    }),
    fetchBenchmarkRuns: ok([{ name: "r1", policy: "cascade", rep: 0, budget: 50, fetched: 3, found: 2, harvest30: 0.5, input_tokens: 10, output_tokens: 5, valid: true, short: false, status: "ok", replay: false }]),
    fetchBenchmarkRun: ok({ labels: [2, 0, 1], sequence: ["/a", "/b", "/c"], manifest: {}, settings: {} }),
    fetchBenchmarkCurves: ok({
      series: {
        cascade: { points: Array.from({ length: 20 }, (_, i) => ({ k: i + 1, mean: 0.5, ci95: 0.1 })), runs: 3, rel_per_call: 1, rel_per_1k_tokens: 2, short: 0 },
        random: { points: Array.from({ length: 20 }, (_, i) => ({ k: i + 1, mean: 0.1 })), runs: 3, rel_per_call: null, rel_per_1k_tokens: null, short: 0 },
      },
      validity: { cascade: { valid: 3, invalid: 0 } },
    }),
    fetchBenchmarkGraph: ok({ nodes: [{ id: "s", parent: null, title: "Seed", label: 2, depth: 0 }, { id: "t", parent: "s", title: "Child", label: 0, depth: 1 }], shown: 2, total: 2, cross_links: 0, topic: "ISI" }),
    fetchBenchmarkPage: ok({ id: "s", text: "Seed text", links: [] }),
    fetchAudit: ok({ items: [{ id: "1", title: "Page one", excerpt: "x", human_label: null }, { id: "2", title: "Page two", excerpt: "y", human_label: 1 }], done: 1 }),
    putAuditLabel: ok({}),
    fetchAuditScore: vi.fn(() => Promise.reject(new Error("no annotated items yet"))),
    fetchBenchmarkEstimate: ok({ arms: {} }),
    startBenchmarkJob: ok({ state: "idle", log: [] }),
    benchmarkJob: ok({ state: "idle", log: [] }),
    stopBenchmarkJob: ok({ state: "idle", log: [] }),
    previewPrompt: ok({ blocks: [{ id: "sys", title: "System", kind: "locked", note: "Fixed.", text: "You score links." }], prompt: "You score links." }),
  };
});

import App from "./App";
import Landing from "./features/landing/Landing";
import SpiderLoader from "./features/loading/SpiderLoader";
import GraphView from "./features/graph/GraphView";
import NodeInspector from "./features/inspector/NodeInspector";
import TimelineDock from "./features/timeline/TimelinePage";
import ConfigPage from "./features/config/ConfigPage";
import HeaderPresets from "./features/config/HeaderPresets";
import RunPage from "./features/run/RunPage";
import BlueprintManager from "./features/blueprints/BlueprintManager";
import DataExplorer from "./features/data/DataExplorer";
import BenchmarkPage from "./features/benchmark/BenchmarkPage";
import NotFoundPage from "./features/errors/NotFoundPage";
import { INITIAL_STATE } from "./state/initialState";

class FakeWebSocket { constructor() { this.readyState = 0; } close() {} }

beforeEach(() => {
  window.location.hash = "";
  vi.stubGlobal("WebSocket", FakeWebSocket);
});
afterEach(cleanup);

const clean = async (node, opts) => expect(await axeViolations(node, opts)).toEqual([]);

const nodes = new Map([
  ["a", { node_id: "a", parent_id: null, state: "EXPANDED", llm_score: 90, priority: 0.9, url: "https://x.org/wiki/A", depth: 0 }],
  ["b", { node_id: "b", parent_id: "a", state: "SCORED", llm_score: 70, priority: 0.7, url: "https://x.org/wiki/B", depth: 1 }],
  ["c", { node_id: "c", parent_id: "a", state: "FETCHED", priority: 0.2, url: "https://x.org/wiki/C", depth: 1 }],
  ["d", { node_id: "d", parent_id: "b", state: "CREATED", url: "https://x.org/wiki/D", depth: 2 }],
]);
const edges = new Set(["a→b", "a→c", "b→d"]);

describe("whole pages pass axe", () => {
  it("the empty graph, with a skip link to main and a section title", async () => {
    const { container } = render(<App />);
    await clean(container, { page: true });
    const skip = screen.getByRole("link", { name: "Skip to content" });
    fireEvent.click(skip);
    expect(document.activeElement.id).toBe("main");
    expect(document.title).toBe("Graph · CrawlViz");
  });

  for (const [hash, title] of [["#/run", "Run a crawl"], ["#/blueprints", "Blueprints"], ["#/data", "Extracted data"], ["#/nope", "Page not found"]]) {
    it(`${hash} has its own title and no violations`, async () => {
      window.location.hash = hash;
      const { container } = render(<App />);
      await screen.findAllByRole("heading", { level: 1 });
      await waitFor(() => expect(document.title).toBe(`${title} · CrawlViz`));
      await clean(container, { page: true });
    });
  }

  it("the landing page", async () => {
    const { container } = render(<Landing onEnter={() => {}} instant />);
    await clean(container, { page: true });
  });

  it("the loader hides the page under it and starts on Skip", async () => {
    const { container } = render(<><main><button type="button">Behind</button></main><SpiderLoader progress={0.2} done={false} onSkip={() => {}} /></>);
    expect(document.activeElement.textContent).toBe("Skip");
    expect(container.querySelector("main").inert).toBe(true);
    await clean(container);
  });

  it("the not-found page", async () => {
    const { container } = render(<NotFoundPage route="nope" onNavigate={() => {}} />);
    await clean(container);
  });
});

describe("graph keyboard", () => {
  const setup = (props = {}) => render(
    <GraphView nodes={nodes} edges={edges} candidates={[{ parent_id: "a", url: "https://x.org/off", decision: "dropped", nlp_score: 0.1 }]}
      replayIndex={null} onNodeClick={vi.fn()} onBackgroundClick={vi.fn()} selectedNodeId={null} heading="Crawl graph" {...props} />,
  );
  const groups = (c) => [...c.querySelectorAll("g.node-group")];

  it("is one tab stop, and its pages say what they are", async () => {
    const { container } = setup();
    await waitFor(() => expect(groups(container).length).toBe(4));
    const stops = groups(container).filter((g) => g.getAttribute("tabindex") === "0");
    expect(stops).toHaveLength(1);
    expect(stops[0].getAttribute("data-node-id")).toBe("a");
    expect(stops[0].getAttribute("aria-label")).toMatch(/wiki\/A, seed page, expanded, relevance \d+ of 100, 2 child pages, 1 link skipped/);
    await clean(container);
  });

  it("arrow keys walk the tree", async () => {
    const { container } = setup();
    await waitFor(() => expect(groups(container).length).toBe(4));
    const g = (id) => container.querySelector(`g[data-node-id="${id}"]`);
    g("a").focus();
    fireEvent.keyDown(g("a"), { key: "ArrowDown" });
    const child = document.activeElement.getAttribute("data-node-id");
    expect(["b", "c"]).toContain(child);
    fireEvent.keyDown(document.activeElement, { key: "ArrowRight" });
    expect(document.activeElement.getAttribute("data-node-id")).toBe(child === "b" ? "c" : "b");
    fireEvent.keyDown(document.activeElement, { key: "ArrowUp" });
    expect(document.activeElement.getAttribute("data-node-id")).toBe("a");
    expect(groups(container).filter((n) => n.getAttribute("tabindex") === "0")).toHaveLength(1);
  });

  it("selects with Enter and marks the selection", async () => {
    const onNodeClick = vi.fn();
    const { container, rerender } = setup({ onNodeClick });
    await waitFor(() => expect(groups(container).length).toBe(4));
    fireEvent.keyDown(container.querySelector('g[data-node-id="b"]'), { key: "Enter" });
    expect(onNodeClick).toHaveBeenCalledWith(expect.objectContaining({ node_id: "b" }));
    rerender(<GraphView nodes={nodes} edges={edges} candidates={[]} replayIndex={null} onNodeClick={onNodeClick}
      onBackgroundClick={vi.fn()} selectedNodeId="b" heading="Crawl graph" annotationId="inspector" />);
    await waitFor(() => expect(container.querySelector('g[data-node-id="b"]').getAttribute("aria-current")).toBe("true"));
    expect(container.querySelector('g[data-node-id="b"]').getAttribute("tabindex")).toBe("0");
    expect(screen.getByRole("button", { name: "Read the annotation" })).toBeTruthy();
  });

  it("zoom keys work only from inside the graph", async () => {
    const { container } = setup();
    await waitFor(() => expect(groups(container).length).toBe(4));
    const level = () => screen.getByLabelText("Zoom level").textContent;
    const before = level();
    fireEvent.keyDown(document.body, { key: "+" });
    expect(level()).toBe(before);
  });

  it("announces how many pages match a search", async () => {
    setup();
    fireEvent.change(screen.getByLabelText("Find a page by URL"), { target: { value: "wiki/b" } });
    expect(screen.getByText("1 page matches")).toBeTruthy();
  });
});

describe("panels", () => {
  it("the annotation panel is a named landmark with real tabs", async () => {
    const { container } = render(
      <NodeInspector node={nodes.get("b")} detail={{ nlp_score: 0.5, llm_score: 70, priority: 0.7, nlp_breakdown: { target_similarity: 0.4 } }}
        allNodes={nodes} errors={[]} eventLog={[]} onSelectNode={() => {}} onClose={() => {}} />,
    );
    expect(screen.getByRole("complementary", { name: /^Annotation: / })).toBeTruthy();
    const tab = screen.getByRole("tab", { name: "Scoring" });
    fireEvent.click(tab);
    expect(tab.getAttribute("aria-selected")).toBe("true");
    expect(screen.getByRole("tabpanel")).toBeTruthy();
    await clean(container);
  });

  it("timeline events are buttons the keyboard reaches", async () => {
    const eventLog = [
      { type: "NODE_ADDED", node_id: "a", url: "/a", _receivedAt: Date.now() },
      { type: "NODE_ADDED", node_id: "b", url: "/b", _receivedAt: Date.now() },
    ];
    const onSeek = vi.fn();
    const { container } = render(<TimelineDock eventLog={eventLog} replayIndex={0} onSeek={onSeek} onExitReplay={() => {}} expanded onToggleExpanded={() => {}} />);
    const list = screen.getByRole("list", { name: "Events" });
    const rows = within(list).getAllByRole("button");
    expect(rows).toHaveLength(2);
    expect(rows[0].getAttribute("aria-current")).toBe("step");
    fireEvent.click(rows[1]);
    expect(onSeek).toHaveBeenCalledWith(1);
    expect(screen.getByRole("slider", { name: "Replay position" }).className).toContain("focus-box");
    await clean(container);
  });

  it("header sets stay reachable when no set matches", () => {
    render(<HeaderPresets fetch={{ user_agent: "custom/1.0" }} onApply={() => {}} />);
    const radios = screen.getAllByRole("radio");
    expect(radios.filter((r) => r.tabIndex === 0)).toHaveLength(1);
    expect(screen.getByRole("radiogroup", { name: "Header sets" })).toBeTruthy();
  });
});

describe("configuration", () => {
  const sections = ["start", "scoring-cascade", "fetch", "priority", "prompts", "pipelines", "llm", "providers", "presets", "api-keys"];
  for (const slug of sections) {
    it(`${slug}: no violations, no orphan labels`, async () => {
      window.location.hash = `#/config/${slug}`;
      const { container } = render(<ConfigPage />);
      await screen.findByLabelText("Search settings");
      await waitFor(() => expect(container.querySelectorAll("section, h3").length).toBeGreaterThan(0));
      expect(orphanLabels(container)).toEqual([]);
      await clean(container);
    });
  }

  it("names every non-native control from its row label", async () => {
    window.location.hash = "#/config/pipelines";
    render(<ConfigPage />);
    await screen.findByRole("table");
    for (const el of document.querySelectorAll('[role="radiogroup"], [role="spinbutton"], [role="group"]')) {
      const named = el.getAttribute("aria-label") || el.getAttribute("aria-labelledby");
      expect(named, el.outerHTML.slice(0, 120)).toBeTruthy();
    }
  });

  it("a number that does not parse says what to type", async () => {
    window.location.hash = "#/config/fetch";
    render(<ConfigPage />);
    const delay = await screen.findByLabelText(/^Min delay/);
    fireEvent.change(delay, { target: { value: "abc" } });
    expect(delay.getAttribute("aria-invalid")).toBe("true");
    const msg = document.getElementById(delay.getAttribute("aria-describedby").split(" ").pop());
    expect(msg.textContent).toMatch(/Enter a number/);
  });

  it("reset every setting asks for a second press", async () => {
    const api = await import("./api/client");
    window.location.hash = "#/config/presets";
    render(<ConfigPage />);
    const reset = await screen.findByRole("button", { name: "Reset every setting to defaults" });
    fireEvent.click(reset);
    expect(api.resetConfig).not.toHaveBeenCalled();
    fireEvent.keyDown(reset, { key: "Escape" });
    expect(reset.textContent).toBe("Reset every setting to defaults");
    fireEvent.click(reset);
    fireEvent.click(reset);
    await waitFor(() => expect(api.resetConfig).toHaveBeenCalled());
  });
});

describe("other pages", () => {
  it("run page", async () => {
    const { container } = render(<RunPage onNavigate={() => {}} state={INITIAL_STATE} metrics={{}} />);
    await screen.findByText("What this will run");
    expect(orphanLabels(container)).toEqual([]);
    await clean(container);
  });

  it("blueprints, editing an existing blueprint", async () => {
    const { container } = render(<BlueprintManager onNavigate={() => {}} />);
    fireEvent.click(await screen.findByRole("button", { name: "wikiMD.json" }));
    await screen.findByRole("tab", { name: "Form" });
    expect(orphanLabels(container)).toEqual([]);
    await clean(container);
  });

  it("blueprints, a new one has a visible file name label", async () => {
    const { container } = render(<BlueprintManager onNavigate={() => {}} />);
    fireEvent.click(await screen.findByRole("button", { name: "New blueprint" }));
    expect(screen.getByLabelText("File name")).toBeTruthy();
    await clean(container);
  });

  it("extracted data", async () => {
    const { container } = render(<DataExplorer graphNodes={new Map()} onOpenNode={() => {}} />);
    await waitFor(() => expect(screen.getAllByRole("option").length).toBeGreaterThan(1));
    fireEvent.change(screen.getByLabelText("Dataset"), { target: { value: "pages" } });
    await screen.findByText("Page A");
    await clean(container);
  });

  for (const tab of ["Overview", "Results", "Runs", "Graph", "Audit"]) {
    it(`benchmark ${tab}`, async () => {
      const { container } = render(<BenchmarkPage />);
      fireEvent.click(screen.getByRole("tab", { name: tab }));
      await waitFor(() => expect(container.querySelector('[role="status"]')?.textContent ?? "").not.toBe("Loading…"));
      if (tab === "Runs") {
        fireEvent.click(await screen.findByRole("button", { name: "cascade, rep 0" }));
        await screen.findByText("Visit order as a list");
      }
      if (tab === "Results") await screen.findByText("The curves as a table");
      if (tab === "Audit") {
        const radios = await screen.findAllByRole("radio", { name: "Label 1" });
        expect(radios[1].getAttribute("aria-checked")).toBe("true");
        // Every arrow key moves the answer inside a group (WAI radio pattern).
        const first = screen.getAllByRole("radio", { name: "Label 0" })[0];
        first.focus();
        fireEvent.keyDown(first, { key: "ArrowDown" });
        await waitFor(() => expect(screen.getAllByRole("radio", { name: "Label 1" })[0].getAttribute("aria-checked")).toBe("true"));
        expect(document.activeElement.getAttribute("aria-label")).toBe("Label 1");
        // A digit answers the item in focus and moves to the next item's answers.
        fireEvent.keyDown(document.activeElement, { key: "2" });
        await waitFor(() => expect(screen.getAllByRole("radio", { name: "Label 2" })[0].getAttribute("aria-checked")).toBe("true"));
        await waitFor(() => expect(document.activeElement.closest("li")?.querySelector("h3")?.textContent).toBe("Page two"));
      }
      await act(async () => {});
      await clean(container);
    });
  }
});
