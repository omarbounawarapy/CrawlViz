import { useState } from "react";
import { getTheme } from "../../theme";
import { TextInput } from "../common/Form";
import { parseNumberText, formatNumber } from "./numberParse";

const theme = getTheme();
const { text } = theme.colors;

/**
 * The one number input the settings pages use. It is type=text so the browser
 * never reformats the value, shows dot decimals, accepts a comma too, and emits
 * a number only when the text parses. `nullable` lets an empty box mean null.
 */
export default function NumberField({
  id, value, onChange, nullable = false, unit, invalid = false, label, width = 110, integer = false, ...rest
}) {
  const [raw, setRaw] = useState(null); // text while typing, so "0." and "" survive
  const shown = raw ?? formatNumber(value);
  const bad = raw !== null && !parseNumberText(raw).ok;
  const flagged = invalid || bad;
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
      <TextInput
        {...rest}
        id={id} type="text" inputMode={integer ? "numeric" : "decimal"} value={shown}
        invalid={flagged} aria-invalid={flagged || undefined} aria-label={label}
        style={{ width, textAlign: "right", color: bad ? theme.colors.accent.red : text.primary }}
        onChange={(e) => {
          const t = e.target.value;
          setRaw(t);
          const parsed = parseNumberText(t);
          if (!parsed.ok) return;
          if (parsed.value === null) onChange(nullable ? null : "");
          else onChange(parsed.value);
        }}
        onBlur={() => setRaw(null)}
      />
      {unit && <span style={{ fontSize: 13, color: text.muted, minWidth: 18 }}>{unit}</span>}
    </span>
  );
}
