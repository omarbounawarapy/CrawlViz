import { StrictMode } from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, act } from "@testing-library/react";
import { useCrawlStream } from "./useCrawlStream";

const sockets = [];
class FakeSocket {
  constructor(url) { this.url = url; this.closed = false; sockets.push(this); }
  close() { this.closed = true; queueMicrotask(() => this.onclose?.()); }
}

function Harness({ dispatch }) {
  useCrawlStream(dispatch, "ws://test");
  return null;
}

describe("useCrawlStream under StrictMode", () => {
  beforeEach(() => { sockets.length = 0; vi.stubGlobal("WebSocket", FakeSocket); vi.useFakeTimers(); });
  afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

  it("keeps one live socket, so each message is dispatched once", async () => {
    const dispatch = vi.fn();
    render(<StrictMode><Harness dispatch={dispatch} /></StrictMode>);
    await act(async () => { await vi.advanceTimersByTimeAsync(5000); });

    const live = sockets.filter(s => !s.closed);
    expect(live).toHaveLength(1);

    const msg = JSON.stringify({ type: "PIPELINE_EVENT", stage: "request", phase: "started", node_id: "1" });
    for (const s of sockets) s.onmessage?.({ data: msg });
    const pipeline = dispatch.mock.calls.filter(([e]) => e.type === "PIPELINE_EVENT");
    expect(pipeline).toHaveLength(1);
  });
});
