import { useEffect, useMemo, useState } from "react";
import { getTheme } from "../../theme";
import { Button, Chip, TextInput } from "../common/Form";
import { fetchConfig, fetchConfigDefaults, fetchConfigSchema } from "../../api/client";
import SettingsEditor from "../config/SettingsEditor";
import { buildFields, buildPatch, isEmptyPatch, setIn } from "../config/configModel";

const theme = getTheme();

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
              <div style={{ display: "flex", gap: 10, margin: "8px 0", alignItems: "center" }}>
                <TextInput aria-label="Search run settings" placeholder="Search settings" value={query}
                           onChange={(e) => setQuery(e.target.value)} style={{ width: 220 }} />
                <Chip pressed={advanced} onClick={() => setAdvanced((v) => !v)}>Advanced</Chip>
                <Button variant="quiet" disabled={isEmptyPatch(patch)} onClick={() => setDraft(saved)}>Clear overrides</Button>
              </div>
              <SettingsEditor
                fields={fields} draft={draft} defaults={defaults} saved={saved}
                onChange={(path, v) => setDraft((d) => setIn(d, path, v))}
                query={query} showAdvanced={advanced}
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
