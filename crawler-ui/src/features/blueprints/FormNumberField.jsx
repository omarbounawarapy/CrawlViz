import { NumberField } from "../../shared/ui";

/** The number a form keeps as text, or null for an empty or non-numeric one. */
function textToNumber(text) {
  if (text === "" || text === null || text === undefined) return null;
  const number = Number(text);
  return Number.isFinite(number) ? number : null;
}

/**
 * A whole-number box for a blueprint form, which keeps every value as text. An empty box
 * stays "" so the form's own validation says what is missing, rather than the box holding
 * the old number back.
 */
export default function FormNumberField({ value, onChange, ...rest }) {
  return (
    <NumberField
      {...rest}
      integer
      nullable
      value={textToNumber(value)}
      onChange={(number) => onChange(number === null ? "" : String(number))}
    />
  );
}
