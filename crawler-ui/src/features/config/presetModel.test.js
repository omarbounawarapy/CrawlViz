import { describe, it, expect } from "vitest";
import { changesMarkdown } from "./presetModel";
import defaults from "./fixtures/defaults.json";

const cfg = (patch = {}) => JSON.parse(JSON.stringify({ ...defaults, ...patch }));

describe("changesMarkdown", () => {
  it("says so when nothing differs from the defaults", () => {
    const md = changesMarkdown(cfg(), defaults, "Exported 2026-10-16");
    expect(md).toContain("# Settings changed from defaults");
    expect(md).toContain("No setting differs from the built-in defaults.");
    expect(md).not.toContain("- ");
  });

  it("lists each changed setting with its default, grouped by section", () => {
    const current = cfg({ fetch: { ...defaults.fetch, min_delay: 2 } });
    const md = changesMarkdown(current, defaults, "Exported 2026-10-16");
    expect(md).toContain("One setting differs from the built-in defaults.");
    expect(md).toContain("## Fetch\n\n- Min delay: default 1, changed to 2");
  });

  it("counts several changes in the summary line", () => {
    const current = cfg({ fetch: { ...defaults.fetch, min_delay: 2, jitter_max: 9 } });
    const md = changesMarkdown(current, defaults, "Exported 2026-10-16");
    expect(md).toContain("2 settings differ from the built-in defaults.");
  });
});
