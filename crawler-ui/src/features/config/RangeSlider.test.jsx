import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import RangeSlider from "./RangeSlider";
import Stepper from "./Stepper";
import { clampPair } from "./configModel";

afterEach(cleanup);

// jsdom has no PointerEvent; without it fireEvent drops clientX.
if (!window.PointerEvent) window.PointerEvent = class extends MouseEvent {};

const B = { min: 0, max: 1, step: 0.01 };

describe("clampPair", () => {
  it("never lets the low thumb reach the high one", () => {
    expect(clampPair({ low: 0.2, high: 0.75 }, "low", 0.9, B)).toEqual({ low: 0.74, high: 0.75 });
  });
  it("never lets the high thumb reach the low one", () => {
    expect(clampPair({ low: 0.2, high: 0.75 }, "high", 0.05, B)).toEqual({ low: 0.2, high: 0.21 });
  });
  it("stays inside the track bounds", () => {
    expect(clampPair({ low: 0.2, high: 0.75 }, "low", -3, B).low).toBe(0);
    expect(clampPair({ low: 0.2, high: 0.75 }, "high", 3, B).high).toBe(1);
  });
});

describe("RangeSlider", () => {
  const setup = (props = {}) => {
    const onChange = vi.fn();
    render(<RangeSlider low={0.2} high={0.75} onChange={onChange} lowLabel="Low" highLabel="High" {...props} />);
    return onChange;
  };

  it("exposes two slider roles bounded by each other", () => {
    setup();
    const [low, high] = screen.getAllByRole("slider");
    expect(low.getAttribute("aria-valuemax")).toBe("0.74");
    expect(high.getAttribute("aria-valuemin")).toBe("0.21");
  });

  it("moves by arrow keys and stops at the other thumb", () => {
    const onChange = setup({ low: 0.74, high: 0.75 });
    const [low] = screen.getAllByRole("slider");
    fireEvent.keyDown(low, { key: "ArrowRight" });
    expect(onChange).not.toHaveBeenCalled();
    fireEvent.keyDown(low, { key: "ArrowLeft" });
    expect(onChange).toHaveBeenCalledWith(0.73, 0.75);
  });

  it("drags the nearest thumb with the pointer without crossing", () => {
    const onChange = setup();
    const track = screen.getAllByRole("slider")[0].parentElement;
    track.getBoundingClientRect = () => ({ left: 0, width: 100, top: 0, height: 28 });
    track.setPointerCapture = () => {};
    fireEvent.pointerDown(track, { clientX: 95, button: 0, pointerId: 1 });
    expect(onChange).toHaveBeenLastCalledWith(0.2, 0.95);
    fireEvent.pointerMove(track, { clientX: 5, pointerId: 1 });
    expect(onChange).toHaveBeenLastCalledWith(0.2, 0.21);
  });
});

describe("Stepper", () => {
  it("clamps to its bounds from buttons and keys", () => {
    const onChange = vi.fn();
    render(<Stepper label="Workers" value={1} min={1} max={3} onChange={onChange} />);
    expect(screen.getByRole("button", { name: "Decrease Workers" }).disabled).toBe(true);
    fireEvent.keyDown(screen.getByRole("spinbutton"), { key: "ArrowDown" });
    expect(onChange).not.toHaveBeenCalled();
    fireEvent.keyDown(screen.getByRole("spinbutton"), { key: "ArrowUp" });
    expect(onChange).toHaveBeenCalledWith(2);
  });

  it("repeats while the button is held", () => {
    vi.useFakeTimers();
    const onChange = vi.fn();
    render(<Stepper label="Workers" value={1} min={1} max={64} onChange={onChange} />);
    const plus = screen.getByRole("button", { name: "Increase Workers" });
    fireEvent.pointerDown(plus, { button: 0 });
    vi.advanceTimersByTime(400 + 70 * 3);
    fireEvent.pointerUp(plus);
    vi.advanceTimersByTime(1000);
    expect(onChange.mock.calls.map((c) => c[0])).toEqual([2, 3, 4, 5]);
    vi.useRealTimers();
  });
});
