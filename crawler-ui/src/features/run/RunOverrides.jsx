import { useEffect, useMemo, useState } from "react";
import { getTheme } from "../../theme";
import { Button, Chip, Select, TextInput } from "../common/Form";
import { fetchConfig, fetchConfigDefaults, fetchConfigSchema } from "../../api/client";
import SettingsEditor from "../config/SettingsEditor";
import { buildFields, buildPatch, buildSections, sectionSlug, setIn } from "../config/configModel";
import { presetChanges, shown } from "../config/presetModel";

const theme = getTheme();
const { text } = theme.colors;

/**
 * Settings for one run only. Starts from the saved settings; whatever is
 * changed here is sent as `overrides` with the run and never saved.
 * Reports the patch (or {} ) through `onPatch`.
 */
export default function RunOverrides({ onPatch, disabled }) {
  const [open, setOpen] = useState(false);
  const [schema, setSchema] = useState(null);
  const [saved, setSaved] = useState(null);
  const [defaults, setDefaults] = useState(null);
  const [draft, setDraft] = useState(null);
  const [query, setQuery] = useState("");
  const [advanced, setAdvanced] = useState(false);
  const [section, setSection] = useState("");
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!open || schema) return;
    Promise.all([fetchConfigSchema(), fetchConfig(), fetchConfigDefaults()])
      .then(([s, v, d]) => { setSchema(s); setSaved(v); setDraft(v); setDefaults(d); })
      .catch((e) => setError(e.message));
  }, [open, schema]);

  const fields = useMemo(() => (schema ? buildFields(schema) : []), [schema]);
  const patch = useMemo(() => (draft && saved ? buildPatch(fields, draft, saved) : {}), [fields, draft, saved]);
  useEffect(() => { onPatch(patch); }, [patch, onPatch]);
  const count = Object.keys(fields.length ? flat(patch) : {}).length;
  // What "Clear overrides" will put back: every leaf the draft holds differently from the saved settings.
  const overridden = useMemo(() => (draft && saved ? presetChanges(draft, saved) : []), [draft, saved]);
  const sections = useMemo(() => (schema ? buildSections(schema).map((s) => s.name) : []), [schema]);

  return (
    <section aria-label="Settings for this run" style={{ marginTop: 20 }}>
      <Button variant="quiet" aria-expanded={open} disabled={disabled} onClick={() => setOpen((o) => !o)}>
        {open ? "Hide" : "Override"} settings for this run{count > 0 ? ` (${count} changed)` : ""}
      </Button>
      {open && (
        <div style={{ borderTop: `1px solid ${theme.colors.rowBorder}`, marginTop: 8, paddingTop: 8 }}>
          <p style={{ fontSize: 13, color: theme.colors.text.muted, maxWidth: "60ch" }}>
            Changes here apply to this run only. Edit the saved defaults on the Configuration page.
          </p>
          {error && <p role="alert" style={{ color: theme.colors.accent.red, fontSize: 14 }}>{error}</p>}
          {draft && (
            <>
              <div style={{ display: "flex", gap: 10, margin: "8px 0", alignItems: "center", flexWrap: "wrap" }}>
                <label htmlFor="run-settings-search" style={{ fontSize: 13, fontWeight: 600 }}>Search run settings</label>
                <TextInput id="run-settings-search" type="search" placeholder="e.g. workers" value={query}
                           onChange={(e) => setQuery(e.target.value)} style={{ width: "min(220px, 100%)" }} />
                <label htmlFor="run-settings-section" style={{ fontSize: 13, fontWeight: 600 }}>Section</label>
                <Select id="run-settings-section" value={section} onChange={(e) => setSection(e.target.value)} style={{ width: "min(200px, 100%)" }}>
                  <option value="">All sections</option>
                  {sections.map((name) => <option key={sectionSlug(name)} value={name}>{name}</option>)}
                </Select>
                <Chip pressed={advanced} onClick={() => setAdvanced((v) => !v)}>Advanced</Chip>
                <Button variant="quiet" disabled={overridden.length === 0} onClick={() => setDraft(saved)}>Clear overrides</Button>
              </div>
              {overridden.length > 0 && (
                <div style={{ fontSize: 13, color: text.secondary, margin: "0 0 8px" }}>
                  <div>{overridden.length} setting{overridden.length === 1 ? "" : "s"} overridden for this run. Clearing puts these back:</div>
                  <ul style={{ margin: "4px 0 0", paddingLeft: 18, display: "flex", flexDirection: "column", gap: 2 }}>
                    {overridden.map((c) => (
                      <li key={c.path} style={{ wordBreak: "break-word" }}>
                        {c.label}: {shown(c.to)} → {shown(c.from)}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              <SettingsEditor
                fields={fields} draft={draft} defaults={defaults} saved={saved}
                onChange={(path, v) => setDraft((d) => setIn(d, path, v))}
                query={query} showAdvanced={advanced} section={section || undefined} sectionOrder={sections}
              />
            </>
          )}
        </div>
      )}
    </section>
  );
}

function flat(obj, prefix = "") {
  return Object.entries(obj).reduce((acc, [k, v]) => {
    const p = prefix ? `${prefix}.${k}` : k;
    if (v && typeof v === "object" && !Array.isArray(v)) Object.assign(acc, flat(v, p));
    else acc[p] = v;
    return acc;
  }, {});
}
