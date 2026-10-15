import { getTheme } from "../../theme";
import { Button } from "../common/Form";

const theme = getTheme();

/** Suggestions for the open section, each with a one-click fix (when safe) and a dismiss. */
export default function SuggestionsStrip({ items, onApply, onDismiss }) {
  if (items.length === 0) return null;
  return (
    <ul aria-label="Suggestions" style={{ listStyle: "none", margin: "8px 0 12px", padding: 0, display: "grid", gap: 6 }}>
      {items.map((s) => (
        <li key={s.id} style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", padding: "8px 10px",
                                border: `1px solid ${theme.colors.background.border}`, borderRadius: theme.radii.md,
                                background: "rgba(15,27,45,0.03)" }}>
          <span style={{ flex: "1 1 280px", fontSize: 13, color: theme.colors.text.primary }}>{s.text}</span>
          {s.fix && <Button onClick={() => onApply(s)}>{s.fix.label}</Button>}
          <Button variant="quiet" onClick={() => onDismiss(s.id)} aria-label={`Dismiss suggestion: ${s.text.slice(0, 40)}`}>Dismiss</Button>
        </li>
      ))}
    </ul>
  );
}
