import { describe, it, expect } from "vitest";
import schema from "./fixtures/schema.json";
import defaults from "./fixtures/defaults.json";
import {
  buildFields, buildPatch, getIn, groupBySection, matches, setIn, validateField,
} from "./configModel";

const fields = buildFields(schema);
const byPath = Object.fromEntries(fields.map((f) => [f.path, f]));

describe("buildFields", () => {
  it("flattens nested pipeline settings with their group", () => {
    const f = byPath["pipelines.filtering.workers"];
    expect(f).toMatchObject({ group: "filtering", topKey: "pipelines", type: "integer", minimum: 1, maximum: 64 });
  });

  it("reads hints and unwraps nullable numbers", () => {
    expect(byPath["fetch.min_delay"]).toMatchObject({ apply: "live", unit: "s", widget: "number" });
    expect(byPath["llm.max_tokens"]).toMatchObject({ nullable: true, type: "integer" });
    expect(byPath["fetch.extra_headers"].widget).toBe("headers");
    expect(byPath["nlp.composite_weights"].widget).toBe("weights");
    expect(byPath["fetch.respect_robots"].widget).toBe("toggle");
  });

  it("covers every leaf of the default config", () => {
    const leaves = [];
    const walk = (o, p) => Object.entries(o).forEach(([k, v]) => {
      const path = p ? `${p}.${k}` : k;
      const isLeaf = v === null || typeof v !== "object" || ["extra_headers", "composite_weights", "strategy_contexts", "endpoints"].includes(k) || k.endsWith("_weights");
      if (isLeaf) leaves.push(path); else walk(v, path);
    });
    walk(defaults, "");
    expect(fields.map((f) => f.path).sort()).toEqual(leaves.sort());
  });
});

describe("patching", () => {
  it("builds a nested patch of only the changed leaves", () => {
    const draft = setIn(setIn(defaults, "fetch.min_delay", 3), "pipelines.priority.workers", 2);
    expect(buildPatch(fields, draft, defaults)).toEqual({
      fetch: { min_delay: 3 },
      pipelines: { priority: { workers: 2 } },
    });
    expect(getIn(draft, "pipelines.filtering.workers")).toBe(10);
  });

  it("sends a cleared nullable value as null", () => {
    const draft = setIn(setIn(defaults, "llm.max_tokens", 500), "llm.max_tokens", null);
    expect(buildPatch(fields, draft, defaults)).toEqual({});
    const saved = setIn(defaults, "llm.max_tokens", 500);
    expect(buildPatch(fields, setIn(saved, "llm.max_tokens", null), saved)).toEqual({ llm: { max_tokens: null } });
  });

  it("does not mutate its input", () => {
    const before = JSON.stringify(defaults);
    setIn(defaults, "fetch.min_delay", 9);
    expect(JSON.stringify(defaults)).toBe(before);
  });
});

describe("validation and search", () => {
  it("applies the schema bounds", () => {
    const w = byPath["pipelines.filtering.workers"];
    expect(validateField(w, 0)).toMatch(/At least 1/);
    expect(validateField(w, 100)).toMatch(/At most 64/);
    expect(validateField(w, 1.5)).toMatch(/whole number/);
    expect(validateField(w, 10)).toBeNull();
    expect(validateField(byPath["llm.max_tokens"], null)).toBeNull();
    expect(validateField(byPath["fetch.min_delay"], "")).toBe("Required");
  });

  it("groups by section and searches names and descriptions", () => {
    const sections = groupBySection(fields).map(([s]) => s);
    expect(sections).toEqual(expect.arrayContaining(["Fetch", "Pipelines", "Retries", "Scoring cascade", "LLM"]));
    expect(fields.filter((f) => matches(f, "user-agent")).map((f) => f.path)).toContain("fetch.user_agent");
    expect(fields.filter((f) => matches(f, "zzzz"))).toHaveLength(0);
  });
});
