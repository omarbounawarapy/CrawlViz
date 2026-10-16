import { Fragment, useId, useMemo } from "react";
import { getTheme } from "../../theme";
import { SectionTitle } from "../common/Page";
import { Button } from "../common/Form";
import FieldControl from "./FieldControl";
import RangeSlider from "./RangeSlider";
import { Explain } from "./Term";
import { Hint } from "../common/Hint";
import EmptyState from "../common/EmptyState";
import { badgeStyle, slug } from "./settingsStyle";
import { stageName } from "./pipelineNames";
import {
  getIn, groupBySection, isActive, matches, rangeOf, sameValue, validateField,
} from "./configModel";
import ScrollRegion from "../common/ScrollRegion";

const theme = getTheme();

// Widgets that are not a native form control: the row's label names them with aria-labelledby,
// since <label for> can only point at an input, select or textarea.
const NON_NATIVE = new Set(["segmented", "stepper", "headers", "stringmap", "weights", "limit"]);

function SettingRow({ field, value, defaultValue, saved, onChange, error, active = true, control }) {
  const id = useId();
  const labelId = `${id}-label`;
  const descId = `${id}-desc`;
  const native = !control && !NON_NATIVE.has(field.widget);
  const modified = !sameValue(value, defaultValue);
  const changed = !sameValue(value, saved);
  const hasDesc = Boolean(field.description || field.effect || !active);
  const errId = `${id}-err`;
  // The error is read with the control, after its description.
  const describedBy = [hasDesc && descId, error && errId].filter(Boolean).join(" ") || undefined;
  return (
    <div className="setting-row" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 24,
                  padding: "11px 0", borderBottom: `1px solid ${theme.colors.rowBorder}` }}>
      <div style={{ minWidth: 0 }}>
        {/* Badges sit beside the label, not in it: a button inside a label would become the label's control. */}
        <div style={{ display: "flex", alignItems: "baseline", flexWrap: "wrap", gap: "0 8px" }}>
          <label id={labelId} htmlFor={native ? id : undefined} style={{ fontSize: 14, color: theme.colors.text.primary }}>{field.title}</label>
          {field.apply === "live" && <Hint text="Can be changed while a crawl runs"><span style={badgeStyle}>live</span></Hint>}
          {field.advanced && <span style={badgeStyle}>advanced</span>}
          {changed && <span style={{ ...badgeStyle, color: theme.colors.text.primary }}>unsaved</span>}
          {!changed && modified && <Hint text="Differs from the built-in default"><span style={badgeStyle}>changed</span></Hint>}
        </div>
        {hasDesc && (
          <div id={descId}>
            {/* An inactive row keeps full-contrast text and says why it does nothing (no fading: WCAG 1.4.3). */}
            {!active && (
              <div style={{ fontSize: 13, fontWeight: 600, color: theme.colors.text.secondary, marginTop: 2 }}>
                Not used with the current settings.
              </div>
            )}
            {field.description && (
              <div style={{ fontSize: 13, color: theme.colors.text.muted, marginTop: 2, maxWidth: "58ch" }}><Explain text={field.description} /></div>
            )}
            {field.effect && (
              <div style={{ fontSize: 13, color: theme.colors.text.secondary, marginTop: 2, maxWidth: "58ch" }}>
                <span style={{ color: theme.colors.text.muted }}>Effect: </span><Explain text={field.effect} />
              </div>
            )}
          </div>
        )}
        {error && <div id={errId} role="alert" style={{ fontSize: 13, color: theme.colors.accent.red, marginTop: 4 }}>{error}</div>}
        {modified && (
          <Button variant="quiet" style={{ marginTop: 2, padding: 0 }} onClick={() => onChange(defaultValue ?? null)}>
            Reset to default
          </Button>
        )}
      </div>
      <div className="setting-control" style={{ flexShrink: 0, maxWidth: "100%" }}>
        {control
          ? control(labelId, describedBy)
          : <FieldControl field={field} value={value} onChange={onChange} id={id} error={error}
                          labelledBy={labelId} describedBy={describedBy} />}
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
      control={(labelId, descId) => (
        <RangeSlider
          low={Number(lv)} high={Number(hv)} min={low.minimum ?? 0} max={high.maximum ?? 1}
          step={low.step ?? 0.01} format={format} invalid={Boolean(err)}
          lowLabel={low.title} highLabel={high.title} labelledBy={labelId} describedBy={descId}
          onChange={(l, h) => { if (l !== lv) onChange(low.path, l); if (h !== hv) onChange(high.path, h); }}
        />
      )}
    />
  );
}

// Two weights that always make 100 %: one slider from pure NLP to pure LLM.
function SplitRow({ nlp, llm, draft, defaults, saved, onChange, errors }) {
  const a = Number(getIn(draft, nlp.path)) || 0;
  const b = Number(getIn(draft, llm.path)) || 0;
  const share = a + b > 0 ? Math.round((b / (a + b)) * 100) : 50;
  const err = errors[nlp.path] ?? errors[llm.path];
  const set = (x) => { onChange(nlp.path, 100 - x); onChange(llm.path, x); };
  const field = {
    ...nlp, title: "NLP and LLM share of the priority",
    description: "How much a link's priority comes from the cheap NLP score and how much from the LLM's judgement. The two always add up to 100 %.",
  };
  return (
    <SettingRow
      field={field} value={[a, b]} defaultValue={[getIn(defaults, nlp.path), getIn(defaults, llm.path)]}
      saved={[getIn(saved, nlp.path), getIn(saved, llm.path)]} error={err}
      onChange={() => { onChange(nlp.path, getIn(defaults, nlp.path)); onChange(llm.path, getIn(defaults, llm.path)); }}
      control={(labelId, descId) => (
        <div style={{ width: "min(300px, 100%)" }}>
          <input type="range" min={0} max={100} step={1} value={share} style={{ width: "100%" }}
                 aria-labelledby={labelId} aria-describedby={descId}
                 aria-valuetext={`${100 - share} percent NLP, ${share} percent LLM`}
                 onChange={(e) => set(Number(e.target.value))} />
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, color: theme.colors.text.secondary }}>
            <span>Pure NLP</span>
            <span className="num" style={{ color: theme.colors.text.primary, fontWeight: 600 }}>
              NLP {100 - share} % · LLM {share} %
            </span>
            <span>Pure LLM</span>
          </div>
        </div>
      )}
    />
  );
}

// The heading of an intent group: what it is for, in one line.
function GroupHeading({ group }) {
  return (
    <div style={{ marginTop: 16, paddingTop: 10, borderTop: `1px solid ${theme.colors.rowBorder}` }}>
      <h3 style={{ fontSize: 15, fontWeight: 600, margin: "0 0 2px", color: theme.colors.text.primary }}>{group.title}</h3>
      {group.hint && <p style={{ fontSize: 13, color: theme.colors.text.muted, margin: "0 0 6px" }}>{group.hint}</p>}
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
    <ScrollRegion label="Pipelines settings table">
    <table style={{ width: "100%", borderCollapse: "collapse", marginTop: 8 }}>
      <thead>
        <tr><th scope="col" style={th}>Pipeline</th>{cols.map((c) => <th scope="col" key={c} style={th}>{fields.find((f) => f.key === c).title}</th>)}</tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.name} style={{ borderTop: `1px solid ${theme.colors.rowBorder}` }}>
            <th scope="row" style={{ padding: "8px 8px 8px 0", fontSize: 14, fontWeight: 400, textAlign: "left" }}>{stageName(r.name)}</th>
            {cols.map((c) => {
              const f = r.cells[c];
              if (!f) return <td key={c} />;
              const v = getIn(draft, f.path);
              const mod = !sameValue(v, getIn(defaults, f.path));
              return (
                <td key={c} style={{ padding: "6px 8px 6px 0" }}>
                  <FieldControl field={{ ...f, ariaLabel: `${stageName(r.name)} ${f.title.toLowerCase()}` }} value={v}
                                onChange={(nv) => onChange(f.path, nv)} id={`${f.path}`} error={errors[f.path]} />
                  {mod && !sameValue(v, getIn(saved, f.path)) && <span style={badgeStyle}>unsaved</span>}
                </td>
              );
            })}
          </tr>
        ))}
      </tbody>
    </table>
    </ScrollRegion>
  );
}

/**
 * The schema-driven editor shared by the Configuration page and the
 * per-run override drawer. Fully controlled: the parent owns `draft`.
 */
export default function SettingsEditor({
  fields, draft, defaults, saved, onChange, errors = {}, query = "", showAdvanced = false,
  onResetSection, sectionExtras = {}, fieldExtras = {}, hiddenPaths = [], section, sectionOrder = [], sectionHelp = {}, onOpenSection,
  groups = {},
}) {
  // Rows in group order, each group's first row tagged with the group. Searching is a flat list.
  function orderRows(list, name) {
    const spec = query ? null : groups[name];
    if (!spec) return list.map((f) => ({ f, group: null }));
    const out = [];
    const placed = new Set();
    spec.forEach((g) => {
      const rows = list.filter((f) => g.paths.includes(f.path));
      rows.forEach((f, i) => { placed.add(f.path); out.push({ f, group: i === 0 ? g : null }); });
    });
    const rest = list.filter((f) => !placed.has(f.path));
    rest.forEach((f, i) => out.push({ f, group: i === 0 ? { title: "Other settings", hint: null } : null }));
    return out;
  }
  const sections = useMemo(() => {
    // An explainer that edits a field itself hides its plain row, except while searching.
    const visible = fields.filter((f) => (showAdvanced || !f.advanced || query) && matches(f, query)
      && (query || !hiddenPaths.includes(f.path)));
    const grouped = groupBySection(visible, sectionOrder);
    // A named section is shown alone, unless a search is looking across all of them.
    if (!section || query) return grouped;
    const shown = grouped.filter(([name]) => name === section);
    // A section whose every row is edited by its explainer has no plain rows left.
    return shown.length === 0 && sectionExtras[section] ? [[section, []]] : shown;
  }, [fields, query, showAdvanced, section, sectionOrder, hiddenPaths, sectionExtras]);

  // The explainer's pictures go above the first plain row, after any range or split rows
  // they read from (the NLP/LLM split sits above the strategy cards on Priority).
  function rowsWithExtras(list, name) {
    const extras = !query && sectionExtras[name] ? sectionExtras[name](draft) : null;
    const ordered = orderRows(list, name);
    const firstPlain = ordered.findIndex(({ f }) => rangeOf(f, list, "split") === undefined);
    const rows = ordered.map(({ f, group }, i) => {
      const row = renderRow(f, list);
      return (
        <Fragment key={`row-${f.path}`}>
          {group && <GroupHeading group={group} />}
          {i === firstPlain && extras}
          {row}
        </Fragment>
      );
    });
    return (
      <>
        {rows}
        {firstPlain === -1 && extras}
      </>
    );
  }

  function renderRow(f, list) {
    const split = rangeOf(f, list, "split");
    if (split === null) return null;
    if (split) {
      return (
        <SplitRow key={f.path} nlp={split.low} llm={split.high} draft={draft} defaults={defaults}
                  saved={saved} onChange={onChange} errors={errors} />
      );
    }
    const pair = rangeOf(f, list);
    if (pair === null) return null;
    if (pair) {
      return (
        <RangeRow key={f.path} low={pair.low} high={pair.high} draft={draft} defaults={defaults}
                  saved={saved} onChange={onChange} errors={errors} />
      );
    }
    return (
      <Fragment key={f.path}>
        <SettingRow
          field={f} value={getIn(draft, f.path)} defaultValue={getIn(defaults, f.path)}
          saved={getIn(saved, f.path)} onChange={(v) => onChange(f.path, v)}
          error={errors[f.path] ?? validateField(f, getIn(draft, f.path))}
          active={isActive(f, draft)}
        />
        {!query && fieldExtras[f.path]?.(draft)}
      </Fragment>
    );
  }

  if (sections.length === 0) {
    // Only advanced rows left: say so, instead of an empty page.
    const allAdvanced = !query && section && fields.some((f) => f.section === section && f.advanced)
      && !fields.some((f) => f.section === section && !f.advanced);
    const reason = query ? `No setting matches “${query}”.`
      : allAdvanced ? `Every setting in ${section} is advanced. Turn on Advanced to see them.`
      : "Nothing to show in this section.";
    return <EmptyState>{reason}</EmptyState>;
  }
  return sections.map(([name, list]) => {
    const asTable = list.length > 0 && list.every((f) => f.group) && list.some((f) => f.topKey === "pipelines");
    return (
      <section key={name} aria-labelledby={slug(name)}>
        <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", flexWrap: "wrap", gap: "0 12px" }}>
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
            <Explain text={sectionHelp[name]} />
          </p>
        )}
        {asTable ? (
          <>
            {!query && sectionExtras[name]?.(draft)}
            <PipelinesTable fields={list} draft={draft} defaults={defaults} saved={saved} onChange={onChange} errors={errors} />
          </>
        ) : (
          <>
            {rowsWithExtras(list, name)}
          </>
        )}
      </section>
    );
  });
}
