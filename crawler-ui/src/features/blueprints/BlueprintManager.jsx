/**
 * Template (blueprint) management screen.
 *
 * Sidebar lists saved blueprints; the main panel offers a structured
 * form editor and a raw JSON editor for the same document (UC-T01,
 * report section 0.11.2), kept in sync when switching tabs.
 *
 * V2 note: moved into features/blueprints/ and wired into the new app
 * shell, but its internals are deliberately left as-is this pass -- see
 * docs/V2_ARCHITECTURE.md roadmap #14. One thing worth flagging exactly
 * here for whoever picks that up: the STRATEGIES list below is a third,
 * hand-maintained copy of the same enum that already lives validated in
 * routes/blueprint_schema.py's ALLOWED_STRATEGIES (and, unused, in
 * routes/blueprint_ui_schema.json) -- see docs/V2_ARCHITECTURE.md §A.1.5.
 * features/config/ConfigPage.jsx shows the pattern this should eventually
 * move to: render from a schema fetched from the backend instead of a
 * literal copied here.
 */

import { useState, useEffect, useCallback } from "react";
import {
  fetchTemplates,
  fetchTemplate,
  createTemplate,
  updateTemplate,
  deleteTemplate,
} from "../../api/client";

// ─── STRICT CONSTANTS ─────────────────────────────────────────────────────────

const STRATEGIES = [
  "TOPICAL",
  "PATHFINDING",
  "EXPLORATION",
  "GOAL_ORIENTED",
  "DENSITY_FOCUSED",
  "UNCERTAINTY_BIASED",
];

const TRANSFORMS_NO_CONFIG = ["strip", "lowercase", "deduplicate", "join"];
const TRANSFORMS_WITH_CONFIG = {
  truncate:      { param: "max_len", inputType: "number", default: 300,  label: "Max Length" },
  regex:         { param: "pattern", inputType: "text",   default: "",   label: "Pattern"    },
  regex_extract: { param: "pattern", inputType: "text",   default: "",   label: "Pattern"    },
};
const ALL_TRANSFORMS = [...TRANSFORMS_NO_CONFIG, ...Object.keys(TRANSFORMS_WITH_CONFIG)];
const EXPORT_TYPES   = ["text", "real", "int", "json"];
const FIELD_TYPES    = ["scalar", "list"];
const EXPANSION_STYLES = ["rich", "minimal"];

// Static profile registry — mirrors extraction_profiles.json
const PROFILES = {
  wikimd_standard:    { label: "WikiMD Standard",    fields: ["title","paragraphs","headings","lists","infobox_items","categories"] },
  wikipedia_standard: { label: "Wikipedia Standard", fields: ["title","paragraphs","headings","lists","infobox_items","references","categories"] },
  pubmed_standard:    { label: "PubMed Standard",    fields: ["title","abstract","authors","keywords","pmid","publication_date"] },
  generic_article:    { label: "Generic Article",    fields: ["title","headings","paragraphs","meta_description"] },
};

// Default blueprint that matches the exact schema
const DEFAULT_BLUEPRINT = {
  blueprint_id: "",
  id: "",
  target_topic: "",
  seeds: [{ url: "", domain: "" }],
  domains: { "": { base_url: "", link_selector: "" } },
  scoring: {
    strategy: "TOPICAL",
    params: { scoring_type: "openrouter", model_information: "" },
  },
  expansion: { style: "rich", num_descriptions: 50, llm_type: "openrouter", llm_model: "" },
  extraction: { mode: "document", fields: {} },
  stop_conditions: {
    max_nodes: 120000, max_depth: 6000, max_duration: 900000,
    no_progress_timeout: 1000000, stop_url: "",
  },
};

// ─── VALIDATION ────────────────────────────────────────────────────────────────

function validateBlueprint(bp) {
  const errors = [];
  if (!bp.blueprint_id?.trim()) errors.push("blueprint_id is required.");
  if (!bp.id?.trim())           errors.push("id is required.");
  if (!bp.target_topic?.trim()) errors.push("target_topic is required.");

  (bp.seeds || []).forEach((s, i) => {
    if (!s.url?.trim())    errors.push(`seeds[${i}].url is required.`);
    if (!s.domain?.trim()) errors.push(`seeds[${i}].domain is required.`);
  });
  if (!(bp.seeds || []).length) errors.push("At least one seed is required.");

  const domKeys = Object.keys(bp.domains || {});
  if (!domKeys.length) errors.push("At least one domain is required.");
  domKeys.forEach((k) => {
    if (!bp.domains[k].base_url?.trim())      errors.push(`domains['${k}'].base_url is required.`);
    if (!bp.domains[k].link_selector?.trim()) errors.push(`domains['${k}'].link_selector is required.`);
  });

  if (!STRATEGIES.includes(bp.scoring?.strategy))
    errors.push(`scoring.strategy must be one of: ${STRATEGIES.join(", ")}.`);
  if (!bp.scoring?.params?.scoring_type?.trim())    errors.push("scoring.params.scoring_type is required.");
  if (!bp.scoring?.params?.model_information?.trim()) errors.push("scoring.params.model_information is required.");

  if (!EXPANSION_STYLES.includes(bp.expansion?.style)) errors.push("expansion.style must be 'rich' or 'minimal'.");
  if (!(bp.expansion?.num_descriptions >= 1))          errors.push("expansion.num_descriptions must be ≥ 1.");
  if (!bp.expansion?.llm_type?.trim())                 errors.push("expansion.llm_type is required.");
  if (!bp.expansion?.llm_model?.trim())                errors.push("expansion.llm_model is required.");

  if (bp.extraction?.mode !== "document") errors.push("extraction.mode must be 'document'.");
  const fields = bp.extraction?.fields || {};
  if (!Object.keys(fields).length) errors.push("At least one extraction field is required.");

  Object.entries(fields).forEach(([fname, f]) => {
    if (!f.selector?.trim())             errors.push(`Field '${fname}': selector is required.`);
    if (!FIELD_TYPES.includes(f.type))   errors.push(`Field '${fname}': type must be scalar|list.`);
    if (!EXPORT_TYPES.includes(f.export_type)) errors.push(`Field '${fname}': export_type must be one of ${EXPORT_TYPES.join("|")}.`);
    (f.transform || []).forEach((step, ti) => {
      if (!ALL_TRANSFORMS.includes(step.type))
        errors.push(`Field '${fname}' transform[${ti}]: '${step.type}' is not allowed.`);
      if (step.type in TRANSFORMS_WITH_CONFIG) {
        const { param } = TRANSFORMS_WITH_CONFIG[step.type];
        if (step[param] === undefined || step[param] === "")
          errors.push(`Field '${fname}' transform[${ti}] '${step.type}': '${param}' is required.`);
      }
    });
  });

  const sc = bp.stop_conditions || {};
  ["max_nodes","max_depth","max_duration","no_progress_timeout"].forEach((k) => {
    if (sc[k] === undefined || sc[k] === "" || isNaN(Number(sc[k])))
      errors.push(`stop_conditions.${k} must be a number.`);
  });

  return errors;
}

// ─── FORM ↔ BLUEPRINT CONVERSION ─────────────────────────────────────────────

function blueprintToForm(bp) {
  bp = bp || DEFAULT_BLUEPRINT;
  const fields = bp.extraction?.fields || {};
  const firstField = Object.values(fields)[0] || {};
  const isProfile = !!firstField._profile_resolved;

  return {
    blueprint_id:   bp.blueprint_id  || "",
    id:             bp.id            || "",
    target_topic:   bp.target_topic  || "",
    seeds: (bp.seeds || [{ url: "", domain: "" }]).map((s) => ({ url: s.url || "", domain: s.domain || "" })),
    domains: Object.entries(bp.domains || {}).map(([key, v]) => ({
      key, base_url: v.base_url || "", link_selector: v.link_selector || "",
    })) || [{ key: "", base_url: "", link_selector: "" }],

    // scoring
    scoringStrategy:   bp.scoring?.strategy                    || "TOPICAL",
    scoringType:       bp.scoring?.params?.scoring_type        || "openrouter",
    modelInformation:  bp.scoring?.params?.model_information   || "",

    // expansion
    expansionStyle:    bp.expansion?.style          || "rich",
    numDescriptions:   bp.expansion?.num_descriptions ?? 50,
    llmType:           bp.expansion?.llm_type        || "openrouter",
    llmModel:          bp.expansion?.llm_model        || "",

    // extraction
    extractionMode: isProfile ? "profile" : "manual",
    profileId: isProfile
      ? (firstField._profile_id || Object.keys(PROFILES)[0])
      : Object.keys(PROFILES)[0],
    profileChecklist: isProfile ? Object.keys(fields) : Object.keys(PROFILES)[0]
      ? [...PROFILES[Object.keys(PROFILES)[0]].fields]
      : [],
    manualFields: isProfile
      ? [{ name: "", selector: "", fieldType: "scalar", exportType: "text", transforms: [] }]
      : Object.entries(fields).map(([name, f]) => ({
          name,
          selector:   f.selector    || "",
          fieldType:  f.type        || "scalar",
          exportType: f.export_type || "text",
          transforms: (f.transform || []).map((t) => ({
            type:       t.type,
            paramValue: t.max_len !== undefined
              ? String(t.max_len)
              : (t.pattern !== undefined ? t.pattern : ""),
          })),
        })),

    // stop
    maxNodes:           bp.stop_conditions?.max_nodes            ?? 120000,
    maxDepth:           bp.stop_conditions?.max_depth            ?? 6000,
    maxDuration:        bp.stop_conditions?.max_duration         ?? 900000,
    noProgressTimeout:  bp.stop_conditions?.no_progress_timeout  ?? 1000000,
    stopUrl:            bp.stop_conditions?.stop_url             || "",
  };
}

function formToBlueprint(form) {
  // Build domains object
  const domains = {};
  (form.domains || []).forEach((d) => {
    if (d.key?.trim()) {
      domains[d.key.trim()] = { base_url: d.base_url, link_selector: d.link_selector };
    }
  });

  // Build extraction fields
  const fields = {};
  if (form.extractionMode === "profile") {
    // Stubs that BlueprintTranslator resolves server-side
    (form.profileChecklist || []).forEach((fname) => {
      fields[fname] = { _profile_resolved: true, _profile_id: form.profileId };
    });
  } else {
    (form.manualFields || []).forEach((mf) => {
      if (!mf.name?.trim()) return;
      const transform = (mf.transforms || []).map((t) => {
        const step = { type: t.type };
        if (t.type in TRANSFORMS_WITH_CONFIG) {
          const { param, inputType } = TRANSFORMS_WITH_CONFIG[t.type];
          step[param] = inputType === "number" ? Number(t.paramValue) : t.paramValue;
        }
        return step;
      });
      fields[mf.name.trim()] = {
        selector:    mf.selector,
        type:        mf.fieldType,
        transform,
        export_type: mf.exportType,
      };
    });
  }

  // Exact blueprint shape — no extra keys, no renamed keys
  return {
    blueprint_id: form.blueprint_id,
    id:           form.id,
    target_topic: form.target_topic,
    seeds:        (form.seeds || []).map((s) => ({ url: s.url, domain: s.domain })),
    domains,
    scoring: {
      strategy: form.scoringStrategy,
      params: {
        scoring_type:      form.scoringType,
        model_information: form.modelInformation,
      },
    },
    expansion: {
      style:            form.expansionStyle,
      num_descriptions: Number(form.numDescriptions),
      llm_type:         form.llmType,
      llm_model:        form.llmModel,
    },
    extraction: { mode: "document", fields },
    stop_conditions: {
      max_nodes:            Number(form.maxNodes),
      max_depth:            Number(form.maxDepth),
      max_duration:         Number(form.maxDuration),
      no_progress_timeout:  Number(form.noProgressTimeout),
      stop_url:             form.stopUrl || "",
    },
  };
}

// ─── DESIGN TOKENS (matches existing palette exactly) ────────────────────────
const C = {
  bg0: "#060a14", bg1: "#080c18", bg2: "#0d1422",
  border: "#111828", border2: "#1a2040",
  text: "#c0cce0", bright: "#e0eaff", dim: "#3a4060",
  accent: "#5a7aff", danger: "#ff4a6a", ok: "#40d9a0",
  mono: "'JetBrains Mono', monospace",
};
const inp = (extra = {}) => ({
  background: C.bg1, border: `1px solid ${C.border2}`, borderRadius: 3,
  color: C.bright, fontFamily: C.mono, fontSize: 11, padding: "4px 8px",
  outline: "none", width: "100%", boxSizing: "border-box", ...extra,
});
const sel = () => ({ ...inp(), cursor: "pointer", appearance: "none", WebkitAppearance: "none" });
const lbl = () => ({
  display: "block", fontSize: 9, letterSpacing: "0.09em", textTransform: "uppercase",
  color: C.dim, marginBottom: 3,
});
const S = {
  root: { display: "flex", height: "100%", background: C.bg0, color: C.text, fontFamily: C.mono, fontSize: 12, overflow: "hidden" },
  sidebar: { width: 220, borderRight: `1px solid ${C.border}`, display: "flex", flexDirection: "column", flexShrink: 0 },
  sidebarHeader: { padding: "12px 14px", borderBottom: `1px solid ${C.border}`, fontSize: 9, letterSpacing: "0.1em", color: C.dim, textTransform: "uppercase", display: "flex", justifyContent: "space-between", alignItems: "center" },
  list: { flex: 1, overflowY: "auto", padding: "6px 0" },
  listItem: (active) => ({ padding: "7px 14px", cursor: "pointer", background: active ? C.bg2 : "transparent", borderLeft: `2px solid ${active ? C.accent : "transparent"}`, color: active ? C.bright : C.text, fontSize: 11, transition: "background 0.1s" }),
  main: { flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" },
  toolbar: { padding: "10px 16px", borderBottom: `1px solid ${C.border}`, display: "flex", gap: 8, alignItems: "center", flexShrink: 0 },
  status: (ok) => ({ fontSize: 10, color: ok ? C.ok : C.danger, marginLeft: "auto" }),
  empty: { flex: 1, display: "flex", alignItems: "center", justifyContent: "center", color: "#2a3050", fontSize: 11, letterSpacing: "0.06em" },
  textarea: { flex: 1, background: C.bg1, border: `1px solid ${C.border}`, borderRadius: 4, color: "#a0b4d0", fontFamily: C.mono, fontSize: 11, padding: 12, resize: "none", outline: "none", lineHeight: 1.6 },
  nameInput: { background: C.bg1, border: `1px solid ${C.border2}`, borderRadius: 4, color: C.bright, fontFamily: C.mono, fontSize: 11, padding: "4px 8px", outline: "none", width: 180 },
  btn: (variant = "default") => ({ background: variant === "primary" ? C.accent : variant === "danger" ? C.danger : C.bg2, color: variant === "primary" || variant === "danger" ? "#fff" : C.text, border: `1px solid ${variant === "primary" ? C.accent : variant === "danger" ? C.danger : C.border2}`, borderRadius: 4, padding: "4px 12px", fontSize: 9, letterSpacing: "0.08em", textTransform: "uppercase", cursor: "pointer", fontFamily: C.mono }),
};
const row2 = { display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 10 };
const sec  = { borderBottom: `1px solid ${C.border}`, padding: "14px 16px" };

// ─── SMALL UI ATOMS ───────────────────────────────────────────────────────────

function SecHead({ title }) {
  return <div style={{ fontSize: 9, letterSpacing: "0.12em", color: C.dim, textTransform: "uppercase", marginBottom: 10 }}>{title}</div>;
}
function F({ label, children }) {
  return <div style={{ marginBottom: 8 }}><label style={lbl()}>{label}</label>{children}</div>;
}
function Pill({ active, onClick, children }) {
  return (
    <span onClick={onClick} style={{ padding: "2px 10px", borderRadius: 10, fontSize: 9, letterSpacing: "0.08em", textTransform: "uppercase", cursor: "pointer", fontFamily: C.mono, border: `1px solid ${active ? C.accent : C.border2}`, background: active ? C.accent + "22" : "transparent", color: active ? C.accent : C.dim, userSelect: "none" }}>
      {children}
    </span>
  );
}

// ─── TRANSFORM PIPELINE ───────────────────────────────────────────────────────

function TransformPipeline({ transforms, onChange }) {
  const add  = () => onChange([...transforms, { type: "strip", paramValue: "" }]);
  const rm   = (i) => onChange(transforms.filter((_, idx) => idx !== i));
  const upd  = (i, patch) => onChange(transforms.map((t, idx) => idx === i ? { ...t, ...patch } : t));

  return (
    <div style={{ marginTop: 4 }}>
      {transforms.map((t, i) => {
        const cfg = TRANSFORMS_WITH_CONFIG[t.type];
        return (
          <div key={i} style={{ display: "grid", gridTemplateColumns: cfg ? "130px 1fr 22px" : "130px 1fr 22px", gap: 5, alignItems: "center", marginBottom: 4 }}>
            <select style={sel()} value={t.type} onChange={(e) => {
              const nc = TRANSFORMS_WITH_CONFIG[e.target.value];
              upd(i, { type: e.target.value, paramValue: nc ? String(nc.default) : "" });
            }}>
              {ALL_TRANSFORMS.map((tr) => <option key={tr} value={tr}>{tr}</option>)}
            </select>
            {cfg
              ? <input style={inp()} type={cfg.inputType} placeholder={cfg.label} value={t.paramValue} onChange={(e) => upd(i, { paramValue: e.target.value })} />
              : <span style={{ fontSize: 10, color: C.dim }}>—</span>
            }
            <button style={{ ...S.btn("danger"), padding: "2px 5px", fontSize: 10 }} onClick={() => rm(i)}>×</button>
          </div>
        );
      })}
      <button style={S.btn()} onClick={add}>+ transform</button>
    </div>
  );
}

// ─── MANUAL FIELDS EDITOR ────────────────────────────────────────────────────

function ManualFields({ fields, onChange }) {
  const add = () => onChange([...fields, { name: "", selector: "", fieldType: "scalar", exportType: "text", transforms: [] }]);
  const rm  = (i) => onChange(fields.filter((_, idx) => idx !== i));
  const upd = (i, patch) => onChange(fields.map((f, idx) => idx === i ? { ...f, ...patch } : f));

  return (
    <div>
      {fields.map((f, i) => (
        <div key={i} style={{ background: C.bg1, border: `1px solid ${C.border}`, borderRadius: 4, padding: "10px 12px", marginBottom: 8 }}>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
            <span style={{ fontSize: 10, color: C.accent }}>Field {i + 1}{f.name ? ` — ${f.name}` : ""}</span>
            <button style={S.btn("danger")} onClick={() => rm(i)}>remove</button>
          </div>
          <div style={row2}>
            <F label="Name">
              <input style={inp()} value={f.name} placeholder="e.g. title" onChange={(e) => upd(i, { name: e.target.value })} />
            </F>
            <F label="XPath Selector">
              <input style={inp()} value={f.selector} placeholder="//h1[@id='firstHeading']" onChange={(e) => upd(i, { selector: e.target.value })} />
            </F>
          </div>
          <div style={row2}>
            <F label="Type">
              <select style={sel()} value={f.fieldType} onChange={(e) => upd(i, { fieldType: e.target.value })}>
                {FIELD_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </F>
            <F label="Export Type">
              <select style={sel()} value={f.exportType} onChange={(e) => upd(i, { exportType: e.target.value })}>
                {EXPORT_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </F>
          </div>
          <F label="Transforms">
            <TransformPipeline transforms={f.transforms} onChange={(transforms) => upd(i, { transforms })} />
          </F>
        </div>
      ))}
      <button style={S.btn("primary")} onClick={add}>+ add field</button>
    </div>
  );
}

// ─── PROFILE EXTRACTION ───────────────────────────────────────────────────────

function ProfileExtraction({ profileId, checklist, onProfileChange, onChecklistChange }) {
  const fields = PROFILES[profileId]?.fields || [];
  const toggle    = (f) => onChecklistChange(checklist.includes(f) ? checklist.filter((x) => x !== f) : [...checklist, f]);
  const toggleAll = () => onChecklistChange(checklist.length === fields.length ? [] : [...fields]);

  return (
    <div>
      <F label="Domain Profile">
        <select style={sel()} value={profileId} onChange={(e) => {
          onProfileChange(e.target.value);
          onChecklistChange([...PROFILES[e.target.value].fields]);
        }}>
          {Object.entries(PROFILES).map(([id, p]) => <option key={id} value={id}>{p.label}</option>)}
        </select>
      </F>
      <div style={{ marginBottom: 6, display: "flex", alignItems: "center", gap: 8 }}>
        <label style={lbl()}>Fields to include</label>
        <button style={{ ...S.btn(), fontSize: 8 }} onClick={toggleAll}>
          {checklist.length === fields.length ? "deselect all" : "select all"}
        </button>
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 6 }}>
        {fields.map((f) => (
          <Pill key={f} active={checklist.includes(f)} onClick={() => toggle(f)}>{f}</Pill>
        ))}
      </div>
      <div style={{ fontSize: 10, color: C.dim }}>Selectors and transforms are resolved automatically.</div>
    </div>
  );
}

// ─── BLUEPRINT FORM ───────────────────────────────────────────────────────────

function BlueprintForm({ form, setForm }) {
  const set = (patch) => setForm((f) => ({ ...f, ...patch }));

  // seeds
  const updSeed = (i, patch) => set({ seeds: form.seeds.map((s, idx) => idx === i ? { ...s, ...patch } : s) });
  const addSeed = () => set({ seeds: [...form.seeds, { url: "", domain: "" }] });
  const rmSeed  = (i) => set({ seeds: form.seeds.filter((_, idx) => idx !== i) });

  // domains
  const updDom = (i, patch) => set({ domains: form.domains.map((d, idx) => idx === i ? { ...d, ...patch } : d) });
  const addDom = () => set({ domains: [...form.domains, { key: "", base_url: "", link_selector: "" }] });
  const rmDom  = (i) => set({ domains: form.domains.filter((_, idx) => idx !== i) });

  return (
    <div style={{ overflowY: "auto", flex: 1 }}>

      {/* META */}
      <div style={sec}>
        <SecHead title="Meta" />
        <div style={row2}>
          <F label="Blueprint ID">
            <input style={inp()} value={form.blueprint_id} placeholder="wikimd_diabetes" onChange={(e) => set({ blueprint_id: e.target.value })} />
          </F>
          <F label="Run ID">
            <input style={inp()} value={form.id} placeholder="beta_1" onChange={(e) => set({ id: e.target.value })} />
          </F>
        </div>
        <F label="Target Topic">
          <input style={inp()} value={form.target_topic} placeholder="TYPE 2 DIABETES" onChange={(e) => set({ target_topic: e.target.value })} />
        </F>
      </div>

      {/* SEEDS */}
      <div style={sec}>
        <SecHead title="Seeds" />
        {form.seeds.map((s, i) => (
          <div key={i} style={{ display: "grid", gridTemplateColumns: "1fr 1fr 22px", gap: 8, alignItems: "end", marginBottom: 8 }}>
            <F label="URL"><input style={inp()} value={s.url} placeholder="https://wikimd.org/wiki/…" onChange={(e) => updSeed(i, { url: e.target.value })} /></F>
            <F label="Domain"><input style={inp()} value={s.domain} placeholder="https://www.wikimd.org" onChange={(e) => updSeed(i, { domain: e.target.value })} /></F>
            <button style={{ ...S.btn("danger"), marginBottom: 8 }} onClick={() => rmSeed(i)}>×</button>
          </div>
        ))}
        <button style={S.btn()} onClick={addSeed}>+ seed</button>
      </div>

      {/* DOMAINS */}
      <div style={sec}>
        <SecHead title="Domains" />
        {form.domains.map((d, i) => (
          <div key={i} style={{ background: C.bg1, border: `1px solid ${C.border}`, borderRadius: 4, padding: "10px 12px", marginBottom: 8 }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
              <span style={{ fontSize: 10, color: C.accent }}>{d.key || `Domain ${i + 1}`}</span>
              <button style={S.btn("danger")} onClick={() => rmDom(i)}>remove</button>
            </div>
            <div style={row2}>
              <F label="Domain Key">
                <input style={inp()} value={d.key} placeholder="wikimd" onChange={(e) => updDom(i, { key: e.target.value })} />
              </F>
              <F label="Base URL">
                <input style={inp()} value={d.base_url} placeholder="https://www.wikimd.org" onChange={(e) => updDom(i, { base_url: e.target.value })} />
              </F>
            </div>
            <F label="Link XPath Selector">
              <input style={inp()} value={d.link_selector} placeholder=".//a[starts-with(@href, '/wiki/')]" onChange={(e) => updDom(i, { link_selector: e.target.value })} />
            </F>
          </div>
        ))}
        <button style={S.btn()} onClick={addDom}>+ domain</button>
      </div>

      {/* SCORING */}
      <div style={sec}>
        <SecHead title="Scoring" />
        <F label="Strategy">
          <select style={sel()} value={form.scoringStrategy} onChange={(e) => set({ scoringStrategy: e.target.value })}>
            {STRATEGIES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </F>
        <div style={row2}>
          <F label="Scoring Backend">
            <input style={inp()} value={form.scoringType} placeholder="openrouter / openai / anthropic / gemini / nvidia" onChange={(e) => set({ scoringType: e.target.value })} />
          </F>
          <F label="Model Identifier">
            <input style={inp()} value={form.modelInformation} placeholder="openai/gpt-4o:free" onChange={(e) => set({ modelInformation: e.target.value })} />
          </F>
        </div>
      </div>

      {/* EXPANSION */}
      <div style={sec}>
        <SecHead title="Expansion" />
        <div style={row2}>
          <F label="Style">
            <select style={sel()} value={form.expansionStyle} onChange={(e) => set({ expansionStyle: e.target.value })}>
              {EXPANSION_STYLES.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </F>
          <F label="Num Descriptions">
            <input style={inp()} type="number" min={1} value={form.numDescriptions} onChange={(e) => set({ numDescriptions: e.target.value })} />
          </F>
        </div>
        <div style={row2}>
          <F label="LLM Backend">
            <input style={inp()} value={form.llmType} placeholder="openrouter / openai / anthropic / gemini / nvidia" onChange={(e) => set({ llmType: e.target.value })} />
          </F>
          <F label="LLM Model">
            <input style={inp()} value={form.llmModel} placeholder="openai/gpt-4o:free" onChange={(e) => set({ llmModel: e.target.value })} />
          </F>
        </div>
      </div>

      {/* EXTRACTION */}
      <div style={sec}>
        <SecHead title="Extraction" />
        <div style={{ display: "flex", gap: 8, marginBottom: 14 }}>
          <Pill active={form.extractionMode === "profile"} onClick={() => set({ extractionMode: "profile" })}>Profile Mode</Pill>
          <Pill active={form.extractionMode === "manual"}  onClick={() => set({ extractionMode: "manual"  })}>Manual Mode</Pill>
        </div>
        {form.extractionMode === "profile"
          ? <ProfileExtraction
              profileId={form.profileId}
              checklist={form.profileChecklist}
              onProfileChange={(profileId) => set({ profileId })}
              onChecklistChange={(profileChecklist) => set({ profileChecklist })}
            />
          : <ManualFields
              fields={form.manualFields}
              onChange={(manualFields) => set({ manualFields })}
            />
        }
      </div>

      {/* STOP CONDITIONS */}
      <div style={sec}>
        <SecHead title="Stop Conditions" />
        <div style={row2}>
          <F label="Max Nodes">
            <input style={inp()} type="number" min={1} value={form.maxNodes} onChange={(e) => set({ maxNodes: e.target.value })} />
          </F>
          <F label="Max Depth">
            <input style={inp()} type="number" min={1} value={form.maxDepth} onChange={(e) => set({ maxDepth: e.target.value })} />
          </F>
        </div>
        <div style={row2}>
          <F label="Max Duration (ms)">
            <input style={inp()} type="number" min={0} value={form.maxDuration} onChange={(e) => set({ maxDuration: e.target.value })} />
          </F>
          <F label="No-Progress Timeout (ms)">
            <input style={inp()} type="number" min={0} value={form.noProgressTimeout} onChange={(e) => set({ noProgressTimeout: e.target.value })} />
          </F>
        </div>
        <F label="Stop URL (optional)">
          <input style={inp()} value={form.stopUrl} placeholder="Leave empty to disable" onChange={(e) => set({ stopUrl: e.target.value })} />
        </F>
      </div>

      <div style={{ height: 24 }} />
    </div>
  );
}

// ─── TEMPLATE MANAGER (PAGE) ──────────────────────────────────────────────────

export default function TemplateManager() {
  const [templates, setTemplates] = useState([]);
  const [selected,  setSelected]  = useState(null);   // filename string
  const [mode,      setMode]      = useState("idle");  // idle | edit | new
  const [tab,       setTab]       = useState("form");  // form | json
  const [newName,   setNewName]   = useState("");
  const [status,    setStatus]    = useState(null);    // { ok, msg }
  const [errors,    setErrors]    = useState([]);

  // form state (structured editor)
  const [form, setForm] = useState(() => blueprintToForm(null));

  // raw json state (textarea)
  const [editorText, setEditorText] = useState(() => JSON.stringify(DEFAULT_BLUEPRINT, null, 2));

  // ── helpers ──────────────────────────────────────────────────────────────────

  const loadList = useCallback(async () => {
    try {
      const data = await fetchTemplates();
      setTemplates(data.templates);
    } catch (e) {
      setStatus({ ok: false, msg: e.message });
    }
  }, []);

  useEffect(() => { loadList(); }, [loadList]);

  // When tab switches: sync form ↔ json
  const switchTab = (next) => {
    if (tab === "form" && next === "json") {
      // form → json
      setEditorText(JSON.stringify(formToBlueprint(form), null, 2));
    } else if (tab === "json" && next === "form") {
      // json → form (best-effort; validation happens on save)
      try {
        const bp = JSON.parse(editorText);
        setForm(blueprintToForm(bp));
      } catch { /* leave form as-is if JSON is invalid */ }
    }
    setTab(next);
  };

  // Get the current blueprint from whichever tab is active
  const getCurrentBlueprint = () => {
    if (tab === "form") return { ok: true, bp: formToBlueprint(form) };
    try   { return { ok: true,  bp: JSON.parse(editorText) }; }
    catch { return { ok: false, bp: null, msg: "Invalid JSON" }; }
  };

  const selectTemplate = async (name) => {
    try {
      const data = await fetchTemplate(name);
      setSelected(name);
      setForm(blueprintToForm(data));
      setEditorText(JSON.stringify(data, null, 2));
      setMode("edit");
      setStatus(null);
      setErrors([]);
    } catch (e) {
      setStatus({ ok: false, msg: e.message });
    }
  };

  const handleNew = () => {
    setSelected(null);
    setNewName("");
    setForm(blueprintToForm(null));
    setEditorText(JSON.stringify(DEFAULT_BLUEPRINT, null, 2));
    setMode("new");
    setStatus(null);
    setErrors([]);
  };

  const handleSave = async () => {
    const { ok, bp, msg } = getCurrentBlueprint();
    if (!ok) { setStatus({ ok: false, msg }); return; }

    const errs = validateBlueprint(bp);
    if (errs.length) { setErrors(errs); setStatus({ ok: false, msg: `${errs.length} validation error(s)` }); return; }
    setErrors([]);

    try {
      if (mode === "new") {
        const name = newName.trim() || "untitled";
        await createTemplate(name, bp);         // payload: { content: bp } — matches TemplateBody
        await loadList();
        setSelected(name.endsWith(".json") ? name : name + ".json");
        setMode("edit");
        setStatus({ ok: true, msg: "Created" });
      } else {
        await updateTemplate(selected, bp);     // payload: { content: bp }
        setStatus({ ok: true, msg: "Saved" });
      }
    } catch (e) {
      setStatus({ ok: false, msg: e.message });
    }
  };

  const handleDelete = async () => {
    if (!selected) return;
    if (!window.confirm(`Delete "${selected}"?`)) return;
    try {
      await deleteTemplate(selected);
      setSelected(null);
      setMode("idle");
      setForm(blueprintToForm(null));
      setEditorText(JSON.stringify(DEFAULT_BLUEPRINT, null, 2));
      await loadList();
      setStatus({ ok: true, msg: "Deleted" });
    } catch (e) {
      setStatus({ ok: false, msg: e.message });
    }
  };

  // ── render ───────────────────────────────────────────────────────────────────
  return (
    <div style={S.root}>

      {/* ── SIDEBAR ── */}
      <div style={S.sidebar}>
        <div style={S.sidebarHeader}>
          <span>Templates</span>
          <button style={S.btn()} onClick={handleNew}>+ New</button>
        </div>
        <div style={S.list}>
          {templates.length === 0 && (
            <div style={{ padding: "12px 14px", color: "#2a3050", fontSize: 10 }}>No templates yet</div>
          )}
          {templates.map((t) => (
            <div key={t} style={S.listItem(t === selected)} onClick={() => selectTemplate(t)}>
              <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{t}</span>
            </div>
          ))}
        </div>
      </div>

      {/* ── MAIN ── */}
      <div style={S.main}>
        {mode === "idle" ? (
          <div style={S.empty}>SELECT OR CREATE A TEMPLATE</div>
        ) : (
          <>
            {/* toolbar */}
            <div style={S.toolbar}>
              {mode === "new" && (
                <input style={S.nameInput} placeholder="template-name.json" value={newName} onChange={(e) => setNewName(e.target.value)} />
              )}
              {mode === "edit" && (
                <span style={{ color: C.bright, fontSize: 11 }}>{selected}</span>
              )}

              {/* tab switcher */}
              <div style={{ display: "flex", gap: 1, background: C.bg1, borderRadius: 4, padding: 2 }}>
                {["form", "json"].map((t) => (
                  <button key={t} style={{ ...S.btn(tab === t ? "primary" : "default"), padding: "3px 10px" }} onClick={() => switchTab(t)}>
                    {t === "form" ? "Form" : "JSON"}
                  </button>
                ))}
              </div>

              <button style={S.btn("primary")} onClick={handleSave}>
                {mode === "new" ? "Create" : "Save"}
              </button>
              {mode === "edit" && (
                <button style={S.btn("danger")} onClick={handleDelete}>Delete</button>
              )}
              {status && <span style={S.status(status.ok)}>{status.msg}</span>}
            </div>

            {/* validation errors */}
            {errors.length > 0 && (
              <div style={{ background: "#1a0810", borderBottom: `1px solid ${C.danger}`, padding: "8px 16px", flexShrink: 0, overflowY: "auto", maxHeight: 100 }}>
                <div style={{ fontSize: 9, color: C.danger, letterSpacing: "0.1em", marginBottom: 4 }}>VALIDATION ERRORS</div>
                {errors.map((e, i) => <div key={i} style={{ fontSize: 10, color: "#ff8099", marginBottom: 2 }}>· {e}</div>)}
              </div>
            )}

            {/* editor area */}
            <div style={{ flex: 1, overflow: "hidden", display: "flex", flexDirection: "column" }}>
              {tab === "form" ? (
                <BlueprintForm form={form} setForm={setForm} />
              ) : (
                <div style={{ flex: 1, padding: 16, display: "flex", flexDirection: "column" }}>
                  <textarea
                    style={S.textarea}
                    value={editorText}
                    onChange={(e) => setEditorText(e.target.value)}
                    spellCheck={false}
                  />
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
