/**
 * The config feature's public surface (ARCH-2). Other areas import from here and never from
 * a file inside this folder.
 *
 * `GlossaryScope` fills the shared Term and Explain with the backend glossary. `useCrawlCost`
 * stays here: it prices a crawl from the config feature's own cost model and sample
 * page, which `shared/` may not import.
 */
export { default as ConfigPage } from "./ConfigPage";
export { default as GlossaryScope } from "./GlossaryScope";
export { default as SettingsEditor } from "./SettingsEditor";
export { useCrawlCost } from "./crawlCost";
export { buildFields, buildPatch, buildSections, sectionSlug, setIn } from "./configModel";
export { presetChanges, shown } from "./presetModel";
