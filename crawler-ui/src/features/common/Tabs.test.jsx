import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { Tabs } from "./Form";

const OPTIONS = [
  ["a", "Alpha"],
  ["b", "Beta"],
  ["c", "Gamma"],
];

function renderTabs(value = "a") {
  const onChange = vi.fn();
  render(<Tabs id="t" label="Letters" value={value} options={OPTIONS} onChange={onChange} />);
  return onChange;
}

describe("Tabs", () => {
  it("moves to the next tab with ArrowRight and focuses it", () => {
    const onChange = renderTabs("a");
    fireEvent.keyDown(screen.getByRole("tab", { name: "Alpha" }), { key: "ArrowRight" });
    expect(onChange).toHaveBeenCalledWith("b");
    expect(document.activeElement).toBe(screen.getByRole("tab", { name: "Beta" }));
  });

  it("wraps from the first tab to the last with ArrowLeft", () => {
    const onChange = renderTabs("a");
    fireEvent.keyDown(screen.getByRole("tab", { name: "Alpha" }), { key: "ArrowLeft" });
    expect(onChange).toHaveBeenCalledWith("c");
  });

  it("ignores other keys and keeps only the selected tab in the tab order", () => {
    const onChange = renderTabs("b");
    fireEvent.keyDown(screen.getByRole("tab", { name: "Beta" }), { key: "Enter" });
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByRole("tab", { name: "Beta" }).getAttribute("tabindex")).toBe("0");
    expect(screen.getByRole("tab", { name: "Alpha" }).getAttribute("tabindex")).toBe("-1");
  });
});
