/**
 * The config feature's public surface (ARCH-2). Other areas import from here and never from
 * a file inside this folder.
 *
 * `NumberField`, `Explain` and `useCrawlCost` serve three features and belong in `shared/`;
 * they are listed here until they move.
 */
export { default as ConfigPage } from "./ConfigPage";
export { default as NumberField } from "./NumberField";
export { default as SettingsEditor } from "./SettingsEditor";
export { Explain } from "./Term";
export { useCrawlCost } from "./crawlCost";
export { buildFields, buildPatch, buildSections, sectionSlug, setIn } from "./configModel";
export { presetChanges, shown } from "./presetModel";
