import { useState } from "react";
import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import FormNumberField from "./FormNumberField";

function Form({ initial }) {
  const [value, setValue] = useState(initial);
  return (
    <>
      <FormNumberField aria-label="Max pages" value={value} onChange={setValue} />
      <output data-testid="stored">{JSON.stringify(value)}</output>
    </>
  );
}

describe("FormNumberField", () => {
  it("stores what is typed as text", () => {
    render(<Form initial="120" />);
    fireEvent.change(screen.getByRole("textbox", { name: "Max pages" }), { target: { value: "45" } });
    expect(screen.getByTestId("stored").textContent).toBe('"45"');
  });

  it("stores an empty box as empty text, so the form's validation can ask for a value", () => {
    render(<Form initial={120} />);
    fireEvent.change(screen.getByRole("textbox", { name: "Max pages" }), { target: { value: "" } });
    expect(screen.getByTestId("stored").textContent).toBe('""');
  });

  it("asks for a whole number and keeps the last good value stored", () => {
    render(<Form initial="5" />);
    const box = screen.getByRole("textbox", { name: "Max pages" });
    fireEvent.change(box, { target: { value: "2.5" } });
    expect(screen.getByText("Enter a whole number, like 12.")).toBeTruthy();
    expect(box.value).toBe("2.5");
    expect(screen.getByTestId("stored").textContent).toBe('"5"');
  });

  it("shows a stored value as a number, and a missing or non-numeric one as an empty box", () => {
    const { rerender } = render(<FormNumberField aria-label="Max pages" value={120} onChange={() => {}} />);
    expect(screen.getByRole("textbox", { name: "Max pages" }).value).toBe("120");
    rerender(<FormNumberField aria-label="Max pages" value="abc" onChange={() => {}} />);
    expect(screen.getByRole("textbox", { name: "Max pages" }).value).toBe("");
  });

  it("keeps a typed number as typed while the form stores it as text", () => {
    render(<Form initial="" />);
    const box = screen.getByRole("textbox", { name: "Max pages" });
    fireEvent.change(box, { target: { value: "007" } });
    expect(box.value).toBe("007");
    expect(screen.getByTestId("stored").textContent).toBe('"7"');
  });
});
