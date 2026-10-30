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

  it("reads an empty box as null and rejects words", () => {
    expect(parseNumberText("  ")).toEqual({ ok: true, value: null });
    expect(parseNumberText("ten")).toEqual({ ok: false });
    expect(parseNumberText("1e999")).toEqual({ ok: false });
  });
});

function Controlled({ initial, onChange, ...props }: { initial: number | null; onChange: (v: number | null) => void; integer?: boolean; nullable?: boolean }) {
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

  it("is described by its unit", () => {
    render(<Controlled initial={5} onChange={vi.fn()} />);
    const describedBy = screen.getByRole("textbox", { name: "Pages" }).getAttribute("aria-describedby") ?? "";
    expect(describedBy).toBe(screen.getByText("pages").id);
  });
});
