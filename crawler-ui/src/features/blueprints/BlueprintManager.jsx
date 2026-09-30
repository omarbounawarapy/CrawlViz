/**
 * Blueprints: pick a saved blueprint, edit it as a form or as raw JSON, save.
 *
 * A blueprint says where a crawl starts, what counts as relevant and when it
 * stops. The data model (constants, validation, form <-> blueprint
 * conversion) lives in blueprintModel.js; shared controls in common/Form.jsx.
 */

import { useState, useEffect, useCallback, useMemo } from "react";
import {
  fetchTemplates, fetchTemplate, createTemplate, updateTemplate, deleteTemplate,
} from "../../api/client";
import { getTheme } from "../../theme";
import { Page, SectionTitle, Row } from "../common/Page";
import { Field, TextInput, Select, Grid, Button, Tabs, TabPanel, Chip, Group, Status } from "../common/Form";
import {
  STRATEGIES, TRANSFORMS_WITH_CONFIG, ALL_TRANSFORMS, EXPORT_TYPES, FIELD_TYPES, EXPANSION_STYLES,
  PROFILES, DEFAULT_BLUEPRINT, validateBlueprint, blueprintToForm, formToBlueprint,
} from "./blueprintModel";

const theme = getTheme();
const { text, background, accent } = theme.colors;

const BACKENDS = ["openrouter", "openai", "anthropic", "gemini", "nvidia", "groq"];
const RUN_PRESELECT_KEY = "crawlviz.run.blueprint";

// Each field's DOM id, so validation errors can focus the field they name.
const bpId = (...parts) => ["bp", ...parts].join("-");

function BackendList() {
  return <datalist id="bp-backends">{BACKENDS.map((b) => <option key={b} value={b} />)}</datalist>;
}

// ─── transforms ──────────────────────────────────────────────────────────────

function TransformPipeline({ transforms, onChange }) {
  const add = () => onChange([...transforms, { type: "strip", paramValue: "" }]);
  const rm  = (i) => onChange(transforms.filter((_, idx) => idx !== i));
  const upd = (i, patch) => onChange(transforms.map((t, idx) => (idx === i ? { ...t, ...patch } : t)));

  return (
    <div>
      {transforms.map((t, i) => {
        const cfg = TRANSFORMS_WITH_CONFIG[t.type];
        return (
          <div key={i} style={{ display: "grid", gridTemplateColumns: "150px 1fr auto", gap: 8, alignItems: "center", marginBottom: 8 }}>
            <Select aria-label={`Transform ${i + 1}`} value={t.type} onChange={(e) => {
              const nc = TRANSFORMS_WITH_CONFIG[e.target.value];
              upd(i, { type: e.target.value, paramValue: nc ? String(nc.default) : "" });
            }}>
              {ALL_TRANSFORMS.map((tr) => <option key={tr} value={tr}>{tr}</option>)}
            </Select>
            {cfg
              ? <TextInput aria-label={cfg.label} type={cfg.inputType} placeholder={cfg.label} value={t.paramValue} onChange={(e) => upd(i, { paramValue: e.target.value })} />
              : <span style={{ fontSize: 13, color: text.muted }}>No setting</span>}
            <Button variant="quiet" aria-label={`Remove transform ${i + 1}`} onClick={() => rm(i)}>Remove</Button>
          </div>
        );
      })}
      <Button onClick={add}>Add transform</Button>
    </div>
  );
}

// ─── extraction ──────────────────────────────────────────────────────────────

function ManualFields({ fields, onChange, errorFor }) {
  const add = () => onChange([...fields, { name: "", selector: "", fieldType: "scalar", exportType: "text", transforms: [] }]);
  const rm  = (i) => onChange(fields.filter((_, idx) => idx !== i));
  const upd = (i, patch) => onChange(fields.map((f, idx) => (idx === i ? { ...f, ...patch } : f)));

  return (
    <div>
      {fields.map((f, i) => (
        <Group key={i} title={f.name || `Field ${i + 1}`} onRemove={() => rm(i)}>
          <Grid>
            <Field label="Name"><TextInput value={f.name} placeholder="e.g. title" onChange={(e) => upd(i, { name: e.target.value })} /></Field>
            <Field label="XPath selector" id={bpId("field", i, "selector")} error={errorFor(bpId("field", i, "selector"))}>
              {(a) => <TextInput {...a} invalid={!!errorFor(a.id)} value={f.selector} placeholder="//h1[@id='firstHeading']" onChange={(e) => upd(i, { selector: e.target.value })} />}
            </Field>
          </Grid>
          <Grid>
            <Field label="Type">
              <Select value={f.fieldType} onChange={(e) => upd(i, { fieldType: e.target.value })}>
                {FIELD_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
              </Select>
            </Field>
            <Field label="Stored as">
              <Select value={f.exportType} onChange={(e) => upd(i, { exportType: e.target.value })}>
                {EXPORT_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
              </Select>
            </Field>
          </Grid>
          <Field label="Transforms" hint="Applied in order to each extracted value.">
            {(a) => <div id={a.id}><TransformPipeline transforms={f.transforms} onChange={(transforms) => upd(i, { transforms })} /></div>}
          </Field>
        </Group>
      ))}
      <Button onClick={add}>Add field</Button>
    </div>
  );
}

function ProfileExtraction({ profileId, checklist, onProfileChange, onChecklistChange }) {
  const fields = PROFILES[profileId]?.fields || [];
  const toggle    = (f) => onChecklistChange(checklist.includes(f) ? checklist.filter((x) => x !== f) : [...checklist, f]);
  const toggleAll = () => onChecklistChange(checklist.length === fields.length ? [] : [...fields]);

  return (
    <div>
      <Field label="Site profile" hint="Selectors and transforms are filled in for you.">
        {(a) => (
          <Select {...a} value={profileId} onChange={(e) => {
            onProfileChange(e.target.value);
            onChecklistChange([...PROFILES[e.target.value].fields]);
          }}>
            {Object.entries(PROFILES).map(([id, p]) => <option key={id} value={id}>{p.label}</option>)}
          </Select>
        )}
      </Field>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
        <span style={{ fontSize: 13, fontWeight: 600, color: text.primary }} id="bp-profile-fields">Fields to keep</span>
        <Button variant="quiet" onClick={toggleAll}>{checklist.length === fields.length ? "Clear all" : "Select all"}</Button>
      </div>
      <div role="group" aria-labelledby="bp-profile-fields" style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        {fields.map((f) => <Chip key={f} pressed={checklist.includes(f)} onClick={() => toggle(f)}>{f}</Chip>)}
      </div>
    </div>
  );
}

// ─── the form ────────────────────────────────────────────────────────────────

const STEPS = [
  ["about", "About"], ["sources", "Sources"], ["relevance", "Relevance"],
  ["extraction", "Extraction"], ["limits", "Limits"], ["review", "Review"],
];
const STEP_SECTIONS = {
  about: ["basics"], sources: ["seeds", "domains"], relevance: ["scoring", "expansion"],
  extraction: ["extraction"], limits: ["stop"], review: [],
};
// Which step holds the field an error id names.
function stepOf(id = "") {
  if (/^bp-(blueprint_id|id|target_topic)$/.test(id)) return "about";
  if (/^bp-(seed|domain)/.test(id)) return "sources";
  if (/^bp-(strategy|scoring|expansion|num-descriptions|llm)/.test(id)) return "relevance";
  if (/^bp-(field|extraction)/.test(id)) return "extraction";
  if (/^bp-(max_|no_progress)/.test(id)) return "limits";
  return null;
}


function BlueprintForm({ form, setForm, errorFor, step }) {
  const has = (sec) => STEP_SECTIONS[step].includes(sec);
  const set = (patch) => setForm((f) => ({ ...f, ...patch }));
  const err = (id) => errorFor(id);
  const field = (label, id, node, extra) => (
    <Field label={label} id={id} error={err(id)} {...extra}>
      {(a) => node(a, !!err(id))}
    </Field>
  );

  const updSeed = (i, patch) => set({ seeds: form.seeds.map((s, idx) => (idx === i ? { ...s, ...patch } : s)) });
  const updDom  = (i, patch) => set({ domains: form.domains.map((d, idx) => (idx === i ? { ...d, ...patch } : d)) });

  return (
    <div>
      <BackendList />

      {has("basics") && (
      <section aria-labelledby="sec-basics">
        <SectionTitle id="sec-basics">Basics</SectionTitle>
        <Grid>
          {field("Blueprint ID", bpId("blueprint_id"), (a, bad) => <TextInput {...a} invalid={bad} value={form.blueprint_id} placeholder="my_topic_crawl" onChange={(e) => set({ blueprint_id: e.target.value })} />, { hint: "A short name for this blueprint." })}
          {field("Run ID", bpId("id"), (a, bad) => <TextInput {...a} invalid={bad} value={form.id} placeholder="run_1" onChange={(e) => set({ id: e.target.value })} />, { hint: "Labels the crawls it produces." })}
        </Grid>
        {field("Target topic", bpId("target_topic"), (a, bad) => <TextInput {...a} invalid={bad} value={form.target_topic} placeholder="e.g. Type 2 diabetes" onChange={(e) => set({ target_topic: e.target.value })} />, { hint: "The crawler scores every link against this." })}
      </section>
      )}

      {has("seeds") && (
      <section aria-labelledby="sec-seeds">
        <SectionTitle id="sec-seeds">Starting pages</SectionTitle>
        <div id="bp-seeds" tabIndex={-1}>
          {form.seeds.map((s, i) => (
            <Group key={i} title={`Page ${i + 1}`} onRemove={form.seeds.length > 1 ? () => set({ seeds: form.seeds.filter((_, idx) => idx !== i) }) : undefined}>
              <Grid>
                {field("URL", bpId("seed", i, "url"), (a, bad) => <TextInput {...a} invalid={bad} value={s.url} placeholder="https://example.org/wiki/Topic" onChange={(e) => updSeed(i, { url: e.target.value })} />)}
                {field("Domain", bpId("seed", i, "domain"), (a, bad) => <TextInput {...a} invalid={bad} value={s.domain} placeholder="https://example.org" onChange={(e) => updSeed(i, { domain: e.target.value })} />)}
              </Grid>
            </Group>
          ))}
        </div>
        <Button onClick={() => set({ seeds: [...form.seeds, { url: "", domain: "" }] })}>Add starting page</Button>
      </section>
      )}

      {has("domains") && (
      <section aria-labelledby="sec-domains">
        <SectionTitle id="sec-domains">Domains</SectionTitle>
        <div id="bp-domains" tabIndex={-1}>
          {form.domains.map((d, i) => (
            <Group key={i} title={d.key || `Domain ${i + 1}`} onRemove={() => set({ domains: form.domains.filter((_, idx) => idx !== i) })}>
              <Grid>
                <Field label="Domain key" hint="Matches the key used in starting pages."><TextInput value={d.key} placeholder="example" onChange={(e) => updDom(i, { key: e.target.value })} /></Field>
                {field("Base URL", bpId("domain", i, "base"), (a, bad) => <TextInput {...a} invalid={bad} value={d.base_url} placeholder="https://example.org" onChange={(e) => updDom(i, { base_url: e.target.value })} />)}
              </Grid>
              {field("Link XPath", bpId("domain", i, "selector"), (a, bad) => <TextInput {...a} invalid={bad} value={d.link_selector} placeholder=".//a[starts-with(@href, '/wiki/')]" onChange={(e) => updDom(i, { link_selector: e.target.value })} />, { hint: "Picks the links to follow on each page." })}
            </Group>
          ))}
        </div>
        <Button onClick={() => set({ domains: [...form.domains, { key: "", base_url: "", link_selector: "" }] })}>Add domain</Button>
      </section>
      )}

      {has("scoring") && (
      <section aria-labelledby="sec-scoring">
        <SectionTitle id="sec-scoring">Scoring</SectionTitle>
        <Field label="Strategy" id={bpId("strategy")} error={err(bpId("strategy"))}>
          {(a) => <Select {...a} value={form.scoringStrategy} onChange={(e) => set({ scoringStrategy: e.target.value })}>{STRATEGIES.map((s) => <option key={s} value={s}>{s}</option>)}</Select>}
        </Field>
        <Grid>
          {field("Scoring backend", bpId("scoring-type"), (a, bad) => <TextInput {...a} invalid={bad} list="bp-backends" value={form.scoringType} onChange={(e) => set({ scoringType: e.target.value })} />)}
          {field("Scoring model", bpId("scoring-model"), (a, bad) => <TextInput {...a} invalid={bad} value={form.modelInformation} placeholder="provider/model-name" onChange={(e) => set({ modelInformation: e.target.value })} />)}
        </Grid>
      </section>
      )}

      {has("expansion") && (
      <section aria-labelledby="sec-expansion">
        <SectionTitle id="sec-expansion">Expansion</SectionTitle>
        <Grid>
          <Field label="Style" id={bpId("expansion-style")} error={err(bpId("expansion-style"))}>
            {(a) => <Select {...a} value={form.expansionStyle} onChange={(e) => set({ expansionStyle: e.target.value })}>{EXPANSION_STYLES.map((s) => <option key={s} value={s}>{s}</option>)}</Select>}
          </Field>
          {field("Number of descriptions", bpId("num-descriptions"), (a, bad) => <TextInput {...a} invalid={bad} type="number" min={1} value={form.numDescriptions} onChange={(e) => set({ numDescriptions: e.target.value })} />)}
        </Grid>
        <Grid>
          {field("LLM backend", bpId("llm-type"), (a, bad) => <TextInput {...a} invalid={bad} list="bp-backends" value={form.llmType} onChange={(e) => set({ llmType: e.target.value })} />)}
          {field("LLM model", bpId("llm-model"), (a, bad) => <TextInput {...a} invalid={bad} value={form.llmModel} placeholder="provider/model-name" onChange={(e) => set({ llmModel: e.target.value })} />)}
        </Grid>
      </section>
      )}

      {has("extraction") && (
      <section aria-labelledby="sec-extraction">
        <SectionTitle id="sec-extraction">Extraction</SectionTitle>
        <div id="bp-extraction" tabIndex={-1} style={{ marginBottom: 12 }}>
          <Tabs id="bp-extract" label="Extraction mode" value={form.extractionMode} onChange={(extractionMode) => set({ extractionMode })} options={[["profile", "Site profile"], ["manual", "Manual fields"]]} />
        </div>
        <TabPanel tabsId="bp-extract" value={form.extractionMode}>
          {form.extractionMode === "profile"
            ? <ProfileExtraction profileId={form.profileId} checklist={form.profileChecklist}
                onProfileChange={(profileId) => set({ profileId })} onChecklistChange={(profileChecklist) => set({ profileChecklist })} />
            : <ManualFields fields={form.manualFields} onChange={(manualFields) => set({ manualFields })} errorFor={err} />}
        </TabPanel>
      </section>
      )}

      {has("stop") && (
      <section aria-labelledby="sec-stop">
        <SectionTitle id="sec-stop">Stop conditions</SectionTitle>
        <Grid>
          {field("Max pages", bpId("max_nodes"), (a, bad) => <TextInput {...a} invalid={bad} type="number" min={1} value={form.maxNodes} onChange={(e) => set({ maxNodes: e.target.value })} />)}
          {field("Max depth", bpId("max_depth"), (a, bad) => <TextInput {...a} invalid={bad} type="number" min={1} value={form.maxDepth} onChange={(e) => set({ maxDepth: e.target.value })} />, { hint: "Links followed from a starting page." })}
        </Grid>
        <Grid>
          {field("Max duration (ms)", bpId("max_duration"), (a, bad) => <TextInput {...a} invalid={bad} type="number" min={0} value={form.maxDuration} onChange={(e) => set({ maxDuration: e.target.value })} />)}
          {field("No-progress timeout (ms)", bpId("no_progress_timeout"), (a, bad) => <TextInput {...a} invalid={bad} type="number" min={0} value={form.noProgressTimeout} onChange={(e) => set({ noProgressTimeout: e.target.value })} />, { hint: "Stops if no new page is found for this long." })}
        </Grid>
        <Field label="Stop URL (optional)" hint="Stop as soon as this page is reached. Leave empty to disable.">
          {(a) => <TextInput {...a} value={form.stopUrl} onChange={(e) => set({ stopUrl: e.target.value })} />}
        </Field>
      </section>
      )}
    </div>
  );
}

// ─── page ────────────────────────────────────────────────────────────────────

const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;
const pretty = (bp) => JSON.stringify(bp, null, 2);
const nameOf = (n) => (n.endsWith(".json") ? n : `${n}.json`);

export default function BlueprintManager({ onNavigate }) {
  const [templates, setTemplates] = useState([]);
  const [listError, setListError] = useState(null);
  const [selected, setSelected] = useState(null);      // filename
  const [mode, setMode] = useState("idle");            // idle | edit | new
  const [tab, setTab] = useState("form");              // form | json
  const [newName, setNewName] = useState("");
  const [status, setStatus] = useState(null);          // { ok, msg }
  const [errors, setErrors] = useState([]);            // [{ id, message }]
  const [form, setForm] = useState(() => blueprintToForm(null));
  const [editorText, setEditorText] = useState(() => pretty(DEFAULT_BLUEPRINT));
  const [baseline, setBaseline] = useState(() => pretty(DEFAULT_BLUEPRINT));
  const [armed, setArmed] = useState(false);           // Delete needs two clicks
  const [pending, setPending] = useState(null);        // action waiting on "discard changes?"
  const [step, setStep] = useState("about");

  const current = useCallback(() => {
    if (tab === "form") return { ok: true, bp: formToBlueprint(form) };
    try { return { ok: true, bp: JSON.parse(editorText) }; }
    catch (e) { return { ok: false, bp: null, msg: e.message }; }
  }, [tab, form, editorText]);

  const dirty = useMemo(() => {
    if (mode === "idle") return false;
    const c = current();
    return mode === "new" ? true : !c.ok || pretty(c.bp) !== baseline;
  }, [mode, current, baseline]);

  const loadList = useCallback(async () => {
    try {
      const data = await fetchTemplates();
      setTemplates(data.templates);
      setListError(null);
    } catch (e) { setListError(e.message); }
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetchTemplates()
      .then((d) => { if (!cancelled) setTemplates(d.templates); })
      .catch((e) => { if (!cancelled) setListError(e.message); });
    return () => { cancelled = true; };
  }, []);

  const errorFor = useCallback((id) => errors.find((e) => e.id === id)?.message, [errors]);

  const openTemplate = async (name) => {
    try {
      const data = await fetchTemplate(name);
      const bp = data.content ?? data;
      setSelected(name); setForm(blueprintToForm(bp)); setEditorText(pretty(bp)); setBaseline(pretty(bp));
      setMode("edit"); setTab("form"); setStep("about"); setStatus(null); setErrors([]); setArmed(false);
    } catch (e) { setStatus({ ok: false, msg: e.message }); }
  };

  const startNew = () => {
    setSelected(null); setNewName(""); setForm(blueprintToForm(null)); setEditorText(pretty(DEFAULT_BLUEPRINT));
    setBaseline(pretty(DEFAULT_BLUEPRINT)); setMode("new"); setTab("form"); setStep("about"); setStatus(null); setErrors([]); setArmed(false);
  };

  // Leaving with unsaved edits asks first, inline.
  const guarded = (action) => (dirty ? setPending(() => action) : action());

  const switchTab = (next) => {
    if (next === tab) return;
    if (tab === "form") {
      setEditorText(pretty(formToBlueprint(form)));
    } else {
      try { setForm(blueprintToForm(JSON.parse(editorText))); }
      catch (e) { setStatus({ ok: false, msg: `The JSON is not valid (${e.message}). Fix it before switching to the form.` }); return; }
    }
    setStatus(null); setTab(next);
  };

  const save = async () => {
    const { ok, bp, msg } = current();
    if (!ok) { setStatus({ ok: false, msg: `The JSON is not valid (${msg}).` }); return; }
    const errs = validateBlueprint(bp);
    if (mode === "new" && !newName.trim()) errs.unshift({ id: "bp-file-name", message: "Give the blueprint a file name." });
    if (errs.length) { setErrors(errs); setStatus(null); return; }
    setErrors([]);
    try {
      if (mode === "new") {
        const name = nameOf(newName.trim());
        await createTemplate(name, bp);
        await loadList();
        setSelected(name); setMode("edit"); setBaseline(pretty(bp)); setStatus({ ok: true, msg: "Created" });
      } else {
        await updateTemplate(selected, bp);
        setBaseline(pretty(bp)); setStatus({ ok: true, msg: "Saved" });
      }
    } catch (e) { setStatus({ ok: false, msg: e.message }); }
  };

  // Cmd/Ctrl+S saves.
  useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "s" && mode !== "idle") { e.preventDefault(); save(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const remove = async () => {
    if (!armed) { setArmed(true); setTimeout(() => setArmed(false), 4000); return; }
    setArmed(false);
    try {
      await deleteTemplate(selected);
      setSelected(null); setMode("idle"); setForm(blueprintToForm(null)); setEditorText(pretty(DEFAULT_BLUEPRINT));
      await loadList();
      setStatus({ ok: true, msg: "Deleted" });
    } catch (e) { setStatus({ ok: false, msg: e.message }); }
  };

  const runThis = () => {
    try { sessionStorage.setItem(RUN_PRESELECT_KEY, selected); } catch { /* storage unavailable: Run opens on its default */ }
    onNavigate?.("run");
  };

  const focusField = (id) => {
    const target = stepOf(id);
    if (tab === "form" && target && target !== step) setStep(target);
    // The field may only exist once its step has rendered.
    requestAnimationFrame(() => {
      const el = document.getElementById(id);
      if (!el) return;
      el.scrollIntoView({ block: "center" });
      el.focus();
    });
  };

  const stepIndex = STEPS.findIndex(([id]) => id === step);
  const stepHasError = (id) => errors.some((e) => stepOf(e.id) === id);

  const stepper = (
    <nav aria-label="Blueprint steps" style={{ margin: "14px 0 4px", overflowX: "auto" }}>
      <ol style={{ listStyle: "none", display: "flex", gap: 4, minWidth: "min-content" }}>
        {STEPS.map(([id, name], i) => (
          <li key={id}>
            <button
              type="button" aria-current={id === step ? "step" : undefined} onClick={() => setStep(id)}
              style={{
                display: "flex", alignItems: "center", gap: 8, height: 40, padding: "0 12px", background: "transparent", borderTop: "none", borderLeft: "none", borderRight: "none",
                borderBottom: `2px solid ${id === step ? text.primary : "transparent"}`, whiteSpace: "nowrap",
                fontSize: 14, fontWeight: id === step ? 600 : 500, color: id === step ? text.primary : text.secondary,
              }}
            >
              <span className="num" style={{ fontSize: 12, color: text.muted }}>{i + 1}</span>
              {name}
              {stepHasError(id) && (
                <svg width="9" height="9" viewBox="0 0 9 9" role="img" aria-label="has errors"><path d="M4.5 0.5 8.5 8.5H0.5Z" fill={accent.red} /></svg>
              )}
            </button>
          </li>
        ))}
      </ol>
    </nav>
  );

  const reviewBp = tab === "form" ? formToBlueprint(form) : null;
  const count = (x) => Object.keys(x || {}).length;
  const review = reviewBp && (
    <section aria-labelledby="sec-review">
      <SectionTitle id="sec-review">What this will run</SectionTitle>
      <p style={{ fontFamily: theme.typography.fontDisplay, fontSize: 18, lineHeight: 1.4, color: text.primary, marginBottom: 6, maxWidth: "52ch" }}>
        {reviewBp.target_topic || "No target topic set."}
      </p>
      <Row label="Starts from">{plural(reviewBp.seeds.filter((x) => x.url).length, "page", "pages")}</Row>
      <Row label="Domains">{count(reviewBp.domains)}</Row>
      <Row label="Scoring strategy">{reviewBp.scoring.strategy}</Row>
      <Row label="Scored by">{reviewBp.scoring.params.scoring_type || "—"}</Row>
      <Row label="Extraction fields">{count(reviewBp.extraction.fields)}</Row>
      <Row label="Stops after">{Number(reviewBp.stop_conditions.max_nodes).toLocaleString()} pages</Row>
      <Row label="Maximum depth">{Number(reviewBp.stop_conditions.max_depth).toLocaleString()} links from a start page</Row>
      {mode === "edit" && (
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginTop: 24 }}>
          <Button onClick={runThis} disabled={dirty} title={dirty ? "Save first to run the saved version" : undefined}>Run this blueprint</Button>
          <Button variant="danger" armed={armed} onClick={remove}>{armed ? "Confirm delete" : "Delete blueprint"}</Button>
        </div>
      )}
    </section>
  );

  return (
    <Page
      title="Blueprints"
      lead="A blueprint says where a crawl starts, what counts as relevant, and when it stops."
      width={720}
    >
      {listError && (
        <div role="alert" style={{ maxWidth: "60ch", marginBottom: 20 }}>
          <p style={{ fontSize: 14, color: accent.red, marginBottom: 12 }}>
            Could not load blueprints: {listError}. Start the backend with make dev-backend, then try again.
          </p>
          <Button onClick={loadList}>Try again</Button>
        </div>
      )}

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
        <span id="bp-list-label" style={{ fontSize: 13, fontWeight: 600, color: text.primary }}>Saved blueprints</span>
        <Button onClick={() => guarded(startNew)}>New blueprint</Button>
      </div>
      <ul aria-labelledby="bp-list-label" style={{ listStyle: "none", marginBottom: 28 }}>
        {templates.length === 0 && !listError && (
          <li style={{ padding: "11px 0", fontSize: 14, color: text.muted, borderBottom: `1px solid ${theme.colors.rowBorder}` }}>No blueprints yet. Create one to describe a crawl.</li>
        )}
        {templates.map((t) => (
          <li key={t} style={{ borderBottom: `1px solid ${theme.colors.rowBorder}` }}>
            <button
              type="button" aria-current={t === selected ? "true" : undefined}
              onClick={() => t !== selected && guarded(() => openTemplate(t))}
              style={{
                display: "flex", alignItems: "center", gap: 10, width: "100%", minHeight: 40, padding: "0 2px",
                background: "transparent", border: "none", textAlign: "left", fontSize: 14,
                fontWeight: t === selected ? 600 : 400, color: text.primary,
              }}
            >
              <svg width="9" height="9" viewBox="0 0 9 9" aria-hidden="true" style={{ flexShrink: 0 }}>
                {t === selected ? <rect x="0.5" y="0.5" width="8" height="8" fill={text.primary} /> : <rect x="0.5" y="0.5" width="8" height="8" fill="none" stroke={text.muted} />}
              </svg>
              {t}
            </button>
          </li>
        ))}
      </ul>

      {pending && (
        <div role="alertdialog" aria-label="Unsaved changes" tabIndex={-1} ref={(el) => el?.focus()} style={{ border: `1px solid ${text.primary}`, padding: "12px 14px", marginBottom: 20, display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
          <span style={{ fontSize: 14, flex: "1 1 240px" }}>You have unsaved changes. Discard them?</span>
          <Button variant="danger" onClick={() => { const a = pending; setPending(null); a(); }}>Discard changes</Button>
          <Button onClick={() => setPending(null)}>Keep editing</Button>
        </div>
      )}

      {mode === "idle" && !pending && (
        <p style={{ fontSize: 14, color: text.muted }}>Choose a blueprint to edit it, or create a new one.</p>
      )}

      {mode !== "idle" && (
        <>
          <div style={{
            position: "sticky", top: 0, zIndex: 3, background: background.primary, padding: "8px 0",
            borderTop: `1px solid ${background.border}`, borderBottom: `1px solid ${background.border}`,
            display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap",
          }}>
            {mode === "new"
              ? <TextInput id="bp-file-name" aria-label="Blueprint file name" invalid={!!errorFor("bp-file-name")} placeholder="file-name.json" value={newName} onChange={(e) => setNewName(e.target.value)} style={{ flex: "1 1 160px", width: "auto", minWidth: 0 }} />
              : <span style={{ fontSize: 14, fontWeight: 600 }}>{selected}</span>}
            <Tabs id="bp-view" label="Editor view" value={tab} onChange={switchTab} options={[["form", "Form"], ["json", "JSON"]]} />
            <span style={{ flex: 1 }} />
            {dirty && mode === "edit" && <span style={{ fontSize: 13, color: text.secondary }}>Unsaved changes</span>}
            {status && <Status ok={status.ok}>{status.msg}</Status>}
            <Button variant="primary" onClick={save}>{mode === "new" ? "Create" : "Save"}</Button>
          </div>

          {errors.length > 0 && (
            <div role="alert" style={{ padding: "12px 0", borderBottom: `1px solid ${accent.red}` }}>
              <p style={{ fontSize: 14, fontWeight: 600, color: accent.red, marginBottom: 6 }}>
                {errors.length === 1 ? "1 thing to fix before saving" : `${errors.length} things to fix before saving`}
              </p>
              <ul style={{ listStyle: "none" }}>
                {errors.map((e, i) => (
                  <li key={i}>
                    <button type="button" onClick={() => focusField(e.id)}
                      style={{ background: "none", border: "none", padding: "4px 0", minHeight: 28, fontSize: 14, color: accent.red, textDecoration: "underline", textAlign: "left" }}>
                      {e.message}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <TabPanel tabsId="bp-view" value={tab}>
          {tab === "form" ? (
            <>
              {stepper}
              {step === "review" ? review : <BlueprintForm form={form} setForm={setForm} errorFor={errorFor} step={step} />}
              <div style={{ display: "flex", justifyContent: "space-between", marginTop: 28 }}>
                <Button onClick={() => setStep(STEPS[stepIndex - 1][0])} disabled={stepIndex === 0}>Back</Button>
                <Button onClick={() => setStep(STEPS[stepIndex + 1][0])} disabled={stepIndex === STEPS.length - 1}>Next: {STEPS[Math.min(stepIndex + 1, STEPS.length - 1)][1]}</Button>
              </div>
            </>
          ) : (
            <div style={{ marginTop: 16 }}>
              <label htmlFor="bp-json" style={{ display: "block", fontSize: 13, fontWeight: 600, marginBottom: 4 }}>Blueprint JSON</label>
              <textarea
                id="bp-json" value={editorText} onChange={(e) => setEditorText(e.target.value)} spellCheck={false}
                style={{
                  width: "100%", minHeight: 520, padding: 12, resize: "vertical", lineHeight: 1.6, fontSize: 13,
                  fontFamily: theme.typography.fontMono, background: background.panel, color: text.primary,
                  border: `1px solid ${background.border}`, borderRadius: theme.radii.sm,
                }}
              />
            </div>
          )}
          </TabPanel>
          <div style={{ height: 48 }} />
        </>
      )}
    </Page>
  );
}
