import { useRef, useState } from "react";
import { getTheme } from "../../theme";
import { Button } from "../common/Form";
import { HEADER_PRESETS, activePreset } from "./headerPresets";
import { presetChanges, shown } from "./presetModel";
import { nextChoice } from "../common/choiceKeys";

const theme = getTheme();
const { text, background } = theme.colors;

/**
 * Ready-made header sets. Choosing one opens a preview of the fields it would change;
 * nothing is written to the draft until Apply, and Save still decides what sticks.
 */
export default function HeaderPresets({ fetch, onApply }) {
  const [pending, setPending] = useState(null);
  const headerRefs = useRef([]);
  const current = activePreset(fetch);
  const chosen = HEADER_PRESETS.find((p) => p.name === pending) ?? null;
  const changes = chosen ? presetChanges({ fetch: chosen.values }, { fetch }) : [];
  return (
    <div role="radiogroup" aria-label="Header sets" style={{ padding: "10px 0 14px", borderBottom: `1px solid ${theme.colors.rowBorder}` }}>
      <div style={{ fontSize: 14, color: text.primary, marginBottom: 6 }}>Header sets</div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        {HEADER_PRESETS.map((p) => {
          const on = (pending ? pending === p.name : current?.name === p.name);
          const i = HEADER_PRESETS.indexOf(p);
          return (
            <button key={p.name} type="button" role="radio" aria-checked={on} tabIndex={on ? 0 : -1}
                    ref={(el) => { headerRefs.current[i] = el; }}
                    onKeyDown={(e) => {
                      const n = nextChoice(e, i, HEADER_PRESETS.length);
                      if (n === null) return;
                      setPending(HEADER_PRESETS[n].name);
                      headerRefs.current[n]?.focus();
                    }}
                    onClick={() => setPending(p.name)}
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
      {chosen && (
        <div role="region" aria-label={`Preview of ${chosen.name}`}
             style={{ marginTop: 10, padding: "10px 12px", border: `1px solid ${background.border}`, borderRadius: theme.radii.md }}>
          {changes.length === 0 ? (
            <p style={{ fontSize: 13, color: text.secondary, margin: 0 }}>{chosen.name} is already the set in use.</p>
          ) : (
            <>
              <p style={{ fontSize: 13, color: text.secondary, margin: "0 0 6px" }}>
                {chosen.name} changes {changes.length} field{changes.length === 1 ? "" : "s"}:
              </p>
              <ul style={{ margin: "0 0 8px", paddingLeft: 18, fontSize: 13, color: text.primary, display: "flex", flexDirection: "column", gap: 3 }}>
                {changes.map((c) => (
                  <li key={c.path} style={{ wordBreak: "break-word" }}>
                    {c.label.replace(/^Fetch › /, "")}: <span style={{ color: text.muted }}>{shown(c.from)}</span> → {shown(c.to)}
                  </li>
                ))}
              </ul>
            </>
          )}
          <div style={{ display: "flex", gap: 8 }}>
            {changes.length > 0 && (
              <Button variant="primary" onClick={() => { onApply(chosen.values); setPending(null); }}>
                Apply to draft
              </Button>
            )}
            <Button variant="quiet" onClick={() => setPending(null)}>Cancel</Button>
          </div>
        </div>
      )}
      <p style={{ fontSize: 13, color: text.muted, margin: "6px 0 0" }}>
        {current ? `Using “${current.name}”.` : "Custom headers."} Edit any field below to fine-tune.
      </p>
    </div>
  );
}
