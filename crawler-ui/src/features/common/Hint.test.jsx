import { describe, it, expect, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { Hint } from "./Hint";

afterEach(cleanup);

describe("Hint", () => {
  it("opens from the keyboard and closes on Escape", () => {
    render(
      <Hint text="Explained.">
        <span>Term</span>
      </Hint>,
    );
    const trigger = screen.getByRole("button", { name: "Term" });
    fireEvent.focus(trigger);
    expect(screen.getByRole("tooltip").textContent).toBe("Explained.");
    expect(trigger.getAttribute("aria-describedby")).toBe(screen.getByRole("tooltip").id);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("tooltip")).toBeNull();
  });

  it("toggles on click, which is how touch reaches it", () => {
    render(
      <Hint text="Explained.">
        <span>Term</span>
      </Hint>,
    );
    const trigger = screen.getByRole("button", { name: "Term" });
    fireEvent.click(trigger);
    expect(screen.getByRole("tooltip").textContent).toBe("Explained.");
    fireEvent.click(trigger);
    expect(screen.queryByRole("tooltip")).toBeNull();
  });
});
