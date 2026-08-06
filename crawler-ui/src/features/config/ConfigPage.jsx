import { useEffect, useState } from "react";
import { getTheme } from "../../theme";
import { createComponentStyles } from "../../theme/components";
import { fetchConfigSchema, fetchConfig } from "../../api/client";

const theme = getTheme();
const S = createComponentStyles(theme);

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

function FieldDisplay({ field, value }) {
  const widget = field.ui_widget;

  return (
    <div style={{ padding: "10px 0", borderBottom: `1px solid ${theme.colors.rowBorder}` }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 12 }}>
        <div style={{ fontSize: theme.typography.size.xs, color: theme.colors.text.primary }}>{field.title}</div>
        <div style={{ fontSize: theme.typography.size.sm, color: theme.colors.accent.blue, fontVariantNumeric: "tabular-nums", flexShrink: 0 }}>
          {String(value ?? field.default)}
        </div>
      </div>
      {(widget === "slider" || (field.minimum != null && field.maximum != null)) && (
        <div style={{ ...S.breakdownBarTrack, marginTop: 6 }}>
          <div style={S.breakdownBarFill(
            `${Math.max(0, Math.min(100, ((value ?? field.default) - (field.minimum ?? 0)) / ((field.maximum ?? 1) - (field.minimum ?? 0)) * 100))}%`,
            theme.colors.accent.blueDim,
          )} />
        </div>
      )}
      {widget === "select" && field.ui_options && (
        <div style={{ display: "flex", gap: 6, marginTop: 6 }}>
          {field.ui_options.map(opt => (
            <span key={opt} style={S.pill(opt === (value ?? field.default) ? "blue" : "muted")}>{opt}</span>
          ))}
        </div>
      )}
      <div style={{ fontSize: theme.typography.size.xxs, color: theme.colors.text.muted, marginTop: 4 }}>
        {field.description}
      </div>
    </div>
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

  return (
    <div style={S.panel}>
      <div style={S.panelHeader}>
        <div>
          <div style={S.panelHeaderTitle}>Configuration</div>
          <div style={S.panelHeaderSubtitle}>What assumptions is this crawl operating under?</div>
        </div>
        <span style={S.pill("gold")}>read-only</span>
      </div>

      <div style={S.panelScroll}>
        {error && (
          <div style={S.emptyState}>
            Couldn't reach the control API ({error}). Is the backend running on the configured VITE_API_BASE_URL?
          </div>
        )}
        {!error && !schema && (
          <div style={S.emptyState}>Loading configuration schema…</div>
        )}
        {schema && values && Object.entries(groupFields(schema)).map(([section, fields]) => (
          <div key={section} style={{ ...S.sectionCard, marginBottom: 16 }}>
            <div style={S.sectionCardTitle}>{section}</div>
            {fields.map(field => (
              <FieldDisplay key={field.path} field={field} value={get(values, field.path)} />
            ))}
          </div>
        ))}
        {schema && values && (
          <div style={{ fontSize: theme.typography.size.xxs, color: theme.colors.text.muted, marginTop: 4 }}>
            This surface is generated from config/runtime_config.py's Pydantic schema, not hand-copied —
            editing support (validated, with inline errors) is scoped as follow-up work; see
            docs/V2_ARCHITECTURE.md roadmap item 18.
          </div>
        )}
      </div>
    </div>
  );
}
