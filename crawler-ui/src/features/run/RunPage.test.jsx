import process from "node:process";
import { afterEach, beforeEach, describe, it, expect, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import RunPage from "./RunPage";

// Each request the page makes on mount stays pending until the test settles it,
// so a test decides when the "late" answer arrives.
const pending = vi.hoisted(() => {
  const open = () => {
    const request = {};
    request.promise = new Promise((resolve, reject) => {
      request.resolve = resolve;
      request.reject = reject;
    });
    return request;
  };
  return { open, templates: open(), status: open(), schema: open() };
});

vi.mock("../../api/client", () => ({
  fetchTemplates: () => pending.templates.promise,
  fetchTemplate: () => new Promise(() => {}),
  crawlStatus: () => pending.status.promise,
  runCrawl: vi.fn(),
  stopCrawl: vi.fn(),
  fetchConfig: () => new Promise(() => {}),
  fetchConfigSchema: () => pending.schema.promise,
  fetchConfigDefaults: () => new Promise(() => {}),
}));

const SETTLE_MS = 20;
const settle = () => new Promise((resolve) => setTimeout(resolve, SETTLE_MS));

// What the CI failure looked like: the answer arrives after the test file's
// jsdom environment is gone, so React finds no `window` when a state setter runs.
async function answerAfterEnvironmentTeardown(answer) {
  const realWindow = globalThis.window;
  delete globalThis.window;
  try {
    answer();
    await settle();
  } finally {
    globalThis.window = realWindow;
  }
}

describe("RunPage requests that finish after the page is gone", () => {
  const unhandled = [];
  const recordUnhandled = (reason) => unhandled.push(reason);
  let warn;

  beforeEach(() => {
    unhandled.length = 0;
    pending.templates = pending.open();
    pending.status = pending.open();
    pending.schema = pending.open();
    process.on("unhandledRejection", recordUnhandled);
    warn = vi.spyOn(console, "warn").mockImplementation(() => {});
  });

  afterEach(() => {
    process.off("unhandledRejection", recordUnhandled);
    warn.mockRestore();
  });

  it("a blueprint list that fails late sets no state and leaves no unhandled rejection", async () => {
    const { unmount } = render(<RunPage />);
    unmount();

    await answerAfterEnvironmentTeardown(() => pending.templates.reject(new Error("Cannot reach the backend.")));

    expect(unhandled).toEqual([]);
  });

  it("a blueprint list that arrives late sets no state and leaves no unhandled rejection", async () => {
    const { unmount } = render(<RunPage />);
    unmount();

    await answerAfterEnvironmentTeardown(() => pending.templates.resolve({ templates: ["demo"] }));

    expect(unhandled).toEqual([]);
  });

  it("a status poll that answers late sets no state, so the poll logs nothing", async () => {
    const { unmount } = render(<RunPage />);
    unmount();

    // A state setter that runs here throws, and the poll's own catch would log it.
    await answerAfterEnvironmentTeardown(() => pending.status.resolve({ running: true, llm_calls: null }));

    expect(warn).not.toHaveBeenCalled();
    expect(unhandled).toEqual([]);
  });

  it("a status poll that fails late does not log a warning for a page that is gone", async () => {
    const { unmount } = render(<RunPage />);
    unmount();

    await answerAfterEnvironmentTeardown(() => pending.status.reject(new Error("Cannot reach the backend.")));

    expect(warn).not.toHaveBeenCalled();
    expect(unhandled).toEqual([]);
  });

  it("run settings that fail to load late set no state and leave no unhandled rejection", async () => {
    const { unmount } = render(<RunPage />);
    fireEvent.click(screen.getByRole("button", { name: /Override settings for this run/ }));
    unmount();

    await answerAfterEnvironmentTeardown(() => pending.schema.reject(new Error("Cannot reach the backend.")));

    expect(unhandled).toEqual([]);
  });
});
