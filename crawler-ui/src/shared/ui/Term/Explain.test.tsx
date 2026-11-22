import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { axeViolations } from "../../../test/axe";
import { Explain } from "./Explain";
import type { GlossaryDefinitions } from "./glossaryContext";
import { GlossaryProvider } from "./Term";

const DEFINITIONS = {
  "top-k": "The k closest reference vectors to a link.",
  top: "Not the same thing.",
  backoff: "The pause after too many requests.",
  seed: "The number that starts a random sequence.",
  "robots.txt": "A file that says what crawlers may fetch.",
};

function renderInGlossary(children: ReactNode, definitions: GlossaryDefinitions = DEFINITIONS) {
  return render(
    <GlossaryProvider definitions={definitions}>
      <p>{children}</p>
    </GlossaryProvider>,
  );
}

/** The text a reader sees: the prose without the explanations the Terms keep in the DOM. */
function shownText(container: HTMLElement): string {
  const copy = container.cloneNode(true) as HTMLElement;
  copy.querySelectorAll('[role="tooltip"]').forEach((explanation) => {
    explanation.remove();
  });
  return copy.textContent;
}

describe("Explain", () => {
  it("wraps glossary words in explainable buttons and keeps the rest of the text", () => {
    const { container } = renderInGlossary(<Explain text="The backoff grows after each 429." />);
    const trigger = screen.getByRole("button", { name: "backoff" });
    fireEvent.focus(trigger);
    expect(screen.getByRole("tooltip").textContent).toBe(DEFINITIONS.backoff);
    expect(shownText(container)).toBe("The backoff grows after each 429.");
  });

  it("finds a word whatever its case and shows it as written", () => {
    renderInGlossary(<Explain text="Backoff comes first." />);
    fireEvent.focus(screen.getByRole("button", { name: "Backoff" }));
    expect(screen.getByRole("tooltip").textContent).toBe(DEFINITIONS.backoff);
  });

  it("prefers the longer term and leaves words inside longer words alone", () => {
    renderInGlossary(<Explain text="Keep the top-k matches, not the top ones. Seeds differ." />);
    expect(screen.getByRole("button", { name: "top-k" })).toBeTruthy();
    // "top" alone is explained once, in "the top ones"; it is not split out of "top-k".
    expect(screen.getAllByRole("button", { name: "top" })).toHaveLength(1);
    expect(screen.queryByRole("button", { name: /seed/i })).toBeNull();
  });

  it("treats letters outside ASCII as part of a word", () => {
    renderInGlossary(<Explain text="Not topé, but top." />);
    expect(screen.getAllByRole("button")).toHaveLength(1);
    expect(screen.getByRole("button", { name: "top" })).toBeTruthy();
  });

  it("matches terms that contain punctuation, and only literally", () => {
    renderInGlossary(<Explain text="Honors robots.txt before fetching robotsXtxt." />);
    expect(screen.getAllByRole("button")).toHaveLength(1);
    expect(screen.getByRole("button", { name: "robots.txt" })).toBeTruthy();
  });

  it("is plain text when the glossary is empty or not provided", () => {
    renderInGlossary(<Explain text="The backoff grows." />, {});
    render(
      <p>
        <Explain text="The backoff also grows." />
      </p>,
    );
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.getByText("The backoff grows.")).toBeTruthy();
    expect(screen.getByText("The backoff also grows.")).toBeTruthy();
  });

  it("ignores a blank glossary word", () => {
    // An empty word would match between any two marks, here between "." and the space.
    const { container } = renderInGlossary(<Explain text="The backoff grows. It resets." />, {
      "": "Nothing.",
      backoff: DEFINITIONS.backoff,
    });
    expect(screen.getAllByRole("button")).toHaveLength(1);
    expect(shownText(container)).toBe("The backoff grows. It resets.");
  });

  it("renders nothing for empty text", () => {
    const { container } = renderInGlossary(<Explain text="" />);
    expect(container.querySelector("p")?.childNodes).toHaveLength(0);
  });

  it("has no axe violations, closed or open", async () => {
    const { container } = renderInGlossary(<Explain text="The backoff grows after each 429, honoring robots.txt." />);
    expect(await axeViolations(container)).toEqual([]);
    fireEvent.focus(screen.getByRole("button", { name: "robots.txt" }));
    expect(await axeViolations(container)).toEqual([]);
  });
});
