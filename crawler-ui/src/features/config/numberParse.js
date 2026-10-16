// Reads what a person typed into a number control. A dot or a comma can be the
// decimal separator ("0,3" and "0.3" are both 0.3); when both appear, the comma
// is a thousands separator ("1,000.5"). Empty text is `null`, not an error.
const NUMBER = /^[-+]?(\d+\.?\d*|\.\d+)(e[-+]?\d+)?$/i;

export function parseNumberText(text) {
  const t = String(text ?? "").trim();
  if (t === "") return { ok: true, value: null };
  let s = t;
  if (s.includes(".") && s.includes(",")) s = s.replace(/,/g, "");
  else if (s.split(",").length === 2) s = s.replace(",", ".");
  if (!NUMBER.test(s)) return { ok: false, value: null };
  return { ok: true, value: Number(s) };
}

/** The text a number is shown as: always dot-decimal, whatever the browser locale. */
export const formatNumber = (value) => (value === null || value === undefined ? "" : String(value));
