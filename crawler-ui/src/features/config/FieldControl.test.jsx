import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import FieldControl from "./FieldControl";

const NUMBER = { widget: "number", title: "Min delay", ariaLabel: "Min delay", type: "number", unit: "s" };

function setup(field, value) {
  const onChange = vi.fn();
  render(<FieldControl field={field} value={value} onChange={onChange} id="f" describedBy="why" />);
  return { onChange, box: screen.getByRole("textbox", { name: field.ariaLabel ?? `${field.title}` }) };
}

describe("FieldControl number box", () => {
  it("reports a typed number, reads the comma as a decimal mark, and shows the unit", () => {
    const { onChange, box } = setup(NUMBER, 1);
    fireEvent.change(box, { target: { value: "0,3" } });
    expect(onChange).toHaveBeenLastCalledWith(0.3);
    expect(screen.getByText("s")).toBeTruthy();
    expect(box.getAttribute("aria-describedby")).toContain("why");
  });

  it("reports an empty box as an empty string for a field that needs a value", () => {
    const { onChange, box } = setup(NUMBER, 1);
    fireEvent.change(box, { target: { value: "" } });
    expect(onChange).toHaveBeenLastCalledWith("");
  });

  it("reports an empty box as null for a nullable field", () => {
    const { onChange, box } = setup({ ...NUMBER, nullable: true }, 1);
    fireEvent.change(box, { target: { value: "" } });
    expect(onChange).toHaveBeenLastCalledWith(null);
  });

  it("shows an empty value as an empty box", () => {
    const { box } = setup(NUMBER, "");
    expect(box.value).toBe("");
  });

  it("does not report text that is not a number, and says what to type", () => {
    const { onChange, box } = setup({ ...NUMBER, type: "integer" }, 4);
    fireEvent.change(box, { target: { value: "abc" } });
    expect(onChange).not.toHaveBeenCalled();
    expect(box.getAttribute("aria-invalid")).toBe("true");
    expect(screen.getByText("Enter a whole number, like 12.")).toBeTruthy();
  });
});

describe("FieldControl percentage slider", () => {
  const FRACTION = { widget: "slider", title: "Threshold", type: "number", minimum: 0, maximum: 1 };

  it("types a percentage and stores the fraction", () => {
    const onChange = vi.fn();
    render(<FieldControl field={FRACTION} value={0.25} onChange={onChange} id="f" />);
    const box = screen.getByRole("textbox");
    expect(box.value).toBe("25");
    fireEvent.change(box, { target: { value: "40" } });
    expect(onChange).toHaveBeenLastCalledWith(0.4);
  });

  it("lets the box be emptied to retype, without snapping back to 0", () => {
    const onChange = vi.fn();
    const { rerender } = render(<FieldControl field={FRACTION} value={0.25} onChange={onChange} id="f" />);
    const box = screen.getByRole("textbox");
    fireEvent.change(box, { target: { value: "" } });
    expect(onChange).toHaveBeenLastCalledWith("");
    rerender(<FieldControl field={FRACTION} value="" onChange={onChange} id="f" />);
    expect(screen.getByRole("textbox").value).toBe("");
  });
});
