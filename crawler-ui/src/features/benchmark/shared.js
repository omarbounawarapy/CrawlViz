import { useEffect, useState, useCallback } from "react";
import { getTheme } from "../../theme";

const { text, relevance } = getTheme().colors;

// Label 0/1/2 is graded relevance, so it rides the relevance ramp: neutral for 0,
// vermilion strengthening for 1 and 2. Shape (radius) repeats it.
export const LABEL = {
  // Pale fill, drawn with a 3:1 outline wherever it is a mark on its own (WCAG 1.4.11).
  0: { name: "Not relevant", fill: "#e3e8ee", ink: text.muted, r: 3 },
  1: { name: "Topical (1)", fill: relevance.ramp[2], ink: relevance.mark, r: 5 },
  2: { name: "Target (2)", fill: relevance.mark, ink: relevance.mark, r: 8 },
};

export const POLICY_ORDER = ["cascade", "no_llm", "llm_all", "anchor_lexical", "bfs", "random", "oracle"];

export const pct = (v, d = 0) => (v == null ? "n/a" : `${(v * 100).toFixed(d)}%`);
export const num = (v, d = 3) => (v == null ? "n/a" : Number(v).toFixed(d));

/** Load once, reload on demand. Returns {data, error, loading, reload}. */
export function useLoad(fn, deps = []) {
  const [state, setState] = useState({ data: null, error: null, loading: true });
  const run = useCallback(() => {
    let live = true;
    setState((s) => ({ ...s, loading: true }));
    fn().then(
      (data) => live && setState({ data, error: null, loading: false }),
      (e) => live && setState({ data: null, error: e.message, loading: false }),
    );
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  useEffect(() => run(), [run]);
  return { ...state, reload: run };
}
