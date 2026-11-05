import useFocusableWhenScrolling from "./useFocusableWhenScrolling";

/**
 * A wide table's sideways scroller. On a narrow screen the table scrolls inside it, so while it
 * scrolls the scroller takes keyboard focus (arrow keys scroll it) and carries a name (WCAG 2.1.1, 1.4.10).
 */
export default function ScrollRegion({ label, style, children }) {
  const ref = useFocusableWhenScrolling();
  return (
    <div ref={ref} role="region" aria-label={label} className="focus-box" style={{ overflowX: "auto", ...style }}>
      {children}
    </div>
  );
}
