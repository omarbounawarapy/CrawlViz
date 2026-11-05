// @vitest-environment node
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, it, expect } from "vitest";
import { ESLint } from "eslint";

import { featureBoundaryConfigs } from "./featureBoundaries.js";

// Runs the boundary rules (ARCH-2, ARCH-5) through ESLint on small snippets, so they are
// tested rather than assumed. Only the boundary blocks and a parser setting are used, so the
// result does not depend on the rest of eslint.config.js.
const uiRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const eslint = new ESLint({
  cwd: uiRoot,
  overrideConfigFile: true,
  overrideConfig: [
    {
      files: ["**/*.{js,jsx}"],
      languageOptions: { ecmaVersion: "latest", sourceType: "module", parserOptions: { ecmaFeatures: { jsx: true } } },
    },
    ...featureBoundaryConfigs,
  ],
});

async function boundaryMessages(file, source) {
  const [result] = await eslint.lintText(source, { filePath: path.join(uiRoot, file) });
  return result.messages.filter((m) => m.ruleId === "no-restricted-imports" || m.fatal);
}

describe("feature boundaries", () => {
  it("rejects a deep import into another feature", async () => {
    const messages = await boundaryMessages(
      "src/features/run/Example.jsx",
      'import NumberField from "../config/NumberField";\nexport const x = NumberField;\n',
    );
    expect(messages).toHaveLength(1);
    expect(messages[0].message).toMatch(/index/);
  });

  it("rejects a deep import from a nested folder of another feature", async () => {
    const messages = await boundaryMessages(
      "src/features/config/explainers/Example.jsx",
      'import { Chip } from "../../common/Form";\nexport const x = Chip;\n',
    );
    expect(messages).toHaveLength(1);
  });

  it("rejects a deep re-export from another feature", async () => {
    const messages = await boundaryMessages(
      "src/features/run/Example.jsx",
      'export { Explain } from "../config/Term";\n',
    );
    expect(messages).toHaveLength(1);
  });

  it("accepts another feature's index", async () => {
    const messages = await boundaryMessages(
      "src/features/run/Example.jsx",
      'import { NumberField } from "../config";\nexport const x = NumberField;\n',
    );
    expect(messages).toEqual([]);
  });

  it("accepts a feature's own inner files, in code and in tests", async () => {
    const code = 'import { buildFields } from "./configModel";\nexport const x = buildFields;\n';
    expect(await boundaryMessages("src/features/config/Example.jsx", code)).toEqual([]);
    expect(await boundaryMessages("src/features/config/Example.test.jsx", code)).toEqual([]);
  });

  it("rejects the app reaching inside a feature", async () => {
    const messages = await boundaryMessages(
      "src/Example.jsx",
      'import ConfigPage from "./features/config/ConfigPage";\nexport const x = ConfigPage;\n',
    );
    expect(messages).toHaveLength(1);
  });

  it("accepts the app using a feature's index", async () => {
    const messages = await boundaryMessages(
      "src/app/Example.jsx",
      'import { ConfigPage } from "../features/config";\nexport const x = ConfigPage;\n',
    );
    expect(messages).toEqual([]);
  });

  it("rejects shared code importing a feature or the app", async () => {
    const feature = await boundaryMessages(
      "src/shared/ui/Example.js",
      'import { Hint } from "../../features/common";\nexport const x = Hint;\n',
    );
    const app = await boundaryMessages(
      "src/shared/ui/Example.js",
      'import Shell from "../../app/Shell";\nexport const x = Shell;\n',
    );
    expect(feature).toHaveLength(1);
    expect(app).toHaveLength(1);
  });

  it("rejects a feature importing the app shell", async () => {
    const messages = await boundaryMessages(
      "src/features/run/Example.jsx",
      'import Shell from "../../app/Shell";\nexport const x = Shell;\n',
    );
    expect(messages).toHaveLength(1);
  });
});
