import { useEffect, useMemo, useRef, useState } from "react";
import { getTheme } from "../../theme";
import { Button } from "../common/Form";
import { previewPrompt } from "../../api/client";
import { STRATEGY_HELP, estimateTokens, lineDiff } from "./promptModel";
import { nextChoice } from "../common/choiceKeys";

const theme = getTheme();
const { text, background, accent } = theme.colors;

const boxStyle = {
  width: "100%", minHeight: 96, font: "13px/1.5 ui-monospace, monospace", padding: 10, resize: "vertical",
  color: text.primary, background: background.primary, border: `1px solid ${theme.colors.control}`, borderRadius: theme.radii.md,
};
const readBox = { ...boxStyle, border: `1px solid ${background.border}` };   // read-only text: no control boundary

function Diff({ before, after }) {
  const lines = lineDiff(before, after);
  if (lines.every((l) => l.kind === "same")) return <p style={{ fontSize: 13, color: text.muted }}>Same as the built-in wording.</p>;
  return (
    <figure style={{ margin: "6px 0 0" }}>
      <figcaption className="sr-only">Difference from the built-in wording. Added lines start with plus, removed lines with minus.</figcaption>
      <pre style={{ ...readBox, minHeight: 0, whiteSpace: "pre-wrap", margin: 0 }}>
        {lines.map((l, i) => (
          <div key={i} style={{ color: l.kind === "add" ? accent.green : l.kind === "del" ? accent.red : text.secondary }}>
            {l.kind === "add" ? "+ " : l.kind === "del" ? "- " : "  "}{l.text}
          </div>
        ))}
      </pre>
    </figure>
  );
}

/** One editable block: textarea, size estimate, reset to built-in, diff. */
function EditableBlock({ id, title, note, value, builtin, onChange }) {
  const [diff, setDiff] = useState(false);
  const changed = value !== builtin;
  return (
    <div style={{ padding: "12px 0", borderBottom: `1px solid ${theme.colors.rowBorder}` }}>
      <label htmlFor={id} style={{ fontSize: 14, fontWeight: 600, color: text.primary }}>{title}</label>
      <p id={`${id}-note`} style={{ fontSize: 13, color: text.secondary, margin: "2px 0 6px" }}>{note}</p>
      <textarea id={id} value={value} onChange={(e) => onChange(e.target.value)} style={boxStyle}
                aria-describedby={`${id}-note ${id}-size`} />
      <div style={{ display: "flex", gap: 10, alignItems: "center", marginTop: 4, flexWrap: "wrap" }}>
        <span id={`${id}-size`} style={{ fontSize: 12, color: text.muted }}>{value.length} characters, about {estimateTokens(value)} tokens</span>
        <span style={{ flex: 1 }} />
        <Button variant="quiet" disabled={!changed} onClick={() => setDiff((d) => !d)} aria-pressed={diff}>Show changes</Button>
        <Button variant="quiet" disabled={!changed} onClick={() => onChange(builtin)} aria-label={`Restore built-in ${title}`}>Restore built-in</Button>
      </div>
      {diff && changed && <Diff before={builtin} after={value} />}
    </div>
  );
}

/**
 * The scoring prompt as the model receives it: named blocks, the editable ones open for
 * editing, the fixed ones shown with the reason, and the assembled prompt rendered by the backend.
 */
export default function PromptStudio({ prompts, defaults, onChange, preview = previewPrompt, target = "bananas" }) {
  const strategies = Object.keys(prompts.strategy_contexts);
  const [strategy, setStrategy] = useState(strategies[0]);
  const focusRefs = useRef([]);
  const [view, setView] = useState({ state: "loading" });
  const [showFull, setShowFull] = useState(false);
  const draftKey = JSON.stringify([prompts, strategy, target]);

  useEffect(() => {
    let live = true;
    setView((v) => (v.blocks ? v : { state: "loading" }));
    const timer = setTimeout(() => {
      preview({ target, strategy, scoring_system: prompts.scoring_system, scoring_rules: prompts.scoring_rules,
                strategy_contexts: prompts.strategy_contexts })
        .then((r) => live && setView({ state: "ok", blocks: r.blocks, prompt: r.prompt }))
        .catch((e) => live && setView({ state: "error", message: e.message }));
    }, 250);
    return () => { live = false; clearTimeout(timer); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draftKey]);

  const contextValue = prompts.strategy_contexts[strategy] ?? "";
  const builtinContext = defaults.strategy_contexts[strategy] ?? "";
  const tokens = useMemo(() => (view.prompt ? estimateTokens(view.prompt) : null), [view.prompt]);
  const fixed = (view.blocks ?? []).filter((b) => b.kind !== "editable");

  return (
    <div style={{ margin: "8px 0 24px" }}>
      <EditableBlock id="prompt-system" title="System prompt" value={prompts.scoring_system}
                     builtin={defaults.scoring_system} note="Who the model is and what it must return. First thing it reads."
                     onChange={(v) => onChange("prompts.scoring_system", v)} />
      <div style={{ padding: "12px 0 0" }}>
        <h3 style={{ fontSize: 14, fontWeight: 600, color: text.primary, margin: 0 }}>Scoring focus wording</h3>
        <p style={{ fontSize: 13, color: text.secondary, margin: "2px 0 8px", maxWidth: "62ch" }}>
          One sentence per scoring focus that tilts how the model scores. These are the LLM's focuses, not the priority
          strategies on the Priority page. Each blueprint picks one focus with its scoring strategy (scoring.strategy).
        </p>
        <div role="tablist" aria-label="Scoring focuses" style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          {strategies.map((s, i) => (
            <button key={s} role="tab" type="button" aria-selected={s === strategy} tabIndex={s === strategy ? 0 : -1}
                    id={`prompt-focus-tab-${s}`} aria-controls={s === strategy ? "prompt-focus-panel" : undefined}
                    ref={(el) => { focusRefs.current[i] = el; }}
                    onKeyDown={(e) => {
                      const n = nextChoice(e, i, strategies.length);
                      if (n === null) return;
                      setStrategy(strategies[n]);
                      focusRefs.current[n]?.focus();
                    }}
                    onClick={() => setStrategy(s)}
                    style={{
                      font: "inherit", fontSize: 13, padding: "4px 10px", cursor: "pointer", color: text.primary,
                      background: s === strategy ? "rgba(15,27,45,0.06)" : "transparent",
                      border: `${s === strategy ? 2 : 1}px solid ${s === strategy ? text.primary : theme.colors.control}`,
                      borderRadius: theme.radii.md,
                    }}>
              {s.replace(/_/g, " ").toLowerCase()}
            </button>
          ))}
        </div>
        <div role="tabpanel" id="prompt-focus-panel" aria-labelledby={`prompt-focus-tab-${strategy}`}>
          <EditableBlock id="prompt-strategy" title={`Wording for the ${strategy.replace(/_/g, " ").toLowerCase()} focus`}
                         note={STRATEGY_HELP[strategy] ?? "Soft bias added to the context block."}
                         value={contextValue} builtin={builtinContext}
                         onChange={(v) => onChange("prompts.strategy_contexts", { ...prompts.strategy_contexts, [strategy]: v })} />
        </div>
      </div>
      <EditableBlock id="prompt-rules" title="Rules" value={prompts.scoring_rules}
                     builtin={defaults.scoring_rules} note="The scoring rules, placed after the candidate links."
                     onChange={(v) => onChange("prompts.scoring_rules", v)} />

      <div style={{ padding: "12px 0" }}>
        <h3 style={{ fontSize: 14, fontWeight: 600, color: text.primary, margin: 0 }}>Fixed parts</h3>
        {view.state === "error" && <p role="alert" style={{ fontSize: 13, color: accent.red }}>Preview unavailable: {view.message}</p>}
        <ul style={{ listStyle: "none", margin: "6px 0 0", padding: 0 }}>
          {fixed.map((b) => (
            <li key={b.id} style={{ fontSize: 13, color: text.secondary, padding: "3px 0" }}>
              <strong style={{ color: text.primary }}>{b.title}</strong>
              {b.kind === "locked" && <span style={{ fontSize: 12, color: text.muted }}> (locked)</span>}: {b.note}
            </li>
          ))}
        </ul>
      </div>

      <div style={{ padding: "8px 0" }}>
        <Button variant="quiet" aria-pressed={showFull} onClick={() => setShowFull((v) => !v)}>
          {showFull ? "Hide the full prompt" : "Show the full prompt"}
        </Button>
        {tokens != null && <>{" "}<span style={{ fontSize: 12, color: text.muted, marginLeft: 8 }}>about {tokens} tokens for 3 sample links</span></>}
        {showFull && view.blocks && (
          <div role="region" aria-label="Full prompt preview" style={{ marginTop: 8 }}>
            {view.blocks.map((b) => (
              <pre key={b.id} style={{ ...readBox, minHeight: 0, whiteSpace: "pre-wrap", margin: "0 0 6px",
                                       background: b.kind === "editable" ? background.primary : "rgba(15,27,45,0.04)" }}>
                {b.text}
              </pre>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
