import { useCallback, useEffect, useRef, useState } from "react";
import { getTheme } from "../../theme";
import { Button, TextInput } from "../common/Form";
import { SectionTitle } from "../common/Page";
import {
  applyPreset, deletePreset, exportConfig, fetchConfig, fetchPresets, replaceConfig, savePreset, validateConfig,
} from "../../api/client";
import { presetChanges, shown } from "./presetModel";

const theme = getTheme();

/** Named presets plus JSON import/export of the stored settings. Applying a
 *  preset or an import replaces the stored settings; `onChanged` hands the
 *  new effective config back to the page. */
export default function PresetsPanel({ onChanged, dirty }) {
  const [presets, setPresets] = useState({ builtin: {}, descriptions: {}, user: {} });
  const [current, setCurrent] = useState(null);
  const [open, setOpen] = useState(null);
  const [name, setName] = useState("");
  const [msg, setMsg] = useState(null);
  const fileRef = useRef(null);

  const load = useCallback(async () => {
    try { setPresets(await fetchPresets()); } catch (e) { setMsg({ ok: false, text: e.message }); }
  }, []);
  useEffect(() => {
    let cancelled = false;
    fetchPresets()
      .then((p) => !cancelled && setPresets(p))
      .catch((e) => !cancelled && setMsg({ ok: false, text: e.message }));
    fetchConfig().then((c) => !cancelled && setCurrent(c)).catch(() => {});
    return () => { cancelled = true; };
  }, []);

  const guard = async (fn, okText) => {
    try {
      const out = await fn();
      setMsg({ ok: true, text: okText });
      return out;
    } catch (e) {
      setMsg({ ok: false, text: e.message });
      return undefined;
    }
  };

  const apply = async (n) => {
    if (dirty && !window.confirm("Applying a preset replaces your stored settings and drops unsaved edits. Continue?")) return;
    const cfg = await guard(() => applyPreset(n), `Preset “${n}” applied. It takes effect from the next crawl.`);
    if (cfg) { onChanged(cfg); setCurrent(cfg); }
  };

  const save = async () => {
    const n = name.trim();
    if (!n) return;
    if (await guard(() => savePreset(n), `Saved the stored settings as “${n}”.`)) {
      setName("");
      load();
    }
  };

  const remove = async (n) => {
    if (await guard(() => deletePreset(n), `Preset “${n}” deleted.`)) load();
  };

  const download = async () => {
    const stored = await guard(() => exportConfig(), "Exported the stored settings.");
    if (!stored) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(stored, null, 2)], { type: "application/json" }));
    const a = document.createElement("a");
    a.href = url; a.download = "crawlviz-settings.json"; a.click();
    URL.revokeObjectURL(url);
  };

  const upload = async (file) => {
    if (!file) return;
    let values;
    try { values = JSON.parse(await file.text()); } catch { setMsg({ ok: false, text: "That file is not valid JSON." }); return; }
    const check = await guard(() => validateConfig(values), "");
    if (!check) return;
    if (!check.valid) {
      setMsg({ ok: false, text: check.errors.map((e) => `${e.path}: ${e.message}`).join("; ") });
      return;
    }
    if (dirty && !window.confirm("Importing replaces your stored settings and drops unsaved edits. Continue?")) return;
    const cfg = await guard(() => replaceConfig(values), `Imported ${file.name}.`);
    if (cfg) onChanged(cfg);
  };

  const row = { display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", padding: "6px 0",
                borderBottom: `1px solid ${theme.colors.rowBorder}` };
  const group = (title, list, deletable) => Object.keys(list).length > 0 && (
    <div style={{ marginBottom: 12 }}>
      <div style={{ fontSize: 13, color: theme.colors.text.muted, marginBottom: 4 }}>{title}</div>
      {Object.keys(list).map((n) => (
        <div key={n} style={row}>
          <span style={{ flex: 1, fontSize: 14 }}>
            {n}
            {presets.descriptions?.[n] && (
              <span style={{ display: "block", fontSize: 13, color: theme.colors.text.secondary }}>{presets.descriptions[n]}</span>
            )}
          </span>
          <Button variant="quiet" aria-expanded={open === n} onClick={() => setOpen(open === n ? null : n)}
                  aria-label={`Show what preset ${n} changes`}>What changes</Button>
          <Button onClick={() => apply(n)} aria-label={`Apply preset ${n}`}>Apply</Button>
          {deletable && <Button variant="quiet" onClick={() => remove(n)} aria-label={`Delete preset ${n}`}>Delete</Button>}
          {open === n && (
            <ul aria-label={`Changes made by ${n}`} style={{ flexBasis: "100%", margin: "4px 0 0", paddingLeft: 18, fontSize: 13 }}>
              {(() => {
                const changes = presetChanges(list[n], current);
                if (changes.length === 0) return <li>Nothing: your settings already match this preset.</li>;
                return changes.map((c) => <li key={c.path}>{c.label}: {shown(c.from)} → <strong>{shown(c.to)}</strong></li>);
              })()}
            </ul>
          )}
        </div>
      ))}
    </div>
  );

  return (
    <section aria-labelledby="cfg-presets">
      <SectionTitle id="cfg-presets">Presets and files</SectionTitle>
      {group("Built in", presets.builtin, false)}
      {group("Yours", presets.user, true)}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginTop: 8 }}>
        <TextInput aria-label="New preset name" placeholder="Preset name" value={name}
                   onChange={(e) => setName(e.target.value)} style={{ width: 200 }} />
        <Button onClick={save} disabled={!name.trim()}>Save stored settings as preset</Button>
        <span style={{ flex: 1 }} />
        <Button onClick={download}>Export JSON</Button>
        <Button onClick={() => fileRef.current?.click()}>Import JSON</Button>
        <input ref={fileRef} type="file" accept="application/json,.json" hidden aria-label="Import settings file"
               onChange={(e) => { upload(e.target.files?.[0]); e.target.value = ""; }} />
      </div>
      {msg && msg.text && (
        <p role="status" style={{ fontSize: 13, marginTop: 8, color: msg.ok ? theme.colors.text.secondary : theme.colors.accent.red }}>
          {msg.text}
        </p>
      )}
    </section>
  );
}
