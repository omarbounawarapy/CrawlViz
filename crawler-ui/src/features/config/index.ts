/**
 * The config feature's public surface (ARCH-2). Other areas import from here and never from
 * a file inside this folder.
 *
 * `Explain` serves three features and belongs in `shared/ui`; it is listed here until it moves.
 * `useCrawlCost` stays: it prices a crawl from the config feature's own cost model and sample
 * page, which `shared/` may not import.
 */
export { default as ConfigPage } from "./ConfigPage";
export { default as SettingsEditor } from "./SettingsEditor";
export { Explain } from "./Term";
export { useCrawlCost } from "./crawlCost";
export { buildFields, buildPatch, buildSections, sectionSlug, setIn } from "./configModel";
export { presetChanges, shown } from "./presetModel";
