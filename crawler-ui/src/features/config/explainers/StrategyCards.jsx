import { useMemo, useRef } from "react";
import { getTheme } from "../../../theme";
import ExplainerFrame from "./ExplainerFrame";
import useReducedMotion from "./useReducedMotion";
import { FEATURES, priorityParts, rank, topFiveSummary, weightTotal } from "./strategyModel";
import sample from "./sampleData.json";
import { Button } from "../../common/Form";
import { nextChoice } from "../../common/choiceKeys";

const theme = getTheme();
const { text, background } = theme.colors;

const STRATEGIES = [
  { key: "aggressive", title: "Aggressive", blurb: "Heads straight for the topic. Strong links first, deep pages are penalised." },
  { key: "balanced", title: "Balanced", blurb: "Mixes relevance with some novelty. A safe default." },
  { key: "exploration", title: "Exploration", blurb: "Seeks out pages unlike what was already seen. The LLM score matters less." },
];
const ROW = 34, BAR_W = 200;
// Parts of a bar: four inks that each keep 3:1 on the card (WCAG 1.4.11), solid and then
// hatched, so eight parts stay apart without leaning on lightness alone. Segments are also
// split by a thin gap. The LLM part is vermilion.
const INKS = ["#0f1b2d", "#33435a", "#56657a", "#707d90"];
const FILLS = [...INKS.map((c, i) => ({ id: `sc-fill-${i}`, color: c, hatch: false })),
               ...INKS.map((c, i) => ({ id: `sc-fill-${i + 4}`, color: c, hatch: true }))];
const LLM_FILL = "#c7311a";

function FillDefs() {
  return (
    <svg width="0" height="0" aria-hidden="true" focusable="false" style={{ position: "absolute" }}>
      <defs>
        {FILLS.filter((f) => f.hatch).map((f) => (
          <pattern key={f.id} id={f.id} width="4" height="4" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <rect width="4" height="4" fill="#fbfcfd" />
            <rect width="2" height="4" fill={f.color} />
          </pattern>
        ))}
      </defs>
    </svg>
  );
}
const paint = (f) => (f.hatch ? `url(#${f.id})` : f.color);

// What each weight measures, in the words the card shows under its name. Matches the features
// in nlp/feature_extractor.py; a feature without a line here is shown by its name alone.
const FEATURE_HINT = {
  target_similarity: "How close the link is to the topic's reference texts",
  novelty_injection: "How unlike the pages already seen it is",
  coverage_gap: "Close to the topic, in a region the crawl has barely covered",
  contextual_consistency: "Whether the text around the link matches the page it sits on",
  lexical_overlap: "Words shared by the link's anchor text and the page that linked to it",
  cluster_distance: "How far it is from the nearest cluster of pages seen so far",
  semantic_delta: "How far its meaning moves from the page that linked to it",
  region_density: "How many pages already seen lie close to it",
  anchor_similarity: "How close its anchor text is to the topic",
  parent_relevance: "How relevant the page that linked to it was",
  boilerplate_score: "How much it looks like site furniture (contact, privacy, copyright)",
  depth_penalty: "Subtracted for each level of depth",
};

/**
 * The three priority strategies as cards. The chosen card is the crawl's default strategy
 * (scoring_cascade.default_priority_strategy) and ranks the same eight example links with its
 * own weights, drawn as stacked contributions; editing a weight re-sorts the list.
 */
export default function StrategyCards({ priority, defaults, defaultStrategy, onChange }) {
  const active = STRATEGIES.some((s) => s.key === defaultStrategy) ? defaultStrategy : "balanced";
  const cardRefs = useRef([]);
  const reduced = useReducedMotion();
  const nlpBias = Number(priority?.nlp_bias ?? 60);
  const llmBias = Number(priority?.llm_bias ?? 40);
  const summaries = Object.fromEntries(STRATEGIES.map((s) => [
    s.key, topFiveSummary(sample.strategyLinks, priority?.[`${s.key}_weights`] ?? {}, nlpBias, llmBias),
  ]));
  // The first strategy whose top five is the same five links, so two cards are not read as two results.
  const twinOf = (key) => {
    const mine = summaries[key].labels.join("|");
    const earlier = STRATEGIES.find((s) => s.key !== key && summaries[s.key].labels.join("|") === mine);
    return earlier && STRATEGIES.indexOf(earlier) < STRATEGIES.findIndex((s) => s.key === key) ? earlier : null;
  };
  const weights = useMemo(() => priority?.[`${active}_weights`] ?? {}, [priority, active]);
  const base = defaults?.[`${active}_weights`] ?? {};
  const nlp = Number(priority?.nlp_bias ?? 60);
  const llm = Number(priority?.llm_bias ?? 40);

  const order = useMemo(() => rank(sample.strategyLinks, weights, nlp, llm), [weights, nlp, llm]);
  const results = useMemo(
    () => sample.strategyLinks.map((l) => priorityParts(l, weights, nlp, llm)),
    [weights, nlp, llm],
  );
  const scale = Math.max(...results.map((r) => r.total), 1e-6);
  const keys = [...new Set([...FEATURES, ...Object.keys(weights)])].filter((k) => k !== "depth_penalty");
  const barKeys = [...new Set(results.flatMap((r) => r.parts.filter((p) => p.value > 0).map((p) => p.key)))];
  const legend = [
    ...barKeys.map((k, i) => ({ key: k, name: k.replace(/_/g, " "), fill: paint(FILLS[i % FILLS.length]) })),
    { key: "llm", name: "LLM score", fill: LLM_FILL },
  ];
  const fillOf = Object.fromEntries(legend.map((l) => [l.key, l.fill]));
  const set = (key, v) => onChange(`priority.${active}_weights`, { ...weights, [key]: v });
  const modified = JSON.stringify(weights) !== JSON.stringify(base);

  return (
    <ExplainerFrame title="Priority strategies" summary="Higher is crawled sooner. Bars add up the parts of each link's score.">
      <FillDefs />
      <div role="radiogroup" aria-label="Priority strategy, which orders the queue" style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
        {STRATEGIES.map((s, i) => {
          const on = s.key === active;
          const top = summaries[s.key];
          return (
            <button key={s.key} type="button" role="radio" aria-checked={on} tabIndex={on ? 0 : -1}
                    ref={(el) => { cardRefs.current[i] = el; }}
                    onKeyDown={(e) => {
                      const n = nextChoice(e, i, STRATEGIES.length);
                      if (n === null) return;
                      onChange("scoring_cascade.default_priority_strategy", STRATEGIES[n].key);
                      cardRefs.current[n]?.focus();
                    }}
                    onClick={() => onChange("scoring_cascade.default_priority_strategy", s.key)}
                    style={{
                      flex: "1 1 180px", minWidth: 0, textAlign: "left", padding: "8px 10px", cursor: "pointer", font: "inherit",
                      background: on ? "rgba(15,27,45,0.06)" : "transparent", color: text.primary,
                      border: `${on ? 2 : 1}px solid ${on ? text.primary : theme.colors.control}`, borderRadius: theme.radii.md,
                    }}>
              <span style={{ display: "block", fontSize: 14, fontWeight: 600 }}>{s.title}</span>
              <span style={{ display: "block", fontSize: 13, color: text.secondary, marginTop: 2 }}>{s.blurb}</span>
              <span style={{ display: "block", fontSize: 12, color: text.muted, marginTop: 6 }}>
                Top {top.count} of the example page: {top.offTopic} off topic, average depth {top.depth}.
                {twinOf(s.key) && ` Same five links as ${twinOf(s.key).title}.`}
              </span>
              {on && <span style={{ display: "block", fontSize: 12, fontWeight: 600, color: text.primary, marginTop: 4 }}>Default strategy</span>}
            </button>
          );
        })}
      </div>

      <p style={{ fontSize: 13, color: text.secondary, margin: "0 0 8px" }}>
        {sample.strategyTarget.note} Eight links found on one page, ranked by the {active} strategy.
        Click a card to make it the default for crawls that do not choose one.
      </p>
      <p style={{ fontSize: 12, color: text.muted, margin: "0 0 6px" }}>
        Bar length: priority score, split into the parts that add it up. The number on the right is the total (higher is crawled sooner).
      </p>
      <ol aria-label={`Example links in ${active} order`} style={{ listStyle: "none", margin: "0 0 4px", padding: 0, position: "relative", height: ROW * order.length }}>
        {order.map((idx, pos) => {
          const link = sample.strategyLinks[idx];
          const r = results[idx];
          let offset = 0;
          const segs = [...r.parts.filter((p) => p.value > 0), { key: "llm", value: r.llm }].filter((s) => s.value > 0);
          return (
            <li key={link.label} style={{
              position: "absolute", left: 0, right: 0, top: pos * ROW, height: ROW, display: "flex", alignItems: "center", gap: 8,
              // Opaque, so a row sliding past another hides it rather than printing over it.
              background: background.panel, zIndex: order.length - pos,
              transition: reduced ? "none" : "top 320ms ease",
            }}>
              <span style={{ flex: "1 1 auto", minWidth: 0, fontSize: 13, lineHeight: 1.2, color: text.primary }}>
                {link.label}
                <span style={{ color: text.muted }}> · depth {link.depth}</span>
              </span>
              {/* The bar's name lists every part, so the split is read, not only seen (WCAG 1.1.1). */}
              <svg viewBox={`0 0 ${BAR_W} 16`} preserveAspectRatio="none" height="16" role="img"
                   style={{ width: `min(${BAR_W}px, 42%)`, flexShrink: 0 }}
                   aria-label={`Priority ${r.total.toFixed(1)}: ${segs.map((g) => `${g.key === "llm" ? "LLM score" : g.key.replace(/_/g, " ")} ${g.value.toFixed(2)}`).join(", ")}`}>
                {segs.map((g) => {
                  const w = (g.value / scale) * BAR_W;
                  const el = <rect key={g.key} x={offset} y="0" width={Math.max(w, 0)} height="16" fill={fillOf[g.key]}
                                   stroke={background.panel} strokeWidth="1" />;
                  offset += w;
                  return el;
                })}
              </svg>
              <span aria-hidden="true" style={{ fontSize: 13, color: text.secondary, fontVariantNumeric: "tabular-nums", flexShrink: 0 }}>{r.total.toFixed(1)}</span>
            </li>
          );
        })}
      </ol>

      {/* The scale: bars share one length per unit, so the longest bar is the largest total on this page. */}
      <div aria-hidden="true" style={{ display: "flex", alignItems: "center", gap: 8, margin: "0 0 8px", fontSize: 12, color: text.muted }}>
        <span style={{ flex: "1 1 auto" }} />
        <span style={{ width: `min(${BAR_W}px, 42%)`, flexShrink: 0, marginRight: 36, display: "flex", justifyContent: "space-between", borderTop: `1px solid ${background.border}`, paddingTop: 2 }}>
          <span>0</span>
          <span>{scale.toFixed(1)} (longest bar)</span>
        </span>
      </div>
      <ul aria-label="Bar parts" style={{ listStyle: "none", padding: 0, display: "flex", flexWrap: "wrap", gap: "2px 14px", margin: "0 0 14px", fontSize: 12, color: text.secondary }}>
        {legend.map((l) => (
          <li key={l.key} style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
            <svg width="12" height="12" aria-hidden="true"><rect width="12" height="12" fill={l.fill} /></svg>{l.name}
          </li>
        ))}
      </ul>

      <details open>
        <summary style={{ fontSize: 13, fontWeight: 600, cursor: "pointer", marginBottom: 6 }}>
          Weights of the {active} strategy
        </summary>
        <p style={{ fontSize: 13, color: text.secondary, margin: "0 0 6px", maxWidth: "60ch" }}>
          The weights add up to {weightTotal(weights).toFixed(2)}. They are not divided by that total, so a bigger total lifts the
          NLP part of every link's priority; the NLP share above scales it.
        </p>
        {[...keys, "depth_penalty"].map((k) => {
          const v = weights[k] ?? 0;
          return (
            <div key={k} style={{ display: "grid", gridTemplateColumns: "minmax(0, 240px) minmax(80px, 1fr) 48px", alignItems: "center", gap: 10, padding: "3px 0" }}>
              <span style={{ fontSize: 13 }}>
                {k.replace(/_/g, " ")}
                {FEATURE_HINT[k] && (
                  <span id={`sc-w-${k}-hint`} style={{ display: "block", fontSize: 12, color: text.muted }}>{FEATURE_HINT[k]}</span>
                )}
              </span>
              <input type="range" min="0" max={k === "depth_penalty" ? 0.3 : 1} step="0.01" value={v}
                     aria-label={`${active} ${k.replace(/_/g, " ")}`}
                     aria-describedby={FEATURE_HINT[k] ? `sc-w-${k}-hint` : undefined}
                     onChange={(e) => set(k, Number(e.target.value))} />
              <span aria-hidden="true" style={{ fontSize: 13, fontVariantNumeric: "tabular-nums", color: text.secondary }}>{v.toFixed(2)}</span>
            </div>
          );
        })}
        <Button variant="quiet" style={{ padding: 0, marginTop: 6 }} disabled={!modified}
                onClick={() => onChange(`priority.${active}_weights`, { ...base })}>
          Reset {active} to default
        </Button>
      </details>
    </ExplainerFrame>
  );
}
