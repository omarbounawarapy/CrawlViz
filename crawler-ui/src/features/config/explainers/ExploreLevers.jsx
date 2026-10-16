import { getTheme } from "../../../theme";

const theme = getTheme();
const { text } = theme.colors;

/**
 * Exploring more of the web is set by four levers in four places. This names them
 * together so the Scoring cascade section does not read as the whole story.
 */
const EXPLORE_LEVERS = [
  { section: "Scoring cascade", label: "Low-score links kept for exploration",
    note: "More links the NLP score doubts reach the LLM, so more of the web is looked at." },
  { section: "Priority", label: "Default priority strategy",
    note: "The Exploration card favours pages unlike those already seen." },
  { section: "Priority", label: "NLP and LLM share of priority",
    note: "A larger NLP share lets the cheap score decide more of the queue order." },
  { section: "Prompts", label: "Scoring focus wording",
    note: "The focus line in the prompt tells the LLM what to reward." },
];

export default function ExploreLevers({ onOpen }) {
  return (
    <div style={{ margin: "8px 0 16px", maxWidth: "62ch" }}>
      <p style={{ fontSize: 14, color: text.primary, margin: "0 0 6px" }}>
        Exploring more is set by four levers, each in its own section:
      </p>
      <ul style={{ margin: 0, paddingLeft: 18, display: "flex", flexDirection: "column", gap: 4 }}>
        {EXPLORE_LEVERS.map((lever) => (
          <li key={lever.label} style={{ fontSize: 13, color: text.secondary }}>
            <button type="button" onClick={() => onOpen(lever.section)}
                    style={{ font: "inherit", color: text.primary, background: "none", border: "none", padding: 0,
                             textDecoration: "underline", cursor: "pointer" }}>
              {lever.label}
            </button>
            {" "}({lever.section}). {lever.note}
          </li>
        ))}
      </ul>
    </div>
  );
}
