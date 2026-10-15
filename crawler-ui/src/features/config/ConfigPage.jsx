import { useCallback, useEffect, useMemo, useState } from "react";
import { getTheme } from "../../theme";
import { Page } from "../common/Page";
import { Button, Chip, TextInput } from "../common/Form";
import {
  fetchConfigSchema, fetchConfig, fetchConfigDefaults, saveConfig, resetConfig,
  crawlStatus, patchLiveConfig,
} from "../../api/client";
import PresetsPanel from "./PresetsPanel";
import CascadeFunnel from "./explainers/CascadeFunnel";
import HeaderPresets from "./HeaderPresets";
import PromptStudio from "./PromptStudio";
import SuggestionsStrip from "./SuggestionsStrip";
import { suggest } from "./suggestions";
import BackoffChart from "./explainers/BackoffChart";
import StrategyCards from "./explainers/StrategyCards";
import { TopKExample, ClusterExample, ContextExample } from "./explainers/TopKExample";
import SettingsEditor from "./SettingsEditor";
import KeysPanel from "./KeysPanel";
import { useRoute } from "../../hooks/useRoute";
import {
  buildFields, buildPatch, buildSections, getIn, groupBySection, isEmptyPatch, livePatch, sectionSlug,
  setIn, validateField,
} from "./configModel";

const theme = getTheme();

// Edited inside StrategyCards instead of as three key/value tables.
const HIDDEN = [
  "priority.aggressive_weights", "priority.balanced_weights", "priority.exploration_weights",
  "prompts.scoring_system", "prompts.scoring_rules", "prompts.strategy_contexts",
];

const PRESETS = { name: "Presets and files", slug: "presets" };
const KEYS = { name: "API keys", slug: "api-keys" };

export default function ConfigPage() {
  const [dismissed, setDismissed] = useState([]);
  const [schema, setSchema] = useState(null);
  const [saved, setSaved] = useState(null);
  const [defaults, setDefaults] = useState(null);
  const [draft, setDraft] = useState(null);
  const [error, setError] = useState(null);
  const [errors, setErrors] = useState({});
  const [status, setStatus] = useState(null);
  const [saving, setSaving] = useState(false);
  const [query, setQuery] = useState("");
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [running, setRunning] = useState(false);
  const { path, navigate } = useRoute();
  const wanted = path.split("/")[2];

  useEffect(() => {
    let cancelled = false;
    const poll = () => crawlStatus().then((s) => !cancelled && setRunning(Boolean(s.running))).catch(() => {});
    poll();
    const t = setInterval(poll, 4000);
    return () => { cancelled = true; clearInterval(t); };
  }, []);

  useEffect(() => {
    let cancelled = false;
    Promise.all([fetchConfigSchema(), fetchConfig(), fetchConfigDefaults()])
      .then(([schemaRes, valuesRes, defaultsRes]) => {
        if (cancelled) return;
        setSchema(schemaRes);
        setSaved(valuesRes);
        setDraft(valuesRes);
        setDefaults(defaultsRes);
      })
      .catch((err) => !cancelled && setError(err.message));
    return () => { cancelled = true; };
  }, []);

  const fields = useMemo(() => (schema ? buildFields(schema) : []), [schema]);
  const patch = useMemo(() => (draft && saved ? buildPatch(fields, draft, saved) : {}), [fields, draft, saved]);
  const dirty = !isEmptyPatch(patch);
  const clientErrors = useMemo(() => {
    const out = {};
    if (!draft) return out;
    fields.forEach((f) => {
      const e = validateField(f, getIn(draft, f.path));
      if (e) out[f.path] = e;
    });
    return out;
  }, [fields, draft]);
  const blocked = Object.keys(clientErrors).length > 0;

  useEffect(() => {
    if (!dirty) return undefined;
    const warn = (e) => { e.preventDefault(); e.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  const change = useCallback((path, value) => {
    setDraft((d) => setIn(d, path, value));
    setStatus(null);
    setErrors((e) => (e[path] ? { ...e, [path]: undefined } : e));
  }, []);

  const save = async () => {
    if (!dirty || blocked || saving) return;
    setSaving(true);
    setStatus(null);
    try {
      const next = await saveConfig(patch);
      setSaved(next);
      setDraft(next);
      setErrors({});
      setStatus({ ok: true, text: "Saved. New values apply from the next crawl." });
    } catch (e) {
      const byPath = {};
      (e.errors ?? []).forEach((x) => { byPath[x.path] = x.message; });
      setErrors(byPath);
      setStatus({ ok: false, text: e.message });
    } finally {
      setSaving(false);
    }
  };

  const live = useMemo(() => livePatch(fields, patch), [fields, patch]);
  const hasLive = !isEmptyPatch(live);

  const applyLive = async () => {
    try {
      await patchLiveConfig(live);
      await save();
      setStatus({ ok: true, text: "Saved and applied to the running crawl." });
    } catch (e) {
      const byPath = {};
      (e.errors ?? []).forEach((x) => { byPath[x.path] = x.message; });
      setErrors(byPath);
      setStatus({ ok: false, text: e.message });
    }
  };

  const resetSection = async (section, list) => {
    // Drafts only: the section returns to defaults and is saved with the rest.
    list.forEach((f) => setDraft((d) => setIn(d, f.path, getIn(defaults, f.path))));
    setStatus({ ok: true, text: `${section} set to defaults. Save to apply.` });
  };

  const resetAll = async () => {
    try {
      const next = await resetConfig();
      setSaved(next);
      setDraft(next);
      setErrors({});
      setStatus({ ok: true, text: "All settings reset to the built-in defaults." });
    } catch (e) {
      setStatus({ ok: false, text: e.message });
    }
  };

  const guide = useMemo(() => (schema ? buildSections(schema) : []), [schema]);
  const order = useMemo(() => guide.map((g) => g.name), [guide]);
  const help = useMemo(() => Object.fromEntries(guide.map((g) => [g.name, g.help])), [guide]);
  const sections = useMemo(() => groupBySection(fields, order).map(([s]) => s), [fields, order]);
  const entries = useMemo(
    () => [...sections.map((name) => ({ name, slug: sectionSlug(name) })), PRESETS, KEYS],
    [sections],
  );
  const current = entries.find((e) => e.slug === wanted) ?? entries[0];
  const open = (entry) => navigate(`/config/${entry.slug}`);
  const openSection = (name) => { setQuery(""); navigate(`/config/${sectionSlug(name)}`); };

  const index = sections.length > 0 && (
    <nav aria-label="Configuration sections" style={{ width: 200, flexShrink: 0, position: "sticky", top: 0, alignSelf: "flex-start", paddingTop: 76 }}>
      <ul style={{ listStyle: "none", display: "flex", flexDirection: "column", gap: 10 }}>
        {entries.map((entry) => {
          const active = !query && entry.slug === current.slug;
          return (
            <li key={entry.slug}>
              <a href={`#/config/${entry.slug}`} aria-current={active ? "page" : undefined}
                 onClick={(e) => { e.preventDefault(); setQuery(""); open(entry); }}
                 style={{
                   display: "inline-block", fontSize: active ? 16 : 14, fontWeight: active ? 700 : 400,
                   color: active ? theme.colors.text.primary : theme.colors.text.secondary, textDecoration: "none",
                   paddingBottom: 2, borderBottom: `2px solid ${active ? theme.colors.accent.blue : "transparent"}`,
                 }}>
                {entry.name}
              </a>
            </li>
          );
        })}
      </ul>
    </nav>
  );

  // Explainers draw from the live draft; the ones that edit a field own its plain row.
  const extras = {
    "Scoring cascade": (d) => <CascadeFunnel cfg={d.scoring_cascade} />,
    Fetch: (d) => <BackoffChart cfg={d.fetch} />,
    Prompts: (d) => <PromptStudio prompts={d.prompts} defaults={defaults?.prompts ?? d.prompts} onChange={change} />,
    Priority: (d) => <StrategyCards priority={d.priority} defaults={defaults?.priority} onChange={change} />,
  };
  const applyHeaders = (values) => Object.entries(values).forEach(([k, v]) => change(`fetch.${k}`, v));
  const fieldExtras = {
    "fetch.respect_robots": (d) => <HeaderPresets fetch={d.fetch} onApply={applyHeaders} />,
    "nlp.target_top_k": (d) => <TopKExample k={d.nlp.target_top_k} />,
    "nlp.cluster_min_samples": (d) => <ClusterExample eps={d.nlp.cluster_eps} minSamples={d.nlp.cluster_min_samples} />,
    "nlp.link_context_length": (d) => <ContextExample length={d.nlp.link_context_length} />,
  };

  return (
    <Page
      title="Configuration"
      lead="Every tunable of the crawler. Changes are saved on the backend and apply from the next crawl; settings marked live can also be pushed to a crawl in progress."
      aside={index || null}
    >
      {error && (
        <div role="alert" style={{ maxWidth: "60ch" }}>
          <p style={{ fontSize: 14, color: theme.colors.accent.red, marginBottom: 12 }}>
            Could not load the configuration. The control API did not answer ({error}). Start it with make dev-backend, then try again.
          </p>
          <Button onClick={() => window.location.reload()}>Try again</Button>
        </div>
      )}
      {!error && !schema && <p style={{ fontSize: 14, color: theme.colors.text.muted }}>Loading configuration…</p>}
      {schema && draft && (
        <>
          <div style={{ position: "sticky", top: 0, zIndex: 2, background: theme.colors.background.primary,
                        padding: "8px 0", display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap",
                        borderBottom: `1px solid ${theme.colors.rowBorder}` }}>
            <TextInput aria-label="Search settings" placeholder="Search settings" value={query}
                       onChange={(e) => setQuery(e.target.value)} style={{ width: 220 }} />
            <Chip pressed={showAdvanced} onClick={() => setShowAdvanced((v) => !v)}>Advanced</Chip>
            <span style={{ flex: 1 }} />
            <Button variant="quiet" disabled={!dirty} onClick={() => { setDraft(saved); setErrors({}); setStatus(null); }}>Revert</Button>
            {running && (
              <Button disabled={!hasLive || blocked || saving} onClick={applyLive}
                      title="Pushes the changed live settings to the crawl in progress, then saves">
                Apply live
              </Button>
            )}
            <Button variant="primary" disabled={!dirty || blocked || saving} onClick={save}>
              {saving ? "Saving…" : dirty ? "Save changes" : "Saved"}
            </Button>
          </div>
          {status && (
            <p role="status" style={{ fontSize: 13, margin: "8px 0", color: status.ok ? theme.colors.text.secondary : theme.colors.accent.red }}>
              {status.text}
            </p>
          )}
          {!query && (
            <SuggestionsStrip
              items={suggest(draft, dismissed).filter((s) => s.section === current.name)}
              onApply={(s) => { s.fix.set.forEach(([p, v]) => change(p, v)); setDismissed((d) => [...d, s.id]); }}
              onDismiss={(id) => setDismissed((d) => [...d, id])}
            />
          )}
          {(query || (current.slug !== PRESETS.slug && current.slug !== KEYS.slug)) && (
          <SettingsEditor
            fields={fields} draft={draft} defaults={defaults} saved={saved} onChange={change}
            errors={errors} query={query} showAdvanced={showAdvanced}
            onResetSection={resetSection} sectionExtras={extras} fieldExtras={fieldExtras}
            hiddenPaths={HIDDEN}
            section={current.name} sectionOrder={order} sectionHelp={help} onOpenSection={openSection}
          />
          )}
          {!query && current.slug === PRESETS.slug && (
            <PresetsPanel dirty={dirty} onChanged={(cfg) => { setSaved(cfg); setDraft(cfg); setErrors({}); }} />
          )}
          {!query && current.slug === KEYS.slug && <KeysPanel />}
          {!query && current.slug === PRESETS.slug && (
            <div style={{ marginTop: 40 }}>
              <Button variant="danger" onClick={resetAll}>Reset every setting to defaults</Button>
            </div>
          )}
        </>
      )}
    </Page>
  );
}
