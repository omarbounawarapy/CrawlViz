import { useId, useMemo } from "react";
import { getTheme } from "../../theme";
import { SectionTitle } from "../common/Page";
import { Button } from "../common/Form";
import FieldControl from "./FieldControl";
import RangeSlider from "./RangeSlider";
import { badgeStyle, slug } from "./settingsStyle";
import {
  getIn, groupBySection, isActive, matches, rangeOf, sameValue, validateField,
} from "./configModel";

const theme = getTheme();

function SettingRow({ field, value, defaultValue, saved, onChange, error, active = true, control }) {
  const id = useId();
  const modified = !sameValue(value, defaultValue);
  const changed = !sameValue(value, saved);
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 24,
                  padding: "11px 0", borderBottom: `1px solid ${theme.colors.rowBorder}`,
                  opacity: active ? 1 : 0.45 }}>
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
        {control ?? <FieldControl field={field} value={value} onChange={onChange} id={id} error={error} />}
      </div>
    </div>
  );
}

// Both cut-offs of a pair on one track; the thumbs cannot cross.
function RangeRow({ low, high, draft, defaults, saved, onChange, errors }) {
  const lv = getIn(draft, low.path);
  const hv = getIn(draft, high.path);
  const percent = low.unit === "%";
  const format = (v) => (percent ? `${Math.round(v)} %` : String(Math.round(v * 100) / 100));
  const err = errors[low.path] ?? errors[high.path] ?? validateField(low, lv) ?? validateField(high, hv);
  const pair = {
    ...low,
    title: `${low.title} and ${high.title.toLowerCase()}`,
    description: percent
      ? `${low.description} ${high.description} Measured against the page's own links: 0 % is its weakest link, 100 % its strongest.`
      : `${low.description} ${high.description}`,
  };
  const reset = () => { onChange(low.path, getIn(defaults, low.path)); onChange(high.path, getIn(defaults, high.path)); };
  return (
    <SettingRow
      field={pair} value={[lv, hv]} defaultValue={[getIn(defaults, low.path), getIn(defaults, high.path)]}
      saved={[getIn(saved, low.path), getIn(saved, high.path)]} error={err} active={isActive(low, draft)}
      onChange={reset}
      control={
        <RangeSlider
          low={Number(lv)} high={Number(hv)} min={low.minimum ?? 0} max={high.maximum ?? 1}
          step={low.step ?? 0.01} format={format} invalid={Boolean(err)}
          lowLabel={low.title} highLabel={high.title}
          onChange={(l, h) => { if (l !== lv) onChange(low.path, l); if (h !== hv) onChange(high.path, h); }}
        />
      }
    />
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
  onResetSection, sectionExtras = {}, section, sectionOrder = [], sectionHelp = {}, onOpenSection,
}) {
  const sections = useMemo(() => {
    const visible = fields.filter((f) => (showAdvanced || !f.advanced || query) && matches(f, query));
    const grouped = groupBySection(visible, sectionOrder);
    // A named section is shown alone, unless a search is looking across all of them.
    return section && !query ? grouped.filter(([name]) => name === section) : grouped;
  }, [fields, query, showAdvanced, section, sectionOrder]);

  if (sections.length === 0) {
    return (
      <p style={{ fontSize: 14, color: theme.colors.text.muted }}>
        {query ? `No setting matches “${query}”.` : "Nothing to show in this section."}
      </p>
    );
  }
  return sections.map(([name, list]) => {
    const asTable = list.every((f) => f.group) && list.some((f) => f.topKey === "pipelines");
    return (
      <section key={name} aria-labelledby={slug(name)}>
        <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between" }}>
          <SectionTitle id={slug(name)}>{name}</SectionTitle>
          {query && onOpenSection && (
            <Button variant="quiet" onClick={() => onOpenSection(name)}>Open section</Button>
          )}
          {!query && onResetSection && (
            <Button variant="quiet" onClick={() => onResetSection(name, list)}>Reset section</Button>
          )}
        </div>
        {!query && sectionHelp[name] && (
          <p style={{ fontSize: 14, color: theme.colors.text.secondary, maxWidth: "62ch", margin: "0 0 8px" }}>
            {sectionHelp[name]}
          </p>
        )}
        {sectionExtras[name]?.(draft)}
        {asTable ? (
          <PipelinesTable fields={list} draft={draft} defaults={defaults} saved={saved} onChange={onChange} errors={errors} />
        ) : list.map((f) => {
          const pair = rangeOf(f, list);
          if (pair === null) return null;
          if (pair) {
            return (
              <RangeRow key={f.path} low={pair.low} high={pair.high} draft={draft} defaults={defaults}
                        saved={saved} onChange={onChange} errors={errors} />
            );
          }
          return (
            <SettingRow
              key={f.path} field={f} value={getIn(draft, f.path)} defaultValue={getIn(defaults, f.path)}
              saved={getIn(saved, f.path)} onChange={(v) => onChange(f.path, v)}
              error={errors[f.path] ?? validateField(f, getIn(draft, f.path))}
              active={isActive(f, draft)}
            />
          );
        })}
      </section>
    );
  });
}
