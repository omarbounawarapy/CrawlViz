import { describe, it, expect } from "vitest";
import { suggest } from "./suggestions";
import { presetChanges, flatten } from "./presetModel";
import defaults from "./fixtures/defaults.json";

const cfg = (patch = {}) => JSON.parse(JSON.stringify({ ...defaults, ...patch }));

describe("suggest", () => {
  it("is silent on the defaults", () => {
    expect(suggest(cfg())).toEqual([]);
  });
  it("flags a fast pause with many workers and offers a fix", () => {
    const c = cfg();
    c.fetch.min_delay = 0.2;
    c.pipelines.requests.workers = 8;
    const [s] = suggest(c);
    expect(s.id).toBe("gentle-delay");
    expect(s.fix.set).toEqual([["fetch.min_delay", 1]]);
  });
  it("flags unbounded queues with many workers and honors dismissals", () => {
    const c = cfg();
    c.pipelines.filtering.workers = 16;
    c.pipelines.filtering.max_queue_size = null;
    expect(suggest(c).map((s) => s.id)).toContain("unbounded-queue");
    expect(suggest(c, ["unbounded-queue"])).toEqual([]);
  });
});

describe("presetChanges", () => {
  it("lists only values that differ", () => {
    const changes = presetChanges({ fetch: { min_delay: 2, jitter_max: defaults.fetch.jitter_max } }, defaults);
    expect(changes).toHaveLength(defaults.fetch.min_delay === 2 ? 0 : 1);
    expect(flatten({ a: { b: 1, c: [2] } })).toEqual([
      ["a.b", 1],
      ["a.c", [2]],
    ]);
  });
});
