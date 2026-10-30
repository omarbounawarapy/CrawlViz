import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

import { axeViolations, orphanLabels } from "../../../test/axe";
import { NumberField } from "../NumberField/NumberField";
import { Field, TextInput } from "./Field";

describe("Field", () => {
  it("names its control by the label and describes it by the hint and the error", () => {
    render(
      <Field label="Topic" hint="A short description of the subject." error="Enter a topic to crawl for.">
        {(control) => <TextInput {...control} />}
      </Field>,
    );
    const box = screen.getByRole("textbox", { name: "Topic" });
    const describedBy = (box.getAttribute("aria-describedby") ?? "").split(" ");
    expect(describedBy).toEqual([
      screen.getByText("A short description of the subject.").id,
      screen.getByText("Enter a topic to crawl for.").id,
    ]);
    expect(box.getAttribute("aria-invalid")).toBe("true");
  });

  it("leaves the control undescribed and valid when there is no hint or error", () => {
    render(<Field label="Topic">{(control) => <TextInput {...control} />}</Field>);
    const box = screen.getByRole("textbox", { name: "Topic" });
    expect(box.hasAttribute("aria-describedby")).toBe(false);
    expect(box.hasAttribute("aria-invalid")).toBe(false);
  });

  it("marks a required field in words and on the control", () => {
    render(
      <Field label="Seed page" required>
        {(control) => <TextInput {...control} type="url" />}
      </Field>,
    );
    const box = screen.getByRole("textbox", { name: /Seed page/ });
    expect((box as HTMLInputElement).required).toBe(true);
    expect(screen.getByText(/required/).textContent).toBe(" (required)");
  });

  it("keeps the id it is given", () => {
    render(
      <Field label="Topic" id="topic" hint="One line.">
        {(control) => <TextInput {...control} />}
      </Field>,
    );
    expect(screen.getByRole("textbox", { name: "Topic" }).id).toBe("topic");
    expect(screen.getByText("One line.").id).toBe("topic-hint");
  });

  it("joins its description with a number field's unit", () => {
    render(
      <Field label="Page limit" hint="The crawl stops after this many pages.">
        {(control) => <NumberField {...control} value={200} onChange={vi.fn()} unit="pages" integer />}
      </Field>,
    );
    const box = screen.getByRole("textbox", { name: "Page limit" });
    expect((box.getAttribute("aria-describedby") ?? "").split(" ")).toEqual([
      screen.getByText("The crawl stops after this many pages.").id,
      screen.getByText("pages").id,
    ]);
  });

  it("has no axe violations or orphan labels, valid or not", async () => {
    const { container } = render(
      <form>
        <Field label="Topic" hint="One line.">
          {(control) => <TextInput {...control} />}
        </Field>
        <Field label="Random seed" error="Enter a whole number, like 12." required>
          {(control) => <NumberField {...control} value={null} onChange={vi.fn()} integer nullable />}
        </Field>
      </form>,
    );
    expect(orphanLabels(container)).toEqual([]);
    expect(await axeViolations(container)).toEqual([]);
  });
});
