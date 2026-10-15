import { useId, useMemo } from "react";
import { getTheme } from "../../theme";
import { SectionTitle } from "../common/Page";
import { Button } from "../common/Form";
import FieldControl from "./FieldControl";
import { badgeStyle, slug } from "./settingsStyle";
import { getIn, groupBySection, matches, sameValue, validateField } from "./configModel";

const theme = getTheme();

function SettingRow({ field, value, defaultValue, saved, onChange, error }) {
  const id = useId();
  const modified = !sameValue(value, defaultValue);
  const changed = !sameValue(value, saved);
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 24,
                  padding: "11px 0", borderBottom: `1px solid ${theme.colors.rowBorder}` }}>
      <div style={{ minWidth: 0 }}>
        <label htmlFor={id} style={{ fontSize: 14, color: theme.colors.text.primary }}>
          {field.title}
          {field.apply === "live" && <span style={badgeStyle} title="Can be changed while a crawl runs">live</span>}
          {field.advanced && <span style={badgeStyle}>advanced</span>}
          {changed && <span style={{ ...badgeStyle, color: theme.colors.text.primary }}>unsaved</span>}
          {!changed && modified && <span style={badgeStyle} title="Differs from the built-in default">changed</span>}
        </label>
        {field.description && (
          <div style={{ fontSize: 13, color: theme.colors.text.muted, marginTop: 2, maxWidth: "58ch" }}>{field.description}</div>
        )}
        {error && <div role="alert" style={{ fontSize: 13, color: theme.colors.accent.red, marginTop: 4 }}>{error}</div>}
        {modified && (
          <Button variant="quiet" style={{ marginTop: 2, padding: 0 }} onClick={() => onChange(defaultValue ?? null)}>
            Reset to default
          </Button>
        )}
      </div>
      <div style={{ flexShrink: 0 }}>
        <FieldControl field={field} value={value} onChange={onChange} id={id} error={error} />
      </div>
    </div>
  );
}

// One row per pipeline, one column per setting, instead of N identical rows.
function PipelinesTable({ fields, draft, defaults, saved, onChange, errors }) {
  const rows = [];
  fields.forEach((f) => {
    let row = rows.find((r) => r.name === f.group);
    if (!row) { row = { name: f.group, cells: {} }; rows.push(row); }
    row.cells[f.key] = f;
  });
  const cols = [...new Set(fields.map((f) => f.key))];
  const th = { textAlign: "left", fontSize: 13, fontWeight: 600, padding: "6px 8px 6px 0", color: theme.colors.text.secondary };
  return (
    <table style={{ width: "100%", borderCollapse: "collapse", marginTop: 8 }}>
      <thead>
        <tr><th style={th}>Pipeline</th>{cols.map((c) => <th key={c} style={th}>{fields.find((f) => f.key === c).title}</th>)}</tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.name} style={{ borderTop: `1px solid ${theme.colors.rowBorder}` }}>
            <td style={{ padding: "8px 8px 8px 0", fontSize: 14 }}>{r.name.replace(/_/g, " ")}</td>
            {cols.map((c) => {
              const f = r.cells[c];
              if (!f) return <td key={c} />;
              const v = getIn(draft, f.path);
              const mod = !sameValue(v, getIn(defaults, f.path));
              return (
                <td key={c} style={{ padding: "6px 8px 6px 0" }}>
                  <FieldControl field={{ ...f, ariaLabel: `${r.name.replace(/_/g, " ")} ${f.title.toLowerCase()}` }} value={v}
                                onChange={(nv) => onChange(f.path, nv)} id={`${f.path}`} error={errors[f.path]} />
                  {mod && !sameValue(v, getIn(saved, f.path)) && <span style={badgeStyle}>unsaved</span>}
                </td>
              );
            })}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/**
 * The schema-driven editor shared by the Configuration page and the
 * per-run override drawer. Fully controlled: the parent owns `draft`.
 */
export default function SettingsEditor({
  fields, draft, defaults, saved, onChange, errors = {}, query = "", showAdvanced = false,
  onResetSection, sectionExtras = {},
}) {
  const sections = useMemo(() => {
    const visible = fields.filter((f) => (showAdvanced || !f.advanced || query) && matches(f, query));
    return groupBySection(visible);
  }, [fields, query, showAdvanced]);

  if (sections.length === 0) {
    return <p style={{ fontSize: 14, color: theme.colors.text.muted }}>No setting matches “{query}”.</p>;
  }
  return sections.map(([section, list]) => {
    const asTable = list.every((f) => f.group) && list.some((f) => f.topKey === "pipelines");
    return (
      <section key={section} aria-labelledby={slug(section)}>
        <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between" }}>
          <SectionTitle id={slug(section)}>{section}</SectionTitle>
          {onResetSection && (
            <Button variant="quiet" onClick={() => onResetSection(section, list)}>Reset section</Button>
          )}
        </div>
        {sectionExtras[section]?.(draft)}
        {asTable ? (
          <PipelinesTable fields={list} draft={draft} defaults={defaults} saved={saved} onChange={onChange} errors={errors} />
        ) : list.map((f) => (
          <SettingRow
            key={f.path} field={f} value={getIn(draft, f.path)} defaultValue={getIn(defaults, f.path)}
            saved={getIn(saved, f.path)} onChange={(v) => onChange(f.path, v)}
            error={errors[f.path] ?? validateField(f, getIn(draft, f.path))}
          />
        ))}
      </section>
    );
  });
}
