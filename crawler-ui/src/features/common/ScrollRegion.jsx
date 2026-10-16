/**
 * A wide table's sideways scroller. On a narrow screen the table scrolls inside it, so the
 * scroller must take keyboard focus (arrow keys scroll it) and carry a name (WCAG 2.1.1, 1.4.10).
 */
export default function ScrollRegion({ label, style, children }) {
  return (
    <div role="region" aria-label={label} tabIndex={0} className="focus-box" style={{ overflowX: "auto", ...style }}>
      {children}
    </div>
  );
}
