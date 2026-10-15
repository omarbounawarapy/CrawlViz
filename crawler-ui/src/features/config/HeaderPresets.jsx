import { getTheme } from "../../theme";
import { HEADER_PRESETS, activePreset } from "./headerPresets";

const theme = getTheme();
const { text, background } = theme.colors;

/** Ready-made header sets; choosing one fills the user agent and every other header field. */
export default function HeaderPresets({ fetch, onApply }) {
  const current = activePreset(fetch);
  return (
    <div role="radiogroup" aria-label="Header sets" style={{ padding: "10px 0 14px", borderBottom: `1px solid ${theme.colors.rowBorder}` }}>
      <div style={{ fontSize: 14, color: text.primary, marginBottom: 6 }}>Header sets</div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        {HEADER_PRESETS.map((p) => {
          const on = current?.name === p.name;
          return (
            <button key={p.name} type="button" role="radio" aria-checked={on} onClick={() => onApply(p.values)}
                    style={{
                      flex: "1 1 170px", textAlign: "left", padding: "8px 10px", cursor: "pointer", font: "inherit",
                      background: on ? "rgba(15,27,45,0.06)" : "transparent", color: text.primary,
                      border: `${on ? 2 : 1}px solid ${on ? text.primary : background.border}`, borderRadius: theme.radii.md,
                    }}>
              <span style={{ display: "block", fontSize: 14, fontWeight: 600 }}>{p.name}</span>
              <span style={{ display: "block", fontSize: 13, color: text.secondary, marginTop: 2 }}>{p.about}</span>
            </button>
          );
        })}
      </div>
      <p style={{ fontSize: 13, color: text.muted, margin: "6px 0 0" }}>
        {current ? `Using “${current.name}”.` : "Custom headers."} Edit any field below to fine-tune.
      </p>
    </div>
  );
}
