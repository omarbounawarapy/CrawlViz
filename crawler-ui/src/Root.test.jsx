import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import Root from "./Root.jsx";

describe("Root", () => {
  beforeEach(() => {
    window.location.hash = "#/";
    sessionStorage.clear();
  });

  it("plays the spider loader once per session, and it can be skipped", () => {
    render(<Root />);
    expect(screen.getByRole("status", { name: /loading crawlviz/i })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /skip/i }));
  });

  it("shows the landing page headline and both calls to action", () => {
    sessionStorage.setItem("crawlviz:boot-seen", "1");
    render(<Root />);
    expect(screen.getByRole("heading", { level: 1 }).textContent).toMatch(/links worth following/i);
    expect(screen.getAllByRole("link", { name: /open the plate/i }).length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: /load a sample replay/i })).toBeTruthy();
  });

  it("does not navigate away when an in-page nav link is used", () => {
    sessionStorage.setItem("crawlviz:boot-seen", "1");
    render(<Root />);
    fireEvent.click(screen.getByRole("link", { name: /^limits$/i }));
    expect(window.location.hash).toBe("#/");
  });
});
