// Behaviour behind the persona rerun findings (docs/config-persona-findings.md, rows 37-53).
import { describe, it, expect, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import defaults from "./fixtures/defaults.json";
import { changedSections, buildFields } from "./configModel";
import { presetChanges, changesMarkdown } from "./presetModel";
import { STAGE_NAMES, stageName } from "./pipelineNames";
import StrategyCards from "./explainers/StrategyCards";
import PolitenessCard from "./explainers/PolitenessCard";
import CostReadout from "./CostReadout";
import CascadeFunnel from "./explainers/CascadeFunnel";
import { weightTotal, topFiveSummary } from "./explainers/strategyModel";
import sample from "./explainers/sampleData.json";

afterEach(cleanup);

const fraction = {
  path: "scoring_cascade.high_score_llm_fraction",
  section: "Scoring cascade",
  widget: "slider",
  minimum: 0,
  maximum: 1,
  unit: "",
};
const minDelay = { path: "fetch.min_delay", section: "Fetch", widget: "number", unit: "s" };

describe("saved-state banner", () => {
  it("names each section with a changed field, in the order given", () => {
    const fields = [minDelay, fraction];
    const patch = { fetch: { min_delay: 2 }, scoring_cascade: { high_score_llm_fraction: 0.1 } };
    expect(changedSections(fields, patch, ["Scoring cascade", "Fetch"])).toEqual(["Scoring cascade", "Fetch"]);
    expect(changedSections(fields, { fetch: { min_delay: 2 } })).toEqual(["Fetch"]);
    expect(changedSections(fields, {})).toEqual([]);
  });
});

describe("preset and goal diffs", () => {
  it("shows a 0-1 fraction as a percentage, as the control draws it", () => {
    const [change] = presetChanges(
      { scoring_cascade: { high_score_llm_fraction: 0.1 } },
      { scoring_cascade: { high_score_llm_fraction: 0.3 } },
      [fraction],
    );
    expect(change.fromText).toBe("30 %");
    expect(change.toText).toBe("10 %");
  });

  it("shows the NLP and LLM biases as the one share slider they are", () => {
    const current = { priority: { nlp_bias: 60, llm_bias: 40 } };
    const changes = presetChanges({ priority: { nlp_bias: 85, llm_bias: 15 } }, current);
    expect(changes).toHaveLength(1);
    expect(changes[0].fromText).toBe("NLP 60 % · LLM 40 %");
    expect(changes[0].toText).toBe("NLP 85 % · LLM 15 %");
  });

  it("drops the share change when the ratio is unchanged", () => {
    const current = { priority: { nlp_bias: 60, llm_bias: 40 } };
    expect(presetChanges({ priority: { nlp_bias: 6, llm_bias: 4 } }, current)).toEqual([]);
  });

  it("names pipeline stages as the Pipelines table does", () => {
    const [change] = presetChanges(
      { pipelines: { requests: { workers: 2 } } },
      { pipelines: { requests: { workers: 4 } } },
    );
    expect(change.label).toBe("Pipelines › Fetch › Workers");
  });

  it("writes the same percentages into the Markdown export", () => {
    const md = changesMarkdown(
      { scoring_cascade: { high_score_llm_fraction: 0.1 } },
      { scoring_cascade: { high_score_llm_fraction: 0.3 } },
      "Exported",
      [fraction],
    );
    expect(md).toContain("default 30 %, changed to 10 %");
  });
});

describe("stage names", () => {
  it("gives the diagram and the table one name per stage", () => {
    expect(STAGE_NAMES.requests).toBe("Fetch");
    expect(stageName("priority")).toBe("Order queue");
    expect(stageName("unknown_stage")).toBe("unknown stage");
  });
});

describe("priority strategy cards", () => {
  const priority = defaults.priority;

  it("says when two strategies pick the same five links", () => {
    render(<StrategyCards priority={priority} defaults={priority} defaultStrategy="balanced" onChange={() => {}} />);
    const a = topFiveSummary(sample.strategyLinks, priority.aggressive_weights, priority.nlp_bias, priority.llm_bias);
    const b = topFiveSummary(sample.strategyLinks, priority.balanced_weights, priority.nlp_bias, priority.llm_bias);
    const same = a.labels.join("|") === b.labels.join("|");
    expect(screen.queryAllByText(/Same five links as/).length > 0).toBe(same);
  });

  it("shows the weights' total and that it is not divided by", () => {
    render(<StrategyCards priority={priority} defaults={priority} defaultStrategy="balanced" onChange={() => {}} />);
    expect(
      screen.getByText(new RegExp(`The weights add up to ${weightTotal(priority.balanced_weights).toFixed(2)}`)),
    ).toBeTruthy();
    expect(screen.getByText(/not divided by that total/)).toBeTruthy();
  });

  it("writes each feature's definition on the page, not in a tooltip", () => {
    render(<StrategyCards priority={priority} defaults={priority} defaultStrategy="balanced" onChange={() => {}} />);
    expect(screen.getByText("How unlike the pages already seen it is")).toBeTruthy();
    expect(screen.getByText(/Words shared by the link's anchor text/)).toBeTruthy();
  });

  it("gives the bars a scale", () => {
    render(<StrategyCards priority={priority} defaults={priority} defaultStrategy="balanced" onChange={() => {}} />);
    expect(screen.getByText(/longest bar/)).toBeTruthy();
  });
});

describe("cascade funnel", () => {
  it("names the middle band by what happens to it", () => {
    const cfg = defaults.scoring_cascade;
    render(<CascadeFunnel cfg={cfg} />);
    expect(screen.getAllByText("Middle band: always to the LLM").length).toBeGreaterThan(0);
    expect(screen.queryByText(/always asked/)).toBeNull();
  });
});

describe("cost readout", () => {
  const cfg = {
    scoring_cascade: defaults.scoring_cascade,
    nlp: defaults.nlp,
    llm: defaults.llm,
    prompts: defaults.prompts,
  };

  it("gives tokens for a whole crawl and says what a token is", () => {
    render(<CostReadout cascade={cfg.scoring_cascade} nlp={cfg.nlp} llm={cfg.llm} prompts={cfg.prompts} priced />);
    expect(screen.getByText(/about four characters of English text/)).toBeTruthy();
    expect(screen.getByText(/and about [\d,]+ tokens/)).toBeTruthy();
  });

  it("has no dollar figure until a price is typed", () => {
    render(<CostReadout cascade={cfg.scoring_cascade} nlp={cfg.nlp} llm={cfg.llm} prompts={cfg.prompts} priced />);
    expect(screen.queryByText(/at the price you typed/)).toBeNull();
  });
});

describe("politeness card", () => {
  it("says it reads the draft and gives the time a 100-page crawl takes", () => {
    render(<PolitenessCard cfg={defaults.fetch} workers={4} maxRetries={3} latency={0.3} />);
    expect(screen.getByText(/Uses your draft, including values you have not saved yet/)).toBeTruthy();
    expect(screen.getByText(/A crawl of 100 pages takes at least [\d.]+ minutes at this pace/)).toBeTruthy();
  });
});

describe("the all-advanced section", () => {
  it("is named as advanced rather than empty", async () => {
    const { default: SettingsEditor } = await import("./SettingsEditor");
    const schema = (await import("./fixtures/schema.json")).default;
    const fields = buildFields(schema).map((f) => ({ ...f, advanced: true }));
    render(
      <SettingsEditor
        fields={fields}
        draft={defaults}
        defaults={defaults}
        saved={defaults}
        onChange={() => {}}
        section={fields[0].section}
        sectionOrder={[]}
      />,
    );
    expect(screen.getByText(new RegExp(`Every setting in ${fields[0].section} is advanced`))).toBeTruthy();
  });
});
