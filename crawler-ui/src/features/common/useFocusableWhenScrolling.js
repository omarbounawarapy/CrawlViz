import { useEffect, useRef } from "react";

/**
 * Ref for a scrolling box (a wide table, a log, a code block). A scrolling box must be keyboard
 * focusable so its arrow keys work (WCAG 2.1.1), but only while it really scrolls: a box that fits
 * is not a tab stop. The hook keeps the element's `tabindex` in step with its overflow, re-checking
 * when the box or one of its children changes size. The attribute is set on the node rather than
 * in JSX because it follows layout, which React does not know.
 */
export default function useFocusableWhenScrolling() {
  const ref = useRef(null);

  // A ResizeObserver reports once when it starts observing, then on every size change.
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === "undefined") return undefined;
    const sync = () => {
      if (el.scrollWidth > el.clientWidth || el.scrollHeight > el.clientHeight) el.tabIndex = 0;
      else el.removeAttribute("tabindex");
    };
    const observer = new ResizeObserver(sync);
    observer.observe(el);
    Array.from(el.children).forEach((child) => observer.observe(child));
    return () => observer.disconnect();
  }, []);

  return ref;
}
