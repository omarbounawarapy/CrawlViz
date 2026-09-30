import { getTheme } from "../../theme";

const theme = getTheme();
const { state, relevance } = theme.colors;
const STAGES = ["CREATED", "FETCHED", "FILTERED", "SCORED", "EXPANDED"];

// Plain-language key. Four ideas, four groups: lightness = how far the page
// got, vermilion ring = how promising it looked, square/diamond = links the
// crawler never turned into pages.
export default function Legend() {
  const label = { fontSize: 12, color: theme.colors.text.secondary };
  const group = { display: "flex", flexDirection: "column", gap: 6 };
  const head  = { fontSize: 12, fontWeight: 600, color: theme.colors.text.primary };

  return (
    <div
      role="group"
      aria-label="How to read the graph"
      style={{
        position: "absolute", left: 16, right: 16, bottom: 16, zIndex: 5, width: "fit-content", maxWidth: "calc(100% - 32px)",
        display: "flex", flexWrap: "wrap", gap: "12px 28px", alignItems: "flex-start",
        background: theme.colors.background.panel, border: `1px solid ${theme.colors.background.border}`,
        borderRadius: theme.radii.lg, padding: "10px 14px", fontFamily: theme.typography.fontMono,
      }}
    >
      <div style={group}>
        <span style={head}>How far it got</span>
        <svg width="148" height="22" aria-hidden="true">
          {STAGES.map((s, i) => (
            <circle key={s} cx={8 + i * 29} cy="11" r={5 + i * 1.2} fill={state[s]} stroke={state.label[s]} strokeWidth={s === "EXPANDED" ? 2 : 1} />
          ))}
        </svg>
        <span style={{ ...label, display: "flex", justifyContent: "space-between", width: 148 }}>
          <span>Found</span><span>Expanded</span>
        </span>
      </div>

      <div style={group}>
        <span style={head}>How promising</span>
        <svg width="96" height="22" aria-hidden="true">
          {[0.15, 0.5, 0.9].map((r, i) => (
            <g key={r}>
              <circle cx={12 + i * 34} cy="11" r="5" fill={state.FILTERED} />
              <circle cx={12 + i * 34} cy="11" r="8.5" fill="none" stroke={relevance.mark}
                strokeWidth={0.75 + r * 3.25} strokeOpacity={0.35 + r * 0.65} />
            </g>
          ))}
        </svg>
        <span style={{ ...label, display: "flex", justifyContent: "space-between", width: 96 }}>
          <span>Low</span><span>High</span>
        </span>
      </div>

      <div style={group}>
        <span style={head}>Never fetched</span>
        <span style={{ ...label, display: "flex", alignItems: "center", gap: 8 }}>
          <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
            <rect x="1.5" y="1.5" width="9" height="9" fill={theme.colors.background.primary} stroke={state.label.DROPPED} strokeDasharray="2 1.5" />
          </svg>
          Skipped as off-topic
        </span>
        <span style={{ ...label, display: "flex", alignItems: "center", gap: 8 }}>
          <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
            <path d="M6 0.5 11.5 6 6 11.5 0.5 6Z" fill={state.TRUSTED} />
          </svg>
          Followed without the LLM
        </span>
      </div>
    </div>
  );
}
