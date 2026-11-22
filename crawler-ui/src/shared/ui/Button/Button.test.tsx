import type { SyntheticEvent } from "react";
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { axeViolations } from "../../../test/axe";
import { Button } from "./Button";

describe("Button", () => {
  it("never submits the form it sits in unless asked to", () => {
    const onSubmit = vi.fn((event: SyntheticEvent) => {
      event.preventDefault();
    });
    render(
      <form onSubmit={onSubmit}>
        <Button>Add a seed page</Button>
        <Button type="submit" variant="primary">
          Start the crawl
        </Button>
      </form>,
    );
    const plain = screen.getByRole("button", { name: "Add a seed page" });
    expect(plain.getAttribute("type")).toBe("button");
    fireEvent.click(plain);
    expect(onSubmit).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Start the crawl" }));
    expect(onSubmit).toHaveBeenCalledTimes(1);
  });

  it("is a toggle only when pressed is given", () => {
    render(
      <>
        <Button>Fit</Button>
        <Button pressed>Measurements</Button>
        <Button pressed={false}>Slow</Button>
      </>,
    );
    expect(screen.getByRole("button", { name: "Fit" }).hasAttribute("aria-pressed")).toBe(false);
    expect(screen.getByRole("button", { name: "Measurements", pressed: true })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Slow", pressed: false })).toBeTruthy();
  });

  it("passes its handlers and disabled state through to the button", () => {
    const onClick = vi.fn();
    render(
      <Button variant="quiet" disabled onClick={onClick}>
        Remove
      </Button>,
    );
    const button = screen.getByRole("button", { name: "Remove" });
    fireEvent.click(button);
    expect(onClick).not.toHaveBeenCalled();
    expect((button as HTMLButtonElement).disabled).toBe(true);
  });

  it("has no axe violations in any variant", async () => {
    const { container } = render(
      <>
        <Button>Outline</Button>
        <Button variant="primary">Primary</Button>
        <Button variant="quiet">Quiet</Button>
        <Button pressed>Pressed</Button>
        <Button disabled>Disabled</Button>
      </>,
    );
    expect(await axeViolations(container)).toEqual([]);
  });
});
