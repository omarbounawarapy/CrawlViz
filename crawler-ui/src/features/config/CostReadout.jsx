import { useMemo, useState } from "react";
import { getTheme } from "../../theme";
import { llmCost } from "./costModel";
import NumberField from "./NumberField";
import sample from "./explainers/sampleData.json";

const theme = getTheme();
const { text } = theme.colors;

const n = (v) => Math.round(v).toLocaleString("en-US");

/**
 * The LLM cost of the cascade settings: one example page, and a crawl of 100 pages like it.
 * With `priced`, an optional price per million tokens turns the token count into dollars. The
 * price is typed here for the estimate only; it is not saved.
 */
export default function CostReadout({ cascade, nlp, llm, prompts, priced = false }) {
  const [price, setPrice] = useState(null);
  const c = useMemo(
    () => llmCost({ cascade, nlp, llm, prompts, scores: sample.cascadeScores }),
    [cascade, nlp, llm, prompts],
  );
  const crawlCalls = c.callsPerPage * 100;
  const crawlTokens = c.tokensPerPage * 100;
  const dollars = priced && price !== null ? (crawlTokens / 1e6) * price : null;
  return (
    <div style={{ margin: "8px 0 14px", maxWidth: "62ch", fontSize: 14, color: text.primary }}>
      <div style={{ fontWeight: 600, marginBottom: 4 }}>LLM cost (estimate)</div>
      <p style={{ margin: "0 0 4px" }}>
        On the example page, {c.linksToLlm} of {c.total} links go to the LLM in {c.callsPerPage} call
        {c.callsPerPage === 1 ? "" : "s"}, about {n(c.tokensPerPage)} tokens. A token is about four characters of
        English text.
      </p>
      <p style={{ margin: 0, color: text.secondary, fontSize: 13 }}>
        {c.cap === null
          ? `No call cap. A crawl of 100 pages like this one makes about ${n(crawlCalls)} calls and about ${n(crawlTokens)} tokens` +
            (dollars !== null ? `, about $${dollars.toFixed(2)} at the price you typed.` : ".")
          : `Call cap ${n(c.cap)} per crawl, enough for about ${n(c.pagesWithinCap ?? 0)} pages like this one. Past the cap the rest is scored on NLP alone.`}
      </p>
      {priced && (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 10,
            flexWrap: "wrap",
            marginTop: 8,
            fontSize: 13,
            color: text.secondary,
          }}
        >
          <label id="llm-token-price-label" htmlFor="llm-token-price">
            Price per million input tokens (for this estimate only, not saved)
          </label>
          <NumberField
            id="llm-token-price"
            value={price}
            nullable
            width={90}
            unit="$"
            onChange={(v) => setPrice(v === "" ? null : v)}
          />
        </div>
      )}
    </div>
  );
}
