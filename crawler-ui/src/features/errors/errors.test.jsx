import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import ErrorBoundary from "./ErrorBoundary";
import NotFoundPage from "./NotFoundPage";

describe("error screens", () => {
  it("shows a recoverable screen instead of a blank page", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const Boom = () => { throw new Error("kaboom"); };
    render(<ErrorBoundary><Boom /></ErrorBoundary>);
    expect(screen.getByRole("alert").textContent).toMatch(/Something went wrong/);
    expect(screen.getByText("kaboom")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Reload" })).toBeTruthy();
  });

  it("names the missing address and offers a way back", () => {
    render(<NotFoundPage route="nope" onNavigate={() => {}} />);
    expect(screen.getByText(/#\/nope/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Go to the graph" })).toBeTruthy();
  });
});
