// /theme/themes/light.js

const light = {
  colors: {
    background: {
      primary: "#f0f2f8",
      panel:   "#f8f9fc",
      border:  "#dde1ee",
    },
    text: {
      primary:   "#1a2040",
      secondary: "#5a6080",
      muted:     "#9aa0b8",
    },
    accent: {
      blue:    "#3a5adf",
      blueDim: "#4a6adf",
      gold:    "#c09010",
      green:   "#20a040",
      red:     "#c03030",
      purple:  "#7a4adf",
    },
    state: {
      CREATED:  "#dde2f5",
      FETCHED:  "#ccf0e0",
      FILTERED: "#cceaf0",
      SCORED:   "#e5ddf5",
      EXPANDED: "#dff0cc",
      DROPPED:  "#f0dde2",
      TRUSTED:  "#f5ecd0",
      ERROR:    "#f5d0d0",

      label: {
        CREATED:  "#5060a0",
        FETCHED:  "#208060",
        FILTERED: "#207888",
        SCORED:   "#7050b0",
        EXPANDED: "#408020",
        DROPPED:  "#a05060",
        TRUSTED:  "#907020",
        ERROR:    "#a02020",
      },

      glow: {
        CREATED:  "rgba(80,96,160,0.25)",
        FETCHED:  "rgba(32,128,96,0.3)",
        FILTERED: "rgba(32,120,136,0.25)",
        SCORED:   "rgba(112,80,176,0.25)",
        EXPANDED: "rgba(64,128,32,0.35)",
        DROPPED:  "rgba(160,80,96,0.15)",
        TRUSTED:  "rgba(144,112,32,0.3)",
        ERROR:    "rgba(160,32,32,0.3)",
      },
    },
    pipeline: {
      idle:      "#ccd2f0",
      active:    "#2060b0",
      completed: "#20a040",
      failed:    "#c03030",
    },
    status: {
      running: {
        bg:     "rgba(32,160,64,0.12)",
        border: "rgba(32,160,64,0.3)",
        dot:    "#20a040",
      },
      stopped: {
        bg:     "rgba(192,48,48,0.1)",
        border: "rgba(192,48,48,0.3)",
        dot:    "#c03030",
      },
      idle: {
        bg:     "rgba(90,96,128,0.1)",
        border: "rgba(90,96,128,0.25)",
        dot:    "#7a80a0",
      },
    },
    replay: {
      bg:         "rgba(192,144,16,0.12)",
      border:     "rgba(192,144,16,0.35)",
      text:       "#c09010",
      currentRow: "rgba(192,144,16,0.07)",
    },
    arrow:       "#9aa0b8",
    edge:        "#ccd2e8",
    nodeText:    "#6070a0",
    rowBorder:   "#e8eaf5",
    scrubber:    "#dde1ee",
  },
  spacing: {
    xs:  "4px",
    sm:  "6px",
    md:  "12px",
    lg:  "16px",
    xl:  "20px",
  },
  typography: {
    fontMono:    "'JetBrains Mono', monospace",
    fontDisplay: "'Syne', sans-serif",
    size: {
      xxs: "8px",
      xs:  "9px",
      sm:  "10px",
      md:  "11px",
      lg:  "13px",
      xl:  "16px",
      xxl: "18px",
    },
    weight: {
      normal:   400,
      medium:   500,
      semibold: 600,
      bold:     700,
    },
    letterSpacing: {
      tight:  "0.04em",
      normal: "0.06em",
      wide:   "0.08em",
      wider:  "0.12em",
    },
  },
  radii: {
    sm:   "3px",
    md:   "4px",
    lg:   "8px",
    full: "50%",
  },
  shadows: {
    panel: "0 8px 32px rgba(0,0,0,0.12)",
    glow:  "0 0 4px",
  },

  // ── App shell (top bar, nav, sidebar chrome) ──────────────────
  shell: {
    background:  "#eef1f8",
    surface:     "#f8f9fc",
    border:      "#dde1ee",
    scrollTrack: "#e4e7f0",
    textPrimary: "#3a4060",
    textBright:  "#1a2040",
    textMuted:   "#9aa0b8",
    textDim:     "#c5c9d8",
    accentTeal:  "#20a040",
  },
};

export default light;
