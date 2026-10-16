import axe from "axe-core";

/**
 * Runs axe-core on a rendered node and returns its violations as readable lines, so a failing
 * test names the rule and the elements. jsdom does no layout, so colour contrast is left to the
 * contrast check in the audit notes; `region` is off for parts rendered outside a full page.
 */
export async function axeViolations(node, { page = false, rules = {} } = {}) {
  const result = await axe.run(node, {
    resultTypes: ["violations"],
    rules: { "color-contrast": { enabled: false }, region: { enabled: page }, ...rules },
  });
  return result.violations.map((v) => `${v.id}: ${v.help}\n    ${v.nodes.map((n) => n.target.join(" ")).join("\n    ")}`);
}

/** Every <label for> must point at an element a label can name. */
export function orphanLabels(root) {
  const labelable = new Set(["INPUT", "SELECT", "TEXTAREA", "BUTTON", "METER", "OUTPUT", "PROGRESS"]);
  return [...root.querySelectorAll("label[for]")]
    .filter((l) => !labelable.has(root.ownerDocument.getElementById(l.htmlFor)?.tagName))
    .map((l) => `label for="${l.htmlFor}" (${l.textContent.trim()})`);
}
