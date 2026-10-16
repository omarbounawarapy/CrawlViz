import { useId, useState } from "react";
import { getTheme } from "../../theme";
import { TextInput } from "../common/Form";
import { parseNumberText, formatNumber } from "./numberParse";

const theme = getTheme();
const { text } = theme.colors;

/**
 * The one number input the settings pages use. It is type=text so the browser
 * never reformats the value, shows dot decimals, accepts a comma too, and emits
 * a number only when the text parses. `nullable` lets an empty box mean null.
 * `label` names it only where no visible <label> does (a table cell); text that
 * does not parse gets a message saying what to type (WCAG 3.3.1, 3.3.3). The unit
 * and any `describedBy` ids are read after the value.
 */
export default function NumberField({
  id, value, onChange, nullable = false, unit, invalid = false, label, width = 110, integer = false, describedBy, ...rest
}) {
  const [raw, setRaw] = useState(null); // text while typing, so "0." and "" survive
  const uid = useId();
  const shown = raw ?? formatNumber(value);
  const bad = raw !== null && !parseNumberText(raw).ok;
  const flagged = invalid || bad;
  const unitId = `${uid}-unit`, badId = `${uid}-bad`;
  const describe = [rest["aria-describedby"], describedBy, unit && unitId, bad && badId].filter(Boolean).join(" ") || undefined;
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
      <TextInput
        {...rest}
        id={id} type="text" inputMode={integer ? "numeric" : "decimal"} value={shown}
        invalid={flagged} aria-invalid={flagged || undefined} aria-label={label} aria-describedby={describe}
        style={{ width, maxWidth: "100%", textAlign: "right", color: bad ? theme.colors.accent.red : text.primary }}
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
      {unit && <span id={unitId} style={{ fontSize: 13, color: text.muted, minWidth: 18 }}>{unit}</span>}
      {bad && (
        <span id={badId} style={{ flexBasis: "100%", fontSize: 13, color: theme.colors.accent.red }}>
          Enter a {integer ? "whole number, like 12" : "number, like 0.5"}.
        </span>
      )}
    </span>
  );
}
