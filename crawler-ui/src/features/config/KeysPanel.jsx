import { useCallback, useEffect, useState } from "react";
import { getTheme } from "../../theme";
import { Button, ConfirmButton, Field, Select, TextInput } from "../common/Form";
import { SectionTitle } from "../common/Page";
import { addKey, fetchKeys, fetchProviders, removeKey } from "../../api/client";

const theme = getTheme();

/** API keys per provider. The backend only ever returns the last four
 *  characters; a pasted key is sent once and never shown again. */
export default function KeysPanel() {
  const [keys, setKeys] = useState({});
  const [providers, setProviders] = useState({});
  const [provider, setProvider] = useState("");
  const [secret, setSecret] = useState("");
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [k, p] = await Promise.all([fetchKeys(), fetchProviders()]);
      setKeys(k);
      setProviders(p);
      setProvider((cur) => cur || Object.keys(p)[0] || "");
    } catch (e) {
      setMsg({ ok: false, text: e.message });
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const add = async () => {
    if (!provider || !secret.trim() || busy) return;
    setBusy(true);
    try {
      await addKey(provider, secret.trim());
      setSecret("");
      setMsg({ ok: true, text: `Key added to ${provider}. A running crawl picks it up immediately.` });
      await load();
    } catch (e) {
      setMsg({ ok: false, text: e.message });
    } finally {
      setBusy(false);
    }
  };

  const remove = async (prov, id) => {
    try {
      await removeKey(prov, id);
      setMsg({ ok: true, text: `Key removed from ${prov}.` });
      await load();
    } catch (e) {
      setMsg({ ok: false, text: e.message });
    }
  };

  const names = Object.keys(providers);
  return (
    <section aria-labelledby="cfg-api-keys">
      <SectionTitle id="cfg-api-keys">API keys</SectionTitle>
      <p style={{ fontSize: 13, color: theme.colors.text.muted, maxWidth: "60ch", marginBottom: 8 }}>
        Stored in keys.json on the machine running the backend. Only the last four characters are shown. Keys rotate
        round-robin within a provider.
      </p>
      {names.map((name) => (
        <div key={name} style={{ padding: "10px 0", borderBottom: `1px solid ${theme.colors.rowBorder}` }}>
          <h3 style={{ fontSize: 14, fontWeight: 600, margin: 0 }}>
            {name}{" "}
            <span style={{ fontWeight: 400, color: theme.colors.text.muted }}>
              {(keys[name] ?? []).length} key{(keys[name] ?? []).length === 1 ? "" : "s"}
              {providers[name].models.length > 0 && ` · used with ${providers[name].models.join(", ")}`}
            </span>
          </h3>
          {(keys[name] ?? []).map((k) => (
            <div key={k.id} style={{ display: "flex", alignItems: "center", gap: 12, fontSize: 14, marginTop: 4 }}>
              <code>
                <span aria-hidden="true">••••</span>
                <span className="sr-only">Key ending </span>
                {k.last4}
              </code>
              {/* A removed key cannot be shown again, so removing takes a second press (WCAG 3.3.4). */}
              <ConfirmButton
                label="Remove"
                confirmLabel="Confirm remove"
                aria-label={`Remove key ending ${k.last4} from ${name}`}
                onConfirm={() => remove(name, k.id)}
              />
            </div>
          ))}
        </div>
      ))}
      <div style={{ display: "flex", gap: "0 8px", marginTop: 14, flexWrap: "wrap", alignItems: "flex-end" }}>
        <div style={{ width: "min(160px, 100%)" }}>
          <Field label="Provider">
            <Select value={provider} onChange={(e) => setProvider(e.target.value)}>
              {names.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        <div style={{ width: "min(320px, 100%)" }}>
          <Field label="API key">
            <TextInput
              type="password"
              autoComplete="off"
              placeholder="Paste the key"
              value={secret}
              onChange={(e) => setSecret(e.target.value)}
            />
          </Field>
        </div>
        <Button variant="primary" disabled={!secret.trim() || busy} onClick={add} style={{ marginBottom: 14 }}>
          Add key
        </Button>
      </div>
      {msg && (
        <p
          role="status"
          style={{ fontSize: 13, marginTop: 8, color: msg.ok ? theme.colors.text.secondary : theme.colors.accent.red }}
        >
          {msg.text}
        </p>
      )}
    </section>
  );
}
