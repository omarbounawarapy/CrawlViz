import { getIn, humanize, sameValue } from "./configModel";
import { STAGE_NAMES } from "./pipelineNames";

const isPlain = (v) => v !== null && typeof v === "object" && !Array.isArray(v);

/** Leaf [path, value] pairs of a nested partial config. */
export function flatten(values, prefix = "") {
  return Object.entries(values ?? {}).flatMap(([k, v]) => {
    const path = prefix ? `${prefix}.${k}` : k;
    return isPlain(v) ? flatten(v, path) : [[path, v]];
  });
}

export const shown = (v) =>
  v === null || v === undefined ? "no limit" : typeof v === "boolean" ? (v ? "on" : "off") : String(v);

// A 0-1 slider with no unit is a fraction: people read it as a percentage, as the control draws it.
const isFraction = (field) =>
  Boolean(field) && field.widget === "slider" && field.minimum === 0 && field.maximum === 1 && field.unit === "";

// A path as the page names it: a pipeline's key reads as its stage name, as the Pipelines table shows it.
const labelPath = (path) =>
  path
    .split(".")
    .map((part, i, all) => (all[0] === "pipelines" && i === 1 ? (STAGE_NAMES[part] ?? humanize(part)) : humanize(part)))
    .join(" › ");

/** A value as the page shows it: fractions as percentages, everything else as `shown` does. */
export function valueText(v, field) {
  if (field && isFraction(field) && typeof v === "number") return `${Math.round(v * 100)} %`;
  return shown(v);
}

// The NLP and LLM biases are one slider on the page ("NLP 60 % · LLM 40 %"), so a change to
// either one is shown as that slider moving, not as two raw weights.
function mergeShares(changes, current, values) {
  const nlp = "priority.nlp_bias";
  const llm = "priority.llm_bias";
  const both = getIn(values, nlp) !== undefined && getIn(values, llm) !== undefined;
  if (!both) return changes;
  const share = (n, l) => {
    const total = Number(n) + Number(l);
    return total > 0 ? Math.round((Number(l) / total) * 100) : 50;
  };
  const from = share(getIn(current, nlp), getIn(current, llm));
  const to = share(getIn(values, nlp), getIn(values, llm));
  const rest = changes.filter((c) => c.path !== nlp && c.path !== llm);
  if (from === to) return rest;
  const sharePair = (l) => `NLP ${100 - l} % · LLM ${l} %`;
  return [
    ...rest,
    {
      path: nlp,
      name: "NLP and LLM share of priority",
      label: "Priority › NLP and LLM share",
      from: sharePair(from),
      to: sharePair(to),
      fromText: sharePair(from),
      toText: sharePair(to),
    },
  ];
}

/**
 * What applying `values` would change against `current`:
 * [{ path, label, name, from, to, fromText, toText }]. `fields` (the schema's editable fields)
 * say how a value reads, for example a fraction as a percentage.
 */
export function presetChanges(values, current, fields = []) {
  const byPath = new Map(fields.map((f) => [f.path, f]));
  const changes = flatten(values)
    .map(([path, to]) => ({ path, to, from: getIn(current, path) }))
    .filter((c) => !sameValue(c.from, c.to));
  return mergeShares(changes, current, values).map((c) => {
    const field = byPath.get(c.path);
    const inside = labelPath(c.path).split(" › ").slice(1).join(" › ");
    const name = c.name ?? (inside || labelPath(c.path));
    return {
      ...c,
      label: c.label ?? labelPath(c.path),
      name,
      fromText: c.fromText ?? valueText(c.from, field),
      toText: c.toText ?? valueText(c.to, field),
    };
  });
}

/** Markdown for a methods section: every setting that differs from the built-in defaults, grouped by section. */
export function changesMarkdown(current, defaults, when, fields = []) {
  const changes = presetChanges(current, defaults, fields);
  const lines = [
    "# Settings changed from defaults",
    "",
    `${when}. ${changes.length === 1 ? "One setting differs" : `${changes.length} settings differ`} from the built-in defaults.`,
  ];
  if (changes.length === 0) return [...lines, "", "No setting differs from the built-in defaults."].join("\n") + "\n";
  const sections = new Map();
  changes.forEach((c) => {
    const section = c.path.includes(".") ? humanize(c.path.split(".")[0]) : "Top level";
    if (!sections.has(section)) sections.set(section, []);
    sections.get(section).push(c);
  });
  sections.forEach((items, section) => {
    lines.push("", `## ${section}`, "");
    items.forEach((c) => {
      lines.push(`- ${c.name}: default ${c.fromText}, changed to ${c.toText}`);
    });
  });
  return lines.join("\n") + "\n";
}
