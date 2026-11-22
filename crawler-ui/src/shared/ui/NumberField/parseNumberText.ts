/** What a person typed into a number box: a number, an empty box (`null`), or text that is not a number. */
export type ParsedNumber = { ok: true; value: number | null } | { ok: false };

const NUMBER_PATTERN = /^[-+]?(\d+\.?\d*|\.\d+)(e[-+]?\d+)?$/i;

/**
 * Reads typed number text whatever the keyboard's locale. A dot or a comma can be the
 * decimal separator ("0,3" and "0.3" are both 0.3); when both appear, the comma separates
 * thousands ("1,000.5"). Spaces around the text are ignored; an empty box is `null`.
 *
 * The config feature has the same reader in `features/config/numberParse.js`; it moves to
 * this one when its settings move to the shared NumberField.
 */
export function parseNumberText(text: string): ParsedNumber {
  const trimmed = text.trim();
  if (trimmed === "") return { ok: true, value: null };
  let normalised = trimmed;
  if (normalised.includes(".") && normalised.includes(",")) normalised = normalised.replaceAll(",", "");
  else if (normalised.split(",").length === 2) normalised = normalised.replace(",", ".");
  if (!NUMBER_PATTERN.test(normalised)) return { ok: false };
  const value = Number(normalised);
  return Number.isFinite(value) ? { ok: true, value } : { ok: false };
}

/** The text a stored number is edited as: dot decimals, no grouping, so it parses back unchanged. */
export function numberToEditableText(value: number | null): string {
  return value === null ? "" : String(value);
}
