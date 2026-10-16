import { useEffect, useState } from "react";
import { getTheme } from "../../theme";
import { fetchProviders } from "../../api/client";
import ScrollRegion from "../common/ScrollRegion";

const theme = getTheme();
const { text, background } = theme.colors;

/** One row per LLM provider: where its requests go, which models blueprints use with it,
 *  and how many API keys are stored. The URL is the draft, so it reflects unsaved edits. */
export default function ProviderTable({ endpoints }) {
  const [providers, setProviders] = useState(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetchProviders()
      .then((p) => !cancelled && setProviders(p))
      .catch(() => !cancelled && setFailed(true));
    return () => { cancelled = true; };
  }, []);

  const names = Object.keys(endpoints ?? {});
  if (names.length === 0) return null;
  const cell = { padding: "6px 10px", textAlign: "left", verticalAlign: "top", borderBottom: `1px solid ${background.border}` };
  const head = { ...cell, fontSize: 12, color: text.muted, fontWeight: 600 };

  return (
    <ScrollRegion label="Providers table" style={{ margin: "8px 0 16px" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13, color: text.primary }}>
        <caption style={{ textAlign: "left", fontSize: 13, color: text.secondary, paddingBottom: 6 }}>
          Each provider, where its requests go, and what is stored for it.
        </caption>
        <thead>
          <tr>
            <th scope="col" style={head}>Provider</th>
            <th scope="col" style={head}>Request URL</th>
            <th scope="col" style={head}>Models used by blueprints</th>
            <th scope="col" style={head}>API keys</th>
          </tr>
        </thead>
        <tbody>
          {names.map((name) => {
            const info = providers?.[name];
            const keys = info?.keys ?? 0;
            return (
              <tr key={name}>
                <th scope="row" style={{ ...cell, fontWeight: 600 }}>{name}</th>
                <td style={{ ...cell, wordBreak: "break-all" }}>{endpoints[name]}</td>
                <td style={cell}>
                  {info ? (info.models.length ? info.models.join(", ") : "None yet") : failed ? "Unavailable" : "Loading"}
                </td>
                <td style={cell}>
                  {info ? (keys === 0 ? "No key stored" : `${keys} stored`) : failed ? "Unavailable" : "Loading"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </ScrollRegion>
  );
}
