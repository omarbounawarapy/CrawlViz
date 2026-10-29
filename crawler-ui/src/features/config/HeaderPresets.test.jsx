import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import HeaderPresets from "./HeaderPresets";
import SettingsEditor from "./SettingsEditor";
import { HEADER_PRESETS, activePreset } from "./headerPresets";

afterEach(cleanup);

describe("header sets", () => {
  it("previews every header field the chosen set would change before applying it", () => {
    const onApply = vi.fn();
    render(<HeaderPresets fetch={{}} onApply={onApply} />);
    fireEvent.click(screen.getByRole("radio", { name: /Desktop Firefox/ }));
    expect(onApply).not.toHaveBeenCalled();
    const preview = screen.getByRole("region", { name: /Preview of Desktop Firefox/ });
    expect(preview.textContent).toMatch(/changes \d+ fields?/);
    fireEvent.click(screen.getByRole("button", { name: "Apply to draft" }));
    expect(onApply).toHaveBeenCalledWith(HEADER_PRESETS[2].values);
  });
  it("cancels a preview without touching the draft", () => {
    const onApply = vi.fn();
    render(<HeaderPresets fetch={{}} onApply={onApply} />);
    fireEvent.click(screen.getByRole("radio", { name: /Desktop Firefox/ }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("region", { name: /Preview/ })).toBeNull();
    expect(onApply).not.toHaveBeenCalled();
  });
  it("marks the set the fields currently hold", () => {
    expect(activePreset(HEADER_PRESETS[1].values).name).toBe("Desktop Chrome");
    expect(activePreset({ ...HEADER_PRESETS[1].values, accept_language: "fr" })).toBeNull();
  });
});

describe("NLP/LLM split", () => {
  const f = (key, other) => ({
    path: `priority.${key}`,
    key,
    topKey: "priority",
    title: key,
    description: "",
    widget: "split",
    pair: other,
    type: "number",
    nullable: false,
    section: "Priority",
    apply: "next_run",
    advanced: false,
    minimum: 0,
  });
  const fields = [f("nlp_bias", "llm_bias"), f("llm_bias", "nlp_bias")];
  const draft = { priority: { nlp_bias: 60, llm_bias: 40 } };

  it("moves both weights so they add up to 100", () => {
    const onChange = vi.fn();
    render(<SettingsEditor fields={fields} draft={draft} defaults={draft} saved={draft} onChange={onChange} />);
    const slider = screen.getByRole("slider");
    expect(slider.value).toBe("40");
    fireEvent.change(slider, { target: { value: "75" } });
    expect(onChange).toHaveBeenCalledWith("priority.nlp_bias", 25);
    expect(onChange).toHaveBeenCalledWith("priority.llm_bias", 75);
  });
});
