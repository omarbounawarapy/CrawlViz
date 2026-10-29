import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import PromptStudio from "./PromptStudio";
import { lineDiff, estimateTokens } from "./promptModel";

const defaults = {
  scoring_system: "SYS",
  scoring_rules: "RULES",
  strategy_contexts: { TOPICAL: "stay", EXPLORATION: "roam" },
};
const blocks = [
  { id: "system", title: "System prompt", kind: "editable", note: "n", text: "SYS" },
  { id: "output", title: "Output format", kind: "locked", note: "Parser reads this JSON shape.", text: "OUT" },
];
const preview = () => Promise.resolve({ blocks, prompt: "SYS\n\nOUT" });

describe("promptModel", () => {
  it("diffs by line", () => {
    expect(lineDiff("a\nb", "a\nc").map((l) => l.kind)).toEqual(["same", "del", "add"]);
    expect(estimateTokens("12345678")).toBe(2);
  });
});

describe("PromptStudio", () => {
  it("edits, restores, switches strategy and lists locked parts", async () => {
    const onChange = vi.fn();
    const prompts = { ...defaults, scoring_system: "CHANGED" };
    render(<PromptStudio prompts={prompts} defaults={defaults} onChange={onChange} preview={preview} />);
    fireEvent.change(screen.getByLabelText("System prompt"), { target: { value: "X" } });
    expect(onChange).toHaveBeenCalledWith("prompts.scoring_system", "X");
    fireEvent.click(screen.getByRole("button", { name: "Restore built-in System prompt" }));
    expect(onChange).toHaveBeenCalledWith("prompts.scoring_system", "SYS");
    fireEvent.click(screen.getByRole("tab", { name: "exploration" }));
    expect(screen.getByLabelText("Wording for the exploration focus").value).toBe("roam");
    await waitFor(() => expect(screen.getByText(/Parser reads this JSON shape/)).toBeTruthy());
  });
});
