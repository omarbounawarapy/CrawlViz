// Blueprint data model: constants, validation and the form <-> blueprint
// conversion used by BlueprintManager. No UI in here.
//
// STRATEGIES is a hand-maintained copy of ALLOWED_STRATEGIES in
// routes/blueprint_schema.py; the long-term
// move is to render from a backend schema, as features/config does.

// ─── STRICT CONSTANTS ─────────────────────────────────────────────────────────

export const STRATEGIES = [
  "TOPICAL",
  "PATHFINDING",
  "EXPLORATION",
  "GOAL_ORIENTED",
  "DENSITY_FOCUSED",
  "UNCERTAINTY_BIASED",
];

export const TRANSFORMS_NO_CONFIG = ["strip", "lowercase", "deduplicate", "join"];
export const TRANSFORMS_WITH_CONFIG = {
  truncate:      { param: "max_len", inputType: "number", default: 300,  label: "Max Length" },
  regex:         { param: "pattern", inputType: "text",   default: "",   label: "Pattern"    },
  regex_extract: { param: "pattern", inputType: "text",   default: "",   label: "Pattern"    },
};
export const ALL_TRANSFORMS = [...TRANSFORMS_NO_CONFIG, ...Object.keys(TRANSFORMS_WITH_CONFIG)];
export const EXPORT_TYPES   = ["text", "real", "int", "json"];
export const FIELD_TYPES    = ["scalar", "list"];
export const EXPANSION_STYLES = ["rich", "minimal"];

// Static profile registry — mirrors extraction_profiles.json
export const PROFILES = {
  wikimd_standard:    { label: "WikiMD Standard",    fields: ["title","paragraphs","headings","lists","infobox_items","categories"] },
  wikipedia_standard: { label: "Wikipedia Standard", fields: ["title","paragraphs","headings","lists","infobox_items","references","categories"] },
  pubmed_standard:    { label: "PubMed Standard",    fields: ["title","abstract","authors","keywords","pmid","publication_date"] },
  generic_article:    { label: "Generic Article",    fields: ["title","headings","paragraphs","meta_description"] },
};

// Default blueprint that matches the exact schema
export const DEFAULT_BLUEPRINT = {
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
// Returns [{ id, message }]. `id` is the DOM id of the field to focus
// (see BlueprintManager's bpId), so an error can link straight to its field.

export function validateBlueprint(bp) {
  const errors = [];
  const add = (id, message) => errors.push({ id, message });
  if (!bp.blueprint_id?.trim()) add("bp-blueprint_id", "Blueprint ID is required.");
  if (!bp.id?.trim())           add("bp-id", "Run ID is required.");
  if (!bp.target_topic?.trim()) add("bp-target_topic", "Target topic is required.");

  (bp.seeds || []).forEach((s, i) => {
    if (!s.url?.trim())    add(`bp-seed-${i}-url`, `Starting page ${i + 1}: URL is required.`);
    if (!s.domain?.trim()) add(`bp-seed-${i}-domain`, `Starting page ${i + 1}: domain is required.`);
  });
  if (!(bp.seeds || []).length) add("bp-seeds", "Add at least one starting page.");

  const domKeys = Object.keys(bp.domains || {});
  if (!domKeys.length) add("bp-domains", "Add at least one domain.");
  domKeys.forEach((k, i) => {
    if (!bp.domains[k].base_url?.trim())      add(`bp-domain-${i}-base`, `Domain "${k}": base URL is required.`);
    if (!bp.domains[k].link_selector?.trim()) add(`bp-domain-${i}-selector`, `Domain "${k}": link XPath is required.`);
  });

  if (!STRATEGIES.includes(bp.scoring?.strategy))
    add("bp-strategy", `Strategy must be one of: ${STRATEGIES.join(", ")}.`);
  if (!bp.scoring?.params?.scoring_type?.trim())     add("bp-scoring-type", "Scoring backend is required.");
  if (!bp.scoring?.params?.model_information?.trim()) add("bp-scoring-model", "Scoring model is required.");

  if (!EXPANSION_STYLES.includes(bp.expansion?.style)) add("bp-expansion-style", "Expansion style must be rich or minimal.");
  if (!(bp.expansion?.num_descriptions >= 1))          add("bp-num-descriptions", "Number of descriptions must be at least 1.");
  if (!bp.expansion?.llm_type?.trim())                 add("bp-llm-type", "LLM backend is required.");
  if (!bp.expansion?.llm_model?.trim())                add("bp-llm-model", "LLM model is required.");

  if (bp.extraction?.mode !== "document") add("bp-extraction", "Extraction mode must be document.");
  const fields = bp.extraction?.fields || {};
  if (!Object.keys(fields).length) add("bp-extraction", "Choose or add at least one extraction field.");

  Object.entries(fields).forEach(([fname, f], i) => {
    if (!f.selector?.trim())             add(`bp-field-${i}-selector`, `Field "${fname}": XPath selector is required.`);
    if (!FIELD_TYPES.includes(f.type))   add(`bp-field-${i}-type`, `Field "${fname}": type must be scalar or list.`);
    if (!EXPORT_TYPES.includes(f.export_type)) add(`bp-field-${i}-export`, `Field "${fname}": export type must be one of ${EXPORT_TYPES.join(", ")}.`);
    (f.transform || []).forEach((step, ti) => {
      if (!ALL_TRANSFORMS.includes(step.type))
        add(`bp-field-${i}-selector`, `Field "${fname}", step ${ti + 1}: "${step.type}" is not an allowed transform.`);
      if (step.type in TRANSFORMS_WITH_CONFIG) {
        const { param, label } = TRANSFORMS_WITH_CONFIG[step.type];
        if (step[param] === undefined || step[param] === "")
          add(`bp-field-${i}-selector`, `Field "${fname}", step ${ti + 1} (${step.type}): ${label.toLowerCase()} is required.`);
      }
    });
  });

  const sc = bp.stop_conditions || {};
  [["max_nodes", "Max pages"], ["max_depth", "Max depth"], ["max_duration", "Max duration"], ["no_progress_timeout", "No-progress timeout"]].forEach(([k, name]) => {
    if (sc[k] === undefined || sc[k] === "" || isNaN(Number(sc[k])))
      add(`bp-${k}`, `${name} must be a number.`);
  });

  return errors;
}

// ─── FORM ↔ BLUEPRINT CONVERSION ─────────────────────────────────────────────

export function blueprintToForm(bp) {
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

export function formToBlueprint(form) {
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
