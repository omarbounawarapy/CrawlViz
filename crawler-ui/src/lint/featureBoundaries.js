// Feature boundaries as ESLint flat-config blocks (ARCH-2, ARCH-5; ADR 10, decision 5).
// A feature is a folder under `src/features/`. Other code reaches it only through
// `features/<name>/index.ts`; `shared/` reaches neither a feature nor `app/`; a feature never
// reaches `app/`. `eslint.config.js` spreads `featureBoundaryConfigs` into its list, and
// `featureBoundaries.test.js` runs these same blocks on small snippets.
//
// A rule block replaces the options of an earlier one, so each group of files gets exactly one
// block below. There is no baseline: every import in `src/` obeys these rules.
import { readdirSync } from "node:fs";

const featuresDir = new URL("../features/", import.meta.url);
const featureNames = readdirSync(featuresDir, { withFileTypes: true })
  .filter((entry) => entry.isDirectory())
  .map((entry) => entry.name);

const SCRIPT_FILES = "{js,jsx,ts,tsx}";
// App-level tests render several features at once and read the config fixtures.
const APP_TESTS = "src/*.test.{js,jsx}";

// `features/<name>/<file>` from anywhere outside the features folder.
const useIndex = (name) => ({
  regex: `(^|/)features/${name}/.+`,
  message: `Import the ${name} feature through its index ("features/${name}"), not a file inside it.`,
});
// `../<name>/<file>` from inside another feature.
const useIndexFromSibling = (name) => ({
  regex: `^(\\.\\./)+${name}/.+`,
  message: `Import the ${name} feature through its index ("../${name}"), not a file inside it.`,
});
const noApp = {
  regex: "(^|/)app(/|$)",
  message: "Features and shared code do not import the app shell; the app imports them.",
};
const noFeatures = {
  regex: "(^|/)features(/|$)",
  message: "Shared code does not import features; features import shared code.",
};
const restrict = (patterns) => ({ "no-restricted-imports": ["error", { patterns }] });

export const featureBoundaryConfigs = [
  {
    name: "boundaries/app-and-top-level",
    files: [`src/**/*.${SCRIPT_FILES}`],
    ignores: ["src/features/**", "src/shared/**", APP_TESTS],
    rules: restrict(featureNames.map(useIndex)),
  },
  ...featureNames.map((own) => ({
    name: `boundaries/features/${own}`,
    files: [`src/features/${own}/**/*.${SCRIPT_FILES}`],
    rules: restrict([
      ...featureNames.filter((name) => name !== own).flatMap((name) => [useIndex(name), useIndexFromSibling(name)]),
      noApp,
    ]),
  })),
  {
    name: "boundaries/shared",
    files: [`src/shared/**/*.${SCRIPT_FILES}`],
    rules: restrict([noFeatures, noApp]),
  },
];
