import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import App from "./App";

// jsdom has no real WebSocket transport; this fake never connects, which is
// fine for a smoke test -- useCrawlStream should degrade to "CONNECTING"
// without throwing, exactly like a real socket that hasn't opened yet.
class FakeWebSocket {
  constructor() {
    this.readyState = 0;
  }
  close() {}
}

beforeEach(() => {
  window.location.hash = "";
  vi.stubGlobal("WebSocket", FakeWebSocket);
});

describe("App — smoke render", () => {
  it("lands on the graph with an empty state and the timeline dock", () => {
    render(<App />);
    expect(screen.getByRole("heading", { name: /No crawl on the plate yet/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Load a synthetic sample" })).toBeTruthy();
    expect(screen.getByLabelText("Replay position")).toBeTruthy();
    cleanup();
  });

  const pages = ["Run", "Blueprints", "Data", "Config", "Graph"];
  for (const label of pages) {
    it(`navigates to ${label} without throwing`, () => {
      render(<App />);
      fireEvent.click(screen.getByRole("button", { name: label }));
      expect(screen.getByRole("button", { name: label }).getAttribute("aria-current")).toBe("page");
      cleanup();
    });
  }

  it("Measurements drawer opens the overview and pipeline panels", () => {
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "Measurements" }));
    expect(screen.getByLabelText("Measurements")).toBeTruthy();
    expect(screen.getByText(/What is this crawl doing right now/)).toBeTruthy();
    cleanup();
  });

  it("the events list expands from the timeline dock", () => {
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "Show events" }));
    expect(screen.getByRole("button", { name: "Hide events" })).toBeTruthy();
    cleanup();
  });

  it("legacy #/overview links open the graph with the drawer", () => {
    window.location.hash = "#/overview";
    render(<App />);
    expect(screen.getByLabelText("Measurements")).toBeTruthy();
    cleanup();
  });
});
