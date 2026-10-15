// Pure helpers for the prompt studio.

export const STRATEGY_HELP = {
  TOPICAL: "Stay on the subject. Best when you want pages that are about the target itself.",
  PATHFINDING: "Reward stepping stones. Best when the target sits a few clicks inside a site.",
  EXPLORATION: "Reward variety. Best early in a crawl, or to map an unfamiliar area.",
  GOAL_ORIENTED: "Reward links that help finish a concrete objective.",
  DENSITY_FOCUSED: "Reward content-rich pages such as definitions and explanations.",
  UNCERTAINTY_BIASED: "Reward ambiguous links that may open a new semantic area.",
};

/** Rough token count (about four characters per token in English). */
export const estimateTokens = (text) => Math.ceil((text ?? "").length / 4);

/**
 * Line diff of `before` against `after`, as [{ kind: "same" | "add" | "del", text }],
 * from the longest common subsequence of lines.
 */
export function lineDiff(before = "", after = "") {
  const a = before.split("\n");
  const b = after.split("\n");
  const lcs = Array.from({ length: a.length + 1 }, () => new Array(b.length + 1).fill(0));
  for (let i = a.length - 1; i >= 0; i--) {
    for (let j = b.length - 1; j >= 0; j--) {
      lcs[i][j] = a[i] === b[j] ? lcs[i + 1][j + 1] + 1 : Math.max(lcs[i + 1][j], lcs[i][j + 1]);
    }
  }
  const out = [];
  let i = 0;
  let j = 0;
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) { out.push({ kind: "same", text: a[i] }); i++; j++; }
    else if (lcs[i + 1][j] >= lcs[i][j + 1]) { out.push({ kind: "del", text: a[i++] }); }
    else { out.push({ kind: "add", text: b[j++] }); }
  }
  while (i < a.length) out.push({ kind: "del", text: a[i++] });
  while (j < b.length) out.push({ kind: "add", text: b[j++] });
  return out;
}
