// /theme/themes/plate.js
//
// The "plate" theme: cool paper, blue-black ink, hairline rules.
//
// Colour discipline (the whole point of the theme):
//   - Lifecycle stage is ONE neutral ink ramp, ordered by lightness
//     (lighter = earlier, darker = further along). No hue to memorise.
//   - Vermilion (`relevance`) is reserved for relevance -- how promising the
//     crawler judged a link. It appears nowhere else.
//   - Structural role and outcome ride on shape and stroke, never on hue
//     (see features/graph/GraphView.jsx).
// Text pairs below are >= 4.5:1 on `background.primary`.

const paper  = "#f3f5f7";
const sheet  = "#fbfcfd";
const rule   = "#d3d9e0";
const ink    = "#0f1b2d";
const ink2   = "#33435a";    // 8.6:1 on paper
const muted  = "#566478";    // 5.4:1 on paper
const vermilion = "#c7311a"; // 4.6:1 on paper

const plate = {
  colors: {
    background: { primary: paper, panel: sheet, border: rule },
    text: { primary: ink, secondary: ink2, muted },

    accent: {
      blue: ink, blueDim: ink2, gold: ink2,
      green: ink, red: "#7a1f5c", purple: ink2,
    },

    relevance: {
      mark: vermilion,
      tint: "rgba(199,49,26,0.10)",
      ramp: ["#ecd5cf", "#e3a496", "#d56a52", vermilion],
    },

    state: {
      // Fills: one neutral ramp, lightness = progress through the lifecycle.
      CREATED:  "#e3e8ee",
      FETCHED:  "#b7c1cd",
      FILTERED: "#8794a5",
      SCORED:   "#56657a",
      EXPANDED: ink,
      // Candidate decisions (never full nodes) -- drawn as squares.
      DROPPED:  "transparent",
      TRUSTED:  ink2,
      ERROR:    "#7a1f5c",
      label: {
        CREATED:  "#7b889a",
        FETCHED:  "#56657a",
        FILTERED: "#3d4c62",
        SCORED:   "#26364d",
        EXPANDED: ink,
        DROPPED:  muted,
        TRUSTED:  ink2,
        ERROR:    "#7a1f5c",
      },
      glow: {
        CREATED: "transparent", FETCHED: "transparent", FILTERED: "transparent",
        SCORED: "transparent", EXPANDED: "transparent", DROPPED: "transparent",
        TRUSTED: "transparent", ERROR: "transparent",
      },
    },

    pipeline: { idle: "#c5ccd5", active: ink2, completed: ink, failed: "#7a1f5c" },

    status: {
      running: { bg: "rgba(15,27,45,0.06)", border: "rgba(15,27,45,0.35)", dot: ink },
      stopped: { bg: "rgba(15,27,45,0.04)", border: "rgba(15,27,45,0.25)", dot: ink2 },
      idle:    { bg: "rgba(15,27,45,0.04)", border: "rgba(15,27,45,0.25)", dot: muted },
    },

    replay: {
      bg: "rgba(15,27,45,0.06)", border: "rgba(15,27,45,0.45)",
      text: ink, currentRow: "rgba(15,27,45,0.07)",
    },

    edge: "#a3adba", arrow: "#8794a5", nodeText: ink2,
    rowBorder: "#e3e8ee", scrubber: "#aab4c0",
  },

  spacing: { xs: "4px", sm: "8px", md: "12px", lg: "16px", xl: "24px" },

  typography: {
    fontMono:    "'Public Sans', system-ui, sans-serif",   // legacy key: the UI face
    fontData:    "'JetBrains Mono', ui-monospace, monospace",
    fontDisplay: "'Source Serif 4', Georgia, serif",
    size: { xxs: "11px", xs: "12px", sm: "12px", md: "13px", lg: "15px", xl: "22px", xxl: "30px" },
    weight: { normal: 400, medium: 500, semibold: 600, bold: 700 },
    letterSpacing: { tight: "0", normal: "0", wide: "0.02em", wider: "0.04em" },
  },

  radii: { sm: "2px", md: "3px", lg: "4px", full: "50%" },

  shadows: {
    panel: "0 1px 2px rgba(15,27,45,0.08), 0 8px 24px rgba(15,27,45,0.10)",
    glow:  "0 0 0",
  },

  shell: {
    background: paper, surface: sheet, border: rule, scrollTrack: paper,
    textPrimary: ink2, textBright: ink, textMuted: muted, textDim: muted,
    accentTeal: ink,
  },
};

export default plate;
