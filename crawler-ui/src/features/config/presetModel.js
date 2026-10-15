import { getIn, humanize, sameValue } from "./configModel";

const isPlain = (v) => v !== null && typeof v === "object" && !Array.isArray(v);

/** Leaf [path, value] pairs of a nested partial config. */
export function flatten(values, prefix = "") {
  return Object.entries(values ?? {}).flatMap(([k, v]) => {
    const path = prefix ? `${prefix}.${k}` : k;
    return isPlain(v) ? flatten(v, path) : [[path, v]];
  });
}

/** What applying `values` would change against `current`: [{ path, label, from, to }]. */
export function presetChanges(values, current) {
  return flatten(values)
    .map(([path, to]) => ({ path, to, from: getIn(current, path) }))
    .filter((c) => !sameValue(c.from, c.to))
    .map((c) => ({ ...c, label: c.path.split(".").map(humanize).join(" › ") }));
}

export const shown = (v) => (v === null || v === undefined ? "no limit" : typeof v === "boolean" ? (v ? "on" : "off") : String(v));
