import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import Scrubber from "./Scrubber";

const describeAt = (i) => ({ title: `Event ${i + 1} of 100`, detail: "12:00:00 · 3 pages", spoken: `Event ${i + 1} of 100, 3 pages found, at 12:00:00` });

function setup(props = {}) {
  const onSeek = vi.fn(), onLive = vi.fn(), onUserSeek = vi.fn();
  render(<Scrubber total={100} position={40} types={Array.from({ length: 100 }, (_, i) => (i === 60 ? "NODE_ERROR" : "NODE_ADDED"))} describe={describeAt}
    onSeek={onSeek} onLive={onLive} onUserSeek={onUserSeek} {...props} />);
  return { onSeek, onLive, onUserSeek, slider: screen.getByRole("slider", { name: "Replay position" }) };
}

describe("Scrubber", () => {
  it("is one slider with a spoken value", () => {
    const { slider } = setup();
    expect(slider.getAttribute("aria-valuenow")).toBe("41");
    expect(slider.getAttribute("aria-valuemax")).toBe("100");
    expect(slider.getAttribute("aria-valuetext")).toMatch(/Event 41 of 100, 3 pages found/);
  });

  it("steps by one, ten and fifty events from the keyboard, clamped to the record", () => {
    const { slider, onSeek } = setup();
    fireEvent.keyDown(slider, { key: "ArrowRight" });
    expect(onSeek).toHaveBeenLastCalledWith(41);
    fireEvent.keyDown(slider, { key: "ArrowLeft", shiftKey: true });
    expect(onSeek).toHaveBeenLastCalledWith(30);
    fireEvent.keyDown(slider, { key: "PageUp" });
    expect(onSeek).toHaveBeenLastCalledWith(90);
    fireEvent.keyDown(slider, { key: "Home" });
    expect(onSeek).toHaveBeenLastCalledWith(0);
  });

  it("End returns to live, and any seek pauses playback", () => {
    const { slider, onLive, onUserSeek } = setup();
    fireEvent.keyDown(slider, { key: "End" });
    expect(onLive).toHaveBeenCalled();
    fireEvent.keyDown(slider, { key: "ArrowRight" });
    expect(onUserSeek).toHaveBeenCalled();
  });

  it("does nothing while disabled", () => {
    const { slider, onSeek } = setup({ total: 0, position: 0, disabled: true });
    fireEvent.keyDown(slider, { key: "ArrowRight" });
    expect(onSeek).not.toHaveBeenCalled();
    expect(slider.getAttribute("aria-valuetext")).toBe("No events yet");
  });
});
