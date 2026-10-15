import { useState } from "react";
import { getTheme } from "../../theme";
import { Button, TextInput, Select } from "../common/Form";

const theme = getTheme();
const { text } = theme.colors;

const NUM_WIDTH = 110;

function NumberInput({ field, value, onChange, id, invalid }) {
  const [raw, setRaw] = useState(null); // text while typing, so "0." and "" survive
  const shown = raw ?? (value === null || value === undefined ? "" : String(value));
  const step = field.type === "integer" ? 1 : "any";
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
      <TextInput
        id={id} type="number" inputMode="decimal" step={step} min={field.minimum} max={field.maximum}
        value={shown} invalid={invalid} aria-invalid={invalid || undefined}
        aria-label={field.ariaLabel}
        style={{ width: NUM_WIDTH, textAlign: "right" }}
        onChange={(e) => {
          const t = e.target.value;
          setRaw(t);
          if (t === "") onChange(field.nullable ? null : "");
          else if (!Number.isNaN(Number(t))) onChange(Number(t));
        }}
        onBlur={() => setRaw(null)}
      />
      {field.unit && <span style={{ fontSize: 13, color: text.muted, minWidth: 18 }}>{field.unit}</span>}
    </span>
  );
}

function Slider({ field, value, onChange, id, invalid }) {
  const min = field.minimum ?? 0;
  const max = field.maximum ?? 1;
  const step = field.type === "integer" || max > 10 ? 1 : 0.01;
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
