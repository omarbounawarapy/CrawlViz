import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup, waitFor, act } from "@testing-library/react";
import GoalGuide from "./GoalGuide";
import GlossaryScope from "./GlossaryScope";
import { primeGlossary, resetGlossaryForTests } from "./glossary";

const goals = {
  gentler: {
    label: "Gentler on a site",
    description: "Waits longer between requests.",
    values: { fetch: { min_delay: 2, jitter_max: 0.5 } },
  },
  cheaper: {
    label: "Cheaper",
    description: "Spends less on the LLM.",
    values: { scoring_cascade: { high_score_llm_fraction: 0.1 } },
  },
};

vi.mock("../../api/client", () => ({
  fetchPresets: vi.fn(() => Promise.resolve({ builtin: {}, user: {}, goals })),
  saveConfig: vi.fn(),
  fetchConfigSchema: vi.fn(() => Promise.resolve({ ui_glossary: {} })),
}));

import * as api from "../../api/client";

afterEach(() => {
  cleanup();
  resetGlossaryForTests();
});

const draft = { fetch: { min_delay: 1, jitter_max: 0.2 }, scoring_cascade: { high_score_llm_fraction: 0.3 } };

describe("GoalGuide", () => {
  it("previews the settings a goal would change against the draft", async () => {
    render(<GoalGuide draft={draft} onChange={() => {}} />);
    fireEvent.click(await screen.findByRole("button", { name: /Show the 2 settings it changes/ }));
    expect(screen.getByText(/Min delay/)).toBeTruthy();
    expect(screen.getByText(/Jitter max/)).toBeTruthy();
  });

  it("applies the goal to the draft without saving", async () => {
    const onChange = vi.fn();
    render(<GoalGuide draft={draft} onChange={onChange} />);
    const cards = await screen.findAllByRole("button", { name: "Apply to draft" });
    fireEvent.click(cards[0]);
    expect(onChange).toHaveBeenCalledWith("fetch.min_delay", 2);
    expect(onChange).toHaveBeenCalledWith("fetch.jitter_max", 0.5);
    expect(api.saveConfig).not.toHaveBeenCalled();
  });

  it("says so when the draft already matches a goal", async () => {
    const matching = { fetch: { min_delay: 2, jitter_max: 0.5 }, scoring_cascade: { high_score_llm_fraction: 0.1 } };
    render(<GoalGuide draft={matching} onChange={() => {}} />);
    await waitFor(() => expect(screen.getAllByText("Your draft already matches this.")).toHaveLength(2));
  });

  it("explains the glossary words in a goal's description", async () => {
    act(() => primeGlossary({ requests: "Page fetches the crawler makes." }));
    render(
      <GlossaryScope>
        <GoalGuide draft={draft} onChange={() => {}} />
      </GlossaryScope>,
    );
    expect(await screen.findByRole("button", { name: "requests" })).toBeTruthy();
  });
});
