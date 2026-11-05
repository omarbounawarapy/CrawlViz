import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { NumberField } from "./NumberField";
import { parseNumberText } from "./parseNumberText";

describe("parseNumberText", () => {
  it("reads a dot or a comma as the decimal mark", () => {
    expect(parseNumberText("0.3")).toEqual({ ok: true, value: 0.3 });
    expect(parseNumberText("0,3")).toEqual({ ok: true, value: 0.3 });
  });

  it("reads a comma as a thousands separator when a dot is present", () => {
    expect(parseNumberText("1,000.5")).toEqual({ ok: true, value: 1000.5 });
  });

  it("rejects text with more than one decimal mark", () => {
    expect(parseNumberText("1.2.3").ok).toBe(false);
    expect(parseNumberText("0,3,1").ok).toBe(false);
  });

  it("reads a trailing dot while typing as the number so far", () => {
    expect(parseNumberText("2.")).toEqual({ ok: true, value: 2 });
  });

  it("reads an empty box as null and rejects words", () => {
    expect(parseNumberText("  ")).toEqual({ ok: true, value: null });
    expect(parseNumberText("ten")).toEqual({ ok: false });
    expect(parseNumberText("1e999")).toEqual({ ok: false });
  });
});

function Controlled({
  initial,
  onChange,
  ...props
}: {
  initial: number | null;
  onChange: (v: number | null) => void;
  integer?: boolean;
  nullable?: boolean;
}) {
  const [value, setValue] = useState(initial);
  return (
    <NumberField
      aria-label="Pages"
      unit="pages"
      value={value}
      onChange={(next) => {
        setValue(next);
        onChange(next);
      }}
      {...props}
    />
  );
}

describe("NumberField", () => {
  it("emits a number only when the text parses", () => {
    const onChange = vi.fn();
    render(<Controlled initial={5} onChange={onChange} />);
    const box = screen.getByRole("textbox", { name: "Pages" });
    fireEvent.change(box, { target: { value: "1,5" } });
    expect(onChange).toHaveBeenLastCalledWith(1.5);
    fireEvent.change(box, { target: { value: "1,5x" } });
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(box.getAttribute("aria-invalid")).toBe("true");
    expect(screen.getByText("Enter a number, like 0.5.").id).toBeTruthy();
  });

  it("keeps text that is not a number after blur, so it can be fixed", () => {
    render(<Controlled initial={5} onChange={vi.fn()} />);
    const box = screen.getByRole("textbox", { name: "Pages" });
    fireEvent.change(box, { target: { value: "five" } });
    fireEvent.blur(box);
    expect((box as HTMLInputElement).value).toBe("five");
  });

  it("asks for a whole number when integer, and for a number when empty and not nullable", () => {
    const onChange = vi.fn();
    render(<Controlled initial={5} onChange={onChange} integer />);
    const box = screen.getByRole("textbox", { name: "Pages" });
    fireEvent.change(box, { target: { value: "2.5" } });
    fireEvent.change(box, { target: { value: "" } });
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByText("Enter a whole number, like 12.").id).toBeTruthy();
  });

  it("emits null for an empty nullable box", () => {
    const onChange = vi.fn();
    render(<Controlled initial={5} onChange={onChange} nullable />);
    fireEvent.change(screen.getByRole("textbox", { name: "Pages" }), { target: { value: "" } });
    expect(onChange).toHaveBeenLastCalledWith(null);
  });

  it("keeps a trailing dot while typing, so a decimal can be finished", () => {
    render(<Controlled initial={1} onChange={vi.fn()} />);
    const box = screen.getByRole("textbox", { name: "Pages" });
    fireEvent.change(box, { target: { value: "0." } });
    expect((box as HTMLInputElement).value).toBe("0.");
    fireEvent.blur(box);
    expect((box as HTMLInputElement).value).toBe("0");
  });

  it("shows a stored number with dot decimals, and an outside change replaces the text", () => {
    const { rerender } = render(<NumberField aria-label="Pages" value={0.25} onChange={vi.fn()} />);
    const box = screen.getByRole<HTMLInputElement>("textbox", { name: "Pages" });
    expect(box.value).toBe("0.25");
    rerender(<NumberField aria-label="Pages" value={null} onChange={vi.fn()} />);
    expect(box.value).toBe("");
  });

  it("is invalid when the caller says so, and reads the caller's description before its own", () => {
    render(
      <>
        <p id="why">Why</p>
        <NumberField aria-label="Pages" value={5} invalid aria-describedby="why" unit="pages" onChange={vi.fn()} />
      </>,
    );
    const box = screen.getByRole("textbox", { name: "Pages" });
    expect(box.getAttribute("aria-invalid")).toBe("true");
    expect(box.getAttribute("aria-describedby")).toBe(`why ${screen.getByText("pages").id}`);
  });

  it("names the problem for the box after the unit, so a screen reader reads the sentence last", () => {
    render(<Controlled initial={5} onChange={vi.fn()} />);
    const box = screen.getByRole("textbox", { name: "Pages" });
    fireEvent.change(box, { target: { value: "abc" } });
    const ids = (box.getAttribute("aria-describedby") ?? "").split(" ");
    expect(ids).toEqual([screen.getByText("pages").id, screen.getByText("Enter a number, like 0.5.").id]);
  });

  it("is described by its unit", () => {
    render(<Controlled initial={5} onChange={vi.fn()} />);
    const describedBy = screen.getByRole("textbox", { name: "Pages" }).getAttribute("aria-describedby") ?? "";
    expect(describedBy).toBe(screen.getByText("pages").id);
  });
});
