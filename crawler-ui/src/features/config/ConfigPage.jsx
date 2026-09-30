import { useEffect, useState } from "react";
import { getTheme } from "../../theme";
import { Page, SectionTitle, Row } from "../common/Page";
import { buttonOutline } from "../common/buttons";
import { fetchConfigSchema, fetchConfig } from "../../api/client";

const theme = getTheme();

function resolve(schema, node) {
  if (node?.$ref) {
    const name = node.$ref.split("/").pop();
    return schema.$defs?.[name] || {};
  }
  return node;
}

// Groups every leaf field across every top-level RuntimeConfig section by
// its ui_section hint, so "Scoring cascade" reads as one coherent block
// even though it's one Pydantic sub-model among several at the schema level.
function groupFields(schema) {
  const groups = {};
  Object.entries(schema.properties || {}).forEach(([key, ref]) => {
    const resolved = resolve(schema, ref);
    Object.entries(resolved.properties || {}).forEach(([fieldKey, field]) => {
      const section = field.ui_section || resolved.title || key;
      if (!groups[section]) groups[section] = [];
      groups[section].push({ path: `${key}.${fieldKey}`, key: fieldKey, ...field });
    });
  });
  return groups;
}

function get(values, path) {
  return path.split(".").reduce((v, k) => (v == null ? v : v[k]), values);
}

const ACRONYMS = { llm: "LLM", nlp: "NLP", ui: "UI", url: "URL", api: "API", ws: "WS" };
function humanize(title = "") {
  const words = title.trim().split(/\s+/).map((w, i) => {
    const lower = w.toLowerCase();
    return ACRONYMS[lower] ?? (i === 0 ? w[0]?.toUpperCase() + w.slice(1).toLowerCase() : lower);
  });
  return words.join(" ");
}
const slug = (t) => `cfg-${t.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;

// Position on the allowed range: a hairline with one tick, not a filled bar.
function RangeTick({ value, min, max }) {
  const pct = Math.max(0, Math.min(100, ((value - min) / (max - min || 1)) * 100));
  return (
    <svg width="120" height="14" role="img" aria-label={`${value} on a scale of ${min} to ${max}`} style={{ display: "block" }}>
      <line x1="0" y1="7" x2="120" y2="7" stroke={theme.colors.text.muted} strokeWidth="1" />
      <line x1="0" y1="3" x2="0" y2="11" stroke={theme.colors.text.muted} strokeWidth="1" />
      <line x1="120" y1="3" x2="120" y2="11" stroke={theme.colors.text.muted} strokeWidth="1" />
      <circle cx={(pct / 100) * 120} cy="7" r="4.5" fill={theme.colors.text.primary} />
    </svg>
  );
}


// The two thresholds drawn on the 0-1 NLP similarity scale, so the numbers
// read as three zones. Vermilion marks the most promising zone.
function CascadeScale({ low, high }) {
  if (typeof low !== "number" || typeof high !== "number") return null;
  const W = 600, H = 34, x = (v) => Math.max(0, Math.min(1, v)) * W;
  const zones = [
    { from: 0, to: low, fill: "#e3e8ee", label: "Mostly skipped" },
    { from: low, to: high, fill: "#b7c1cd", label: "LLM decides" },
    { from: high, to: 1, fill: theme.colors.relevance.ramp[1], label: "Trusted on NLP score" },
  ];
  return (
    <figure style={{ margin: "4px 0 10px", maxWidth: 600 }}>
      <svg viewBox={`0 0 ${W} ${H + 26}`} width="100%" role="img"
           aria-label={`Similarity scores below ${low} are mostly skipped, between ${low} and ${high} the LLM decides, above ${high} are trusted on the NLP score.`}>
        {zones.map((z) => (
          <g key={z.label}>
            <rect x={x(z.from)} y="0" width={Math.max(0, x(z.to) - x(z.from))} height={H} fill={z.fill} />
            <text x={(x(z.from) + x(z.to)) / 2} y={H + 18} textAnchor="middle" fontSize="13" fill={theme.colors.text.secondary}>{z.label}</text>
          </g>
        ))}
        {[low, high].map((v) => (
          <g key={v}>
            <line x1={x(v)} x2={x(v)} y1="-2" y2={H + 2} stroke={theme.colors.text.primary} strokeWidth="2" />
          </g>
        ))}
      </svg>
      <figcaption style={{ fontSize: 13, color: theme.colors.text.muted, marginTop: 2 }}>
        NLP similarity from 0 to 1. Thresholds at {low} and {high}.
      </figcaption>
    </figure>
  );
}

function FieldDisplay({ field, value }) {
  const current = value ?? field.default;
  const hasRange = field.minimum != null && field.maximum != null && typeof current === "number";
  const options = field.ui_widget === "select" && field.ui_options ? field.ui_options : null;

  return (
    <Row label={humanize(field.title)} note={field.description}>
      {options ? (
        <span style={{ fontWeight: 400, color: theme.colors.text.muted }}>
          {options.map((opt, i) => (
            <span key={opt}>
              {i > 0 && " · "}
              <span style={opt === current ? { fontWeight: 700, color: theme.colors.text.primary } : undefined}>{opt}</span>
            </span>
          ))}
        </span>
      ) : hasRange ? (
        <span style={{ display: "inline-flex", alignItems: "center", gap: 14 }}>
          <RangeTick value={current} min={field.minimum} max={field.maximum} />
          <span style={{ minWidth: 44 }}>{String(current)}</span>
        </span>
      ) : String(current)}
    </Row>
  );
}

export default function ConfigPage() {
  const [schema, setSchema] = useState(null);
  const [values, setValues] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([fetchConfigSchema(), fetchConfig()])
      .then(([schemaRes, valuesRes]) => {
        if (cancelled) return;
        setSchema(schemaRes);
        setValues(valuesRes);
      })
      .catch(err => !cancelled && setError(err.message));
    return () => { cancelled = true; };
  }, []);

  const groups = schema && values ? Object.entries(groupFields(schema)) : [];

  const index = groups.length > 0 && (
    <nav aria-label="Configuration sections" style={{ width: 200, flexShrink: 0, position: "sticky", top: 0, alignSelf: "flex-start", paddingTop: 76 }}>
      <ul style={{ listStyle: "none", display: "flex", flexDirection: "column", gap: 10 }}>
        {groups.map(([section]) => (
          <li key={section}><a href={`#/config`} onClick={(e) => { e.preventDefault(); document.getElementById(slug(section))?.scrollIntoView({ behavior: "smooth" }); }}
            style={{ fontSize: 14, color: theme.colors.text.secondary, textDecoration: "none" }}>{section}</a></li>
        ))}
      </ul>
    </nav>
  );

  return (
    <Page
      title="Configuration"
      lead="The settings the crawler is running under. These are read from the backend and cannot be edited here yet."
      aside={index || null}
    >
      {error && (
        <div role="alert" style={{ maxWidth: "60ch" }}>
          <p style={{ fontSize: 14, color: theme.colors.accent.red, marginBottom: 12 }}>
            Could not load the configuration. The control API did not answer ({error}). Start it with make dev-backend, then try again.
          </p>
          <button onClick={() => window.location.reload()} style={buttonOutline(false)}>Try again</button>
        </div>
      )}
      {!error && !schema && <p style={{ fontSize: 14, color: theme.colors.text.muted }}>Loading configuration…</p>}
      {groups.map(([section, fields]) => (
        <section key={section} aria-labelledby={slug(section)}>
          <SectionTitle id={slug(section)}>{section}</SectionTitle>
          {section === "Scoring cascade" && (
            <CascadeScale low={get(values, "scoring_cascade.low_threshold")} high={get(values, "scoring_cascade.high_threshold")} />
          )}
          {fields.map(field => (
            <FieldDisplay key={field.path} field={field} value={get(values, field.path)} />
          ))}
        </section>
      ))}
    </Page>
  );
}
