import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { axeViolations } from "../../../test/axe";
import { GlossaryProvider, Term } from "./Term";

const DEFINITIONS = {
  "seed page": "A page the crawl starts from. A blueprint lists one or more.",
  backoff: "The pause the crawler takes after a site answers with too many requests.",
};

function renderInGlossary(children: ReactNode) {
  return render(
    <GlossaryProvider definitions={DEFINITIONS}>
      <p>{children}</p>
    </GlossaryProvider>,
  );
}

describe("Term", () => {
  it("finds its definition whatever the case, and shows its own words", () => {
    renderInGlossary(<Term term="Seed page">seed pages</Term>);
    const trigger = screen.getByRole("button", { name: "seed pages" });
    expect(trigger.getAttribute("aria-describedby")).toBe(screen.getByRole("tooltip", { hidden: true }).id);
    expect(screen.queryByRole("tooltip")).toBeNull();
  });

  it("is plain text when the glossary lacks the word or is not provided", () => {
    render(
      <p>
        <Term term="backoff" />
      </p>,
    );
    renderInGlossary(<Term term="jitter">some jitter</Term>);
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.getByText("backoff")).toBeTruthy();
    expect(screen.getByText("some jitter")).toBeTruthy();
  });

  it("opens on focus and closes on Escape and on blur", () => {
    renderInGlossary(<Term term="backoff" />);
    const trigger = screen.getByRole("button", { name: "backoff" });
    fireEvent.focus(trigger);
    expect(screen.getByRole("tooltip").textContent).toBe(DEFINITIONS.backoff);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("tooltip")).toBeNull();
    fireEvent.focus(trigger);
    fireEvent.blur(trigger);
    expect(screen.queryByRole("tooltip")).toBeNull();
  });

  it("stays open through a tap's hover, focus and click, and closes on a press elsewhere", () => {
    renderInGlossary(<Term term="backoff" />);
    const trigger = screen.getByRole("button", { name: "backoff" });
    fireEvent.mouseEnter(trigger);
    fireEvent.focus(trigger);
    fireEvent.click(trigger);
    expect(screen.getByRole("tooltip").textContent).toBe(DEFINITIONS.backoff);
    fireEvent.pointerDown(screen.getByRole("tooltip"));
    expect(screen.getByRole("tooltip")).toBeTruthy();
    fireEvent.pointerDown(document.body);
    expect(screen.queryByRole("tooltip")).toBeNull();
  });

  it("opens on hover and closes when the pointer leaves", () => {
    renderInGlossary(<Term term="backoff" />);
    const trigger = screen.getByRole("button", { name: "backoff" });
    fireEvent.mouseEnter(trigger);
    expect(screen.getByRole("tooltip")).toBeTruthy();
    fireEvent.mouseLeave(trigger);
    expect(screen.queryByRole("tooltip")).toBeNull();
  });

  it("has no axe violations, closed or open", async () => {
    const { container } = renderInGlossary(
      <>
        A crawl starts from its <Term term="seed page" /> and slows by its <Term term="backoff" />.
      </>,
    );
    expect(await axeViolations(container)).toEqual([]);
    fireEvent.focus(screen.getByRole("button", { name: "backoff" }));
    expect(await axeViolations(container)).toEqual([]);
  });
});
