// Pure helpers behind the settings editor. The backend's JSON Schema is the
// only description of what can be edited; nothing here names a setting.

const ACRONYMS = { llm: "LLM", nlp: "NLP", ui: "UI", url: "URL", api: "API", ws: "WS", http: "HTTP", nlp_bias: "NLP bias" };

export function humanize(key = "") {
  const words = key.replace(/[_-]+/g, " ").trim().split(/\s+/).map((w, i) => {
    const lower = w.toLowerCase();
    return ACRONYMS[lower] ?? (i === 0 ? lower[0]?.toUpperCase() + lower.slice(1) : lower);
  });
  return words.join(" ");
}

function resolve(schema, node) {
  if (node?.$ref) return schema.$defs?.[node.$ref.split("/").pop()] ?? {};
  return node ?? {};
}

// `int | None` arrives as anyOf [{type: integer}, {type: null}].
function unwrap(schema, node) {
  if (!node?.anyOf) return { node: resolve(schema, node), nullable: false };
  const nullable = node.anyOf.some((n) => n.type === "null");
  const inner = node.anyOf.find((n) => n.type !== "null") ?? {};
  return { node: { ...resolve(schema, inner), ...node, anyOf: undefined }, nullable };
}

function widgetFor(field, node) {
  if (field.ui_widget) return field.ui_widget;
  if (node.type === "boolean") return "toggle";
  if (node.type === "integer" || node.type === "number") return "number";
  if (node.type === "object") return "headers";
  return "text";
}

/**
 * Flatten RuntimeConfig's schema into editable leaves:
 * { path: "fetch.min_delay", key, title, description, widget, type, nullable,
 *   minimum, maximum, unit, apply, advanced, options, section, group }
 * Nested objects that are plain settings groups (pipelines.filtering.*) are
 * descended into; `group` names that sub-object so a table can lay it out.
 */
export function buildFields(schema) {
  const fields = [];
  const walk = (def, prefix, topKey, group) => {
    Object.entries(def.properties ?? {}).forEach(([key, raw]) => {
      const { node, nullable } = unwrap(schema, raw);
      const path = prefix ? `${prefix}.${key}` : key;
      const isGroup = node.type === "object" && node.properties && !raw.ui_widget;
      if (isGroup) {
        walk(node, path, topKey, key);
        return;
      }
      fields.push({
        path, key, topKey, group,
        title: humanize(key),
        description: (raw.description ?? node.description ?? "").replace(/\s*--\s*/g, " — "),
        type: node.type,
        nullable,
        widget: widgetFor(raw, node),
        minimum: node.minimum ?? node.exclusiveMinimum,
        maximum: node.maximum,
        unit: raw.ui_unit,
        apply: raw.ui_apply ?? "next_run",
        advanced: Boolean(raw.ui_advanced),
        options: raw.ui_options,
        default: raw.default,
        section: raw.ui_section ?? humanize(topKey),
      });
    });
  };
  Object.entries(schema.properties ?? {}).forEach(([topKey, ref]) => {
    walk(resolve(schema, ref), topKey, topKey, null);
  });
  return fields;
}

export function groupBySection(fields) {
  const out = new Map();
  fields.forEach((f) => {
    if (!out.has(f.section)) out.set(f.section, []);
    out.get(f.section).push(f);
  });
  return [...out.entries()];
}

export const getIn = (obj, path) => path.split(".").reduce((v, k) => (v == null ? v : v[k]), obj);

export function setIn(obj, path, value) {
  const [head, ...rest] = path.split(".");
  const next = { ...(obj ?? {}) };
  next[head] = rest.length ? setIn(next[head], rest.join("."), value) : value;
  return next;
}

export const sameValue = (a, b) => JSON.stringify(a ?? null) === JSON.stringify(b ?? null);

/** Nested patch holding only the leaves where `draft` differs from `base`. */
export function buildPatch(fields, draft, base) {
  let patch = {};
  fields.forEach((f) => {
    const value = getIn(draft, f.path);
    if (!sameValue(value, getIn(base, f.path))) patch = setIn(patch, f.path, value ?? null);
  });
  return patch;
}

/** The part of `patch` that can be pushed to a running crawl. */
export function livePatch(fields, patch) {
  let out = {};
  fields.forEach((f) => {
    if (f.apply !== "live") return;
    const v = getIn(patch, f.path);
    if (v !== undefined) out = setIn(out, f.path, v);
  });
  return out;
}

export const isEmptyPatch = (patch) => Object.keys(patch).length === 0;

/** Client-side bounds check mirroring the schema; the server stays authoritative. */
export function validateField(field, value) {
  if (field.widget === "number" || field.widget === "slider") {
    if (value === null || value === undefined || value === "") {
      return field.nullable ? null : "Required";
    }
    const n = Number(value);
    if (Number.isNaN(n)) return "Must be a number";
    if (field.type === "integer" && !Number.isInteger(n)) return "Must be a whole number";
    if (field.minimum != null && n < field.minimum) return `At least ${field.minimum}`;
    if (field.maximum != null && n > field.maximum) return `At most ${field.maximum}`;
  }
  return null;
}

export function matches(field, query) {
  if (!query) return true;
  const q = query.toLowerCase();
  return [field.path, field.title, field.description, field.section].some((s) => s?.toLowerCase().includes(q));
}
