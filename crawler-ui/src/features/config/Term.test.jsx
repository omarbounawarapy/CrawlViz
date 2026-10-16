import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup, act } from "@testing-library/react";
import { Explain } from "./Term";
import { Hint } from "../common/Hint";
import { primeGlossary, resetGlossaryForTests } from "./glossary";

const GLOSSARY = {
  "top-k": "The k closest reference vectors to a link.",
  top: "Not the same thing.",
  backoff: "The pause after too many requests.",
  seed: "The number that starts a random sequence.",
  "robots.txt": "A file that says what crawlers may fetch.",
};

beforeEach(() => { act(() => primeGlossary(GLOSSARY)); });
afterEach(() => { cleanup(); resetGlossaryForTests(); });

describe("Explain", () => {
  it("wraps glossary words in explainable buttons", () => {
    render(<p><Explain text="The backoff grows after each 429." /></p>);
    expect(screen.getByRole("button", { name: "backoff" })).toBeTruthy();
  });

  it("prefers the longer term and leaves words inside longer words alone", () => {
    render(<p><Explain text="Keep the top-k matches, not the top ones. Seeds differ." /></p>);
    expect(screen.getByRole("button", { name: "top-k" })).toBeTruthy();
    // "top" alone is explained once, in "the top ones"; it is not split out of "top-k".
    expect(screen.getAllByRole("button", { name: "top" })).toHaveLength(1);
    expect(screen.queryByRole("button", { name: "seed" })).toBeNull();
  });

  it("matches terms that contain punctuation", () => {
    render(<p><Explain text="Honors robots.txt before fetching." /></p>);
    expect(screen.getByRole("button", { name: "robots.txt" })).toBeTruthy();
  });

  it("returns plain text when the glossary is not loaded", () => {
    act(() => resetGlossaryForTests());
    render(<p><Explain text="The backoff grows." /></p>);
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.getByText("The backoff grows.")).toBeTruthy();
  });
});

describe("Hint", () => {
  it("opens from the keyboard and closes on Escape", () => {
    render(<Hint text="Explained."><span>Term</span></Hint>);
    const trigger = screen.getByRole("button", { name: "Term" });
    fireEvent.focus(trigger);
    expect(screen.getByRole("tooltip").textContent).toBe("Explained.");
    expect(trigger.getAttribute("aria-describedby")).toBe(screen.getByRole("tooltip").id);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("tooltip")).toBeNull();
  });

  it("toggles on click, which is how touch reaches it", () => {
    render(<Hint text="Explained."><span>Term</span></Hint>);
    const trigger = screen.getByRole("button", { name: "Term" });
    fireEvent.click(trigger);
    expect(screen.getByRole("tooltip").textContent).toBe("Explained.");
    fireEvent.click(trigger);
    expect(screen.queryByRole("tooltip")).toBeNull();
  });
});
