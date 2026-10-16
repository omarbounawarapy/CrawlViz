import { useCallback, useEffect, useMemo, useState } from "react";
import { getTheme } from "../../theme";
import { Page } from "../common/Page";
import { Button, Chip, ConfirmButton, TextInput } from "../common/Form";
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
import FetchExplainers from "./explainers/FetchExplainers";
import ExploreLevers from "./explainers/ExploreLevers";
import CostReadout from "./CostReadout";
import ProviderTable from "./ProviderTable";
import PipelineFlow from "./PipelineFlow";
import { SECTION_GROUPS } from "./intentGroups";
import GoalGuide from "./GoalGuide";
import StrategyCards from "./explainers/StrategyCards";
import { TopKExample, ClusterExample, ContextExample } from "./explainers/TopKExample";
import SettingsEditor from "./SettingsEditor";
import KeysPanel from "./KeysPanel";
import { useRoute } from "../../hooks/useRoute";
import {
  buildFields, buildPatch, buildSections, changedSections, getIn, groupBySection, isEmptyPatch, livePatch, matches, schemaGaps,
  sectionSlug, setIn, validateField,
} from "./configModel";
import { primeGlossary } from "./glossary";

const theme = getTheme();

// Edited inside StrategyCards (or PromptStudio) instead of as plain rows: the default strategy is chosen
// by its card, so a second dropdown for the same setting would be two controls for one value.
const HIDDEN = [
  "priority.aggressive_weights", "priority.balanced_weights", "priority.exploration_weights",
  "scoring_cascade.default_priority_strategy",
  "prompts.scoring_system", "prompts.scoring_rules", "prompts.strategy_contexts",
];

const START = { name: "Start here", slug: "start" };
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
  const [queues, setQueues] = useState(null);
  const { path, navigate } = useRoute();
  const wanted = path.split("/")[2];

  useEffect(() => {
    let cancelled = false;
    const poll = () => crawlStatus().then((s) => {
      if (cancelled) return;
      setRunning(Boolean(s.running));
      setQueues(s.queues ?? null);
    }).catch(() => {});
    poll();
    const t = setInterval(poll, 4000);
    return () => { cancelled = true; clearInterval(t); };
  }, []);

  useEffect(() => {
    let cancelled = false;
    Promise.all([fetchConfigSchema(), fetchConfig(), fetchConfigDefaults()])
      .then(([schemaRes, valuesRes, defaultsRes]) => {
        if (cancelled) return;
        primeGlossary(schemaRes.ui_glossary);
        setSchema(schemaRes);
        setSaved(valuesRes);
        setDraft(valuesRes);
        setDefaults(defaultsRes);
      })
      .catch((err) => !cancelled && setError(err.message));
    return () => { cancelled = true; };
  }, []);

  const fields = useMemo(() => (schema ? buildFields(schema) : []), [schema]);
  const gaps = useMemo(() => (schema ? schemaGaps(schema, fields) : []), [schema, fields]);
  const patch = useMemo(() => (draft && saved ? buildPatch(fields, draft, saved) : {}), [fields, draft, saved]);
  const dirty = !isEmptyPatch(patch);
  const unsavedIn = useMemo(() => changedSections(fields, patch, []), [fields, patch]);
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
  // How many rows a search finds, announced as it is typed (WCAG 4.1.3).
  const searchCount = useMemo(
    () => (query ? fields.filter((f) => matches(f, query) && (showAdvanced || !f.advanced || query)).length : 0),
    [fields, query, showAdvanced],
  );

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
  // Every section with a setting is listed, so a section that is all advanced is named, with the reason
  // it is empty, rather than missing from the nav.
  const sections = useMemo(() => groupBySection(fields, order).map(([s]) => s), [fields, order]);
  const entries = useMemo(
    () => [START, ...sections.map((name) => ({ name, slug: sectionSlug(name) })), PRESETS, KEYS],
    [sections],
  );
  const current = entries.find((e) => e.slug === wanted) ?? entries[0];
  const open = (entry) => navigate(`/config/${entry.slug}`);
  const openSection = (name) => { setQuery(""); navigate(`/config/${sectionSlug(name)}`); };

  // Narrow screens swap the side index for this select. Choosing opens the section, and the hint
  // says so before the choice is made (WCAG 3.2.2).
  const sectionPicker = (
    <div className="config-section-select" style={{ marginBottom: 16 }}>
      <label htmlFor="config-section" style={{ display: "block", fontSize: 13, fontWeight: 600, marginBottom: 4 }}>Section</label>
      <select id="config-section" aria-describedby="config-section-hint" value={current.slug}
              onChange={(e) => { setQuery(""); navigate(`/config/${e.target.value}`); }}
              style={{ minHeight: 44, width: "100%", fontSize: 15, padding: "0 10px", borderRadius: theme.radii.sm,
                       border: `1px solid ${theme.colors.control}`, background: theme.colors.background.panel, color: theme.colors.text.primary }}>
        {entries.map((entry) => <option key={entry.slug} value={entry.slug}>{entry.name}</option>)}
      </select>
      <div id="config-section-hint" style={{ fontSize: 13, color: theme.colors.text.muted, marginTop: 4 }}>Choosing a section opens it.</div>
    </div>
  );

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
                   display: "inline-block", minHeight: 24, fontSize: active ? 16 : 14, fontWeight: active ? 700 : 400,
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
    "Scoring cascade": (d) => (
      <>
        <CascadeFunnel cfg={d.scoring_cascade} />
        <CostReadout cascade={d.scoring_cascade} nlp={d.nlp} llm={d.llm} prompts={d.prompts} />
        <p style={{ fontSize: 13, color: theme.colors.text.secondary, margin: "0 0 12px", maxWidth: "62ch" }}>
          Queue order when a blueprint picks no strategy: <strong style={{ color: theme.colors.text.primary }}>{d.scoring_cascade.default_priority_strategy}</strong>.
          It is chosen with the cards on the Priority page.{" "}
          <Button variant="quiet" style={{ padding: 0 }} onClick={() => openSection("Priority")}>Open Priority</Button>
        </p>
        <ExploreLevers onOpen={openSection} />
      </>
    ),
    LLM: (d) => <CostReadout cascade={d.scoring_cascade} nlp={d.nlp} llm={d.llm} prompts={d.prompts} priced />,
    Fetch: (d) => (
      <FetchExplainers cfg={d.fetch} workers={d.pipelines.requests.workers} maxRetries={d.retries.max_request_retries}
                       onChange={change} />
    ),
    Pipelines: (d) => <PipelineFlow pipelines={d.pipelines} batchSize={d.export.batch_size} queues={queues} />,
    Providers: (d) => <ProviderTable endpoints={d.providers.endpoints} />,
    Prompts: (d) => <PromptStudio prompts={d.prompts} defaults={defaults?.prompts ?? d.prompts} onChange={change} />,
    Priority: (d) => (
      <StrategyCards priority={d.priority} defaults={defaults?.priority}
                     defaultStrategy={d.scoring_cascade.default_priority_strategy} onChange={change} />
    ),
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
      lead="Every setting the crawler reads. Changes save to the backend and apply from the next crawl. Settings marked live can also change a crawl in progress."
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
      {gaps.length > 0 && (
        <p role="alert" style={{ fontSize: 14, color: theme.colors.accent.red, maxWidth: "62ch", margin: "0 0 12px" }}>
          The API server is older than this page and is missing {gaps.join(", ")}. Restart it (make dev-backend) and reload; until then some controls and explanations are missing.
        </p>
      )}
      {schema && draft && (
        <>
          {sectionPicker}
          <div style={{ position: "sticky", top: 0, zIndex: 2, background: theme.colors.background.primary,
                        padding: "8px 0", display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap",
                        borderBottom: `1px solid ${theme.colors.rowBorder}` }}>
            <label htmlFor="config-search" style={{ fontSize: 13, fontWeight: 600 }}>Search settings</label>
            <TextInput id="config-search" type="search" placeholder="e.g. user agent" value={query}
                       aria-describedby={query ? "config-search-count" : undefined}
                       onChange={(e) => setQuery(e.target.value)} style={{ width: "min(220px, 100%)" }} />
            <span id="config-search-count" role="status" className="sr-only">
              {query ? `${searchCount} ${searchCount === 1 ? "setting matches" : "settings match"}` : ""}
            </span>
            <Chip pressed={showAdvanced} onClick={() => setShowAdvanced((v) => !v)}>Advanced</Chip>
            <span style={{ flex: 1 }} />
            {dirty && (
              <span style={{ fontSize: 13, color: theme.colors.text.secondary }}>
                Unsaved in {unsavedIn.join(", ")}. Changes in every section are saved together.
              </span>
            )}
            <Button variant="quiet" disabled={!dirty} onClick={() => { setDraft(saved); setErrors({}); setStatus(null); }}>Revert</Button>
            {running && (
              <Button disabled={!hasLive || blocked || saving} onClick={applyLive}>
                Apply live
              </Button>
            )}
            <Button variant="primary" disabled={!dirty || blocked || saving} onClick={save}>
              {saving ? "Saving…" : dirty ? "Save changes" : "Saved"}
            </Button>
          </div>
          {running && (
            <p style={{ fontSize: 13, color: theme.colors.text.secondary, margin: "8px 0 0", maxWidth: "62ch" }}>
              A crawl is running. Settings marked live can be applied to it now with Apply live; the rest apply from the next crawl.
            </p>
          )}
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
          {current.slug === START.slug && !query && <GoalGuide draft={draft} fields={fields} onChange={change} />}
          {(query || (current.slug !== START.slug && current.slug !== PRESETS.slug && current.slug !== KEYS.slug)) && (
          <SettingsEditor
            fields={fields} draft={draft} defaults={defaults} saved={saved} onChange={change}
            errors={errors} query={query} showAdvanced={showAdvanced} groups={SECTION_GROUPS}
            onResetSection={resetSection} sectionExtras={extras} fieldExtras={fieldExtras}
            hiddenPaths={HIDDEN}
            section={current.name} sectionOrder={order} sectionHelp={help} onOpenSection={openSection}
          />
          )}
          {!query && current.slug === PRESETS.slug && (
            <PresetsPanel dirty={dirty} fields={fields}
                          onChanged={(cfg) => { setSaved(cfg); setDraft(cfg); setErrors({}); }} />
          )}
          {!query && current.slug === KEYS.slug && <KeysPanel />}
          {!query && current.slug === PRESETS.slug && (
            <div style={{ marginTop: 40 }}>
              <ConfirmButton label="Reset every setting to defaults" confirmLabel="Confirm: reset every setting"
                             onConfirm={resetAll} />
            </div>
          )}
        </>
      )}
    </Page>
  );
}
