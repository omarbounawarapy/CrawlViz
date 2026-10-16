import { useRef, useState } from "react";
import { getTheme } from "../../theme";
import { Button, TextInput, Select } from "../common/Form";
import Stepper from "./Stepper";
import NumberField from "./NumberField";
import { nextChoice } from "../common/choiceKeys";

const theme = getTheme();
const { text } = theme.colors;

function NumberInput({ field, value, onChange, id, invalid }) {
  return (
    <NumberField
      id={id} value={value} onChange={onChange} nullable={Boolean(field.nullable)} unit={field.unit}
      invalid={invalid} label={field.ariaLabel} integer={field.type === "integer"}
    />
  );
}

// A 0-1 fraction is shown and typed as a percentage; the stored value stays 0-1.
function Slider({ field, value, onChange, id, invalid }) {
  const min = field.minimum ?? 0;
  const max = field.maximum ?? 1;
  const fraction = min === 0 && max === 1 && !field.unit;
  if (fraction) {
    const pct = Math.round(Number(value ?? 0) * 100);
    return (
      <span style={{ display: "inline-flex", alignItems: "center", gap: 12 }}>
        <input
          type="range" min={0} max={100} step={1} value={pct}
          aria-label={`${field.title} (percent)`} onChange={(e) => onChange(Number(e.target.value) / 100)}
          style={{ width: 150 }}
        />
        <NumberInput
          field={{ ...field, type: "integer", minimum: 0, maximum: 100, unit: "%", step: 1 }}
          value={pct} id={id} invalid={invalid} onChange={(v) => onChange(v === "" ? "" : Number(v) / 100)}
        />
      </span>
    );
  }
  const step = field.step ?? (field.type === "integer" || max > 10 ? 1 : 0.01);
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 12 }}>
      <input
        type="range" min={min} max={max} step={step} value={Number(value ?? min)}
        aria-label={field.title} onChange={(e) => onChange(Number(e.target.value))}
        style={{ width: 150 }}
      />
      <NumberInput field={field} value={value} onChange={onChange} id={id} invalid={invalid} />
    </span>
  );
}

// "No limit" switch plus a stepper that appears while a limit is set.
function LimitControl({ field, value, onChange, id }) {
  const step = field.step ?? 100;
  const unlimited = value === null || value === undefined;
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 12 }}>
      <label style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 14, cursor: "pointer" }}>
        <input type="checkbox" checked={unlimited} aria-label={`${field.ariaLabel ?? field.title} no limit`}
               onChange={(e) => onChange(e.target.checked ? null : step)} />
        No limit
      </label>
      {!unlimited && (
        <Stepper
          id={id} label={field.ariaLabel ?? field.title} value={Number(value)}
          min={Math.min(step, Number(value))} max={field.maximum ?? Infinity} step={step} onChange={onChange}
        />
      )}
    </span>
  );
}

// Two named choices of a boolean (or any value), shown side by side.
function Segmented({ field, value, onChange, id }) {
  const options = field.options ?? [];
  const refs = useRef([]);
  return (
    <div id={id} role="radiogroup" aria-label={field.title}
         style={{ display: "inline-flex", border: `1px solid ${theme.colors.background.border}`, borderRadius: theme.radii.sm, overflow: "hidden" }}>
      {options.map((o, i) => {
        const on = o.value === value;
        return (
          <button key={String(o.value)} type="button" role="radio" aria-checked={on} tabIndex={on ? 0 : -1}
                  ref={(el) => { refs.current[i] = el; }}
                  onKeyDown={(e) => {
                    const n = nextChoice(e, i, options.length);
                    if (n === null) return;
                    onChange(options[n].value);
                    refs.current[n]?.focus();
                  }}
                  onClick={() => onChange(o.value)}
                  style={{ height: 32, padding: "0 14px", fontSize: 13, fontWeight: on ? 700 : 500, border: "none",
                           background: on ? text.primary : "transparent",
                           color: on ? theme.colors.background.panel : text.secondary }}>
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

function Toggle({ value, onChange, id }) {
  return (
    <label style={{ display: "inline-flex", alignItems: "center", gap: 8, cursor: "pointer", fontSize: 14 }}>
      <input id={id} type="checkbox" checked={Boolean(value)} onChange={(e) => onChange(e.target.checked)} />
      {value ? "On" : "Off"}
    </label>
  );
}

// Add/remove rows of name -> value; `numeric` coerces values to numbers.
function KeyValueEditor({ value, onChange, numeric, keyLabel, valueLabel, id }) {
  const entries = Object.entries(value ?? {});
  const [draftKey, setDraftKey] = useState("");
  const [draftVal, setDraftVal] = useState("");
  const set = (k, v) => onChange({ ...(value ?? {}), [k]: numeric ? Number(v) : v });
  const rename = (oldK, newK) => {
    if (!newK || newK === oldK) return;
    const next = {};
    entries.forEach(([k, v]) => { next[k === oldK ? newK : k] = v; });
    onChange(next);
  };
  const remove = (k) => {
    const next = { ...(value ?? {}) };
    delete next[k];
    onChange(next);
  };
  const add = () => {
    const k = draftKey.trim();
    if (!k || (numeric && Number.isNaN(Number(draftVal)))) return;
    set(k, draftVal);
    setDraftKey(""); setDraftVal("");
  };
  const sum = numeric ? entries.reduce((a, [, v]) => a + Number(v || 0), 0) : null;
  return (
    <div id={id} style={{ display: "flex", flexDirection: "column", gap: 6, alignItems: "flex-end", textAlign: "left" }}>
      {entries.map(([k, v]) => (
        <div key={k} style={{ display: "flex", gap: 6 }}>
          <TextInput aria-label={`${keyLabel} ${k}`} defaultValue={k} style={{ width: 170 }}
                     onBlur={(e) => rename(k, e.target.value.trim())} />
          <TextInput aria-label={`${valueLabel} for ${k}`} value={v} type={numeric ? "number" : "text"}
                     step={numeric ? "any" : undefined} style={{ width: numeric ? 90 : 220 }}
                     onChange={(e) => set(k, e.target.value)} />
          <Button variant="quiet" aria-label={`Remove ${k}`} onClick={() => remove(k)}>Remove</Button>
        </div>
      ))}
      <div style={{ display: "flex", gap: 6 }}>
        <TextInput aria-label={`New ${keyLabel}`} placeholder={keyLabel} value={draftKey}
                   style={{ width: 170 }} onChange={(e) => setDraftKey(e.target.value)} />
        <TextInput aria-label={`New ${valueLabel}`} placeholder={valueLabel} value={draftVal}
                   type={numeric ? "number" : "text"} step={numeric ? "any" : undefined}
                   style={{ width: numeric ? 90 : 220 }} onChange={(e) => setDraftVal(e.target.value)} />
        <Button onClick={add}>Add</Button>
      </div>
      {numeric && <span style={{ fontSize: 13, color: text.muted }}>Sum {Math.round(sum * 1000) / 1000}</span>}
    </div>
  );
}

/** One control chosen by the schema's ui_widget. */
export default function FieldControl({ field, value, onChange, id, error }) {
  const invalid = Boolean(error);
  switch (field.widget) {
    case "slider":
      return <Slider field={field} value={value} onChange={onChange} id={id} invalid={invalid} />;
    case "stepper":
      return (
        <Stepper id={id} label={field.ariaLabel ?? field.title} value={Number(value ?? field.minimum ?? 0)}
                 min={field.minimum ?? 0} max={field.maximum ?? Infinity} step={field.step ?? 1}
                 unit={field.unit} onChange={onChange} />
      );
    case "limit":
      return <LimitControl field={field} value={value} onChange={onChange} id={id} />;
    case "segmented":
      return <Segmented field={field} value={value} onChange={onChange} id={id} />;
    case "toggle":
      return <Toggle value={value} onChange={onChange} id={id} />;
    case "select":
      return (
        <Select id={id} value={value ?? ""} onChange={(e) => onChange(e.target.value)} style={{ width: 200 }}>
          {(field.options ?? []).map((o) => <option key={o} value={o}>{o}</option>)}
          {value && !(field.options ?? []).includes(value) && <option value={value}>{value}</option>}
        </Select>
      );
    case "headers":
      return <KeyValueEditor id={id} value={value} onChange={onChange} keyLabel="Header" valueLabel="Value" />;
    case "stringmap":
      return <KeyValueEditor id={id} value={value} onChange={onChange} keyLabel="Name" valueLabel="Value" />;
    case "textarea":
      return (
        <textarea id={id} value={value ?? ""} rows={6} aria-invalid={invalid || undefined}
                  onChange={(e) => onChange(e.target.value)}
                  style={{ width: 420, maxWidth: "100%", font: "inherit", fontSize: 13, padding: 8,
                           border: `1px solid ${invalid ? theme.colors.accent.red : theme.colors.rowBorder}`,
                           borderRadius: 4, background: "transparent", color: text.primary, resize: "vertical" }} />
      );
    case "weights":
      return <KeyValueEditor id={id} value={value} onChange={onChange} numeric keyLabel="Feature" valueLabel="Weight" />;
    case "text":
      return <TextInput id={id} value={value ?? ""} invalid={invalid} style={{ width: 320 }}
                        onChange={(e) => onChange(e.target.value)} />;
    default:
      return <NumberInput field={field} value={value} onChange={onChange} id={id} invalid={invalid} />;
  }
}
