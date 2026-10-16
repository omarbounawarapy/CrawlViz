import { useState } from "react";
import { getTheme } from "../../../theme";
import NumberField from "../NumberField";
import PolitenessCard from "./PolitenessCard";
import BackoffChart from "./BackoffChart";

const theme = getTheme();
const { text } = theme.colors;

export const DEFAULT_LATENCY = 0.3;

/**
 * Pictures of the Fetch section. The one assumption they share, how long a
 * request takes, is an input here: it is not saved, and it is named on the page.
 */
export default function FetchExplainers({ cfg, workers, maxRetries, onChange }) {
  const [latency, setLatency] = useState(DEFAULT_LATENCY);
  return (
    <>
      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", fontSize: 13, color: text.secondary, margin: "4px 0 0" }}>
        <label id="assumed-latency-label" htmlFor="assumed-latency">Assumed time per request (for the pictures only, not saved)</label>
        <NumberField id="assumed-latency" value={latency} unit="s" width={80}
                     onChange={(v) => setLatency(v === "" || v === null ? DEFAULT_LATENCY : v)} />
      </div>
      <PolitenessCard cfg={cfg} workers={workers} maxRetries={maxRetries} latency={latency} />
      <BackoffChart cfg={cfg} latency={latency} onMinDelay={(v) => onChange?.("fetch.min_delay", v)} />
    </>
  );
}
