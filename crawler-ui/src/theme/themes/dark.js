// /theme/themes/dark.js

const dark = {
  colors: {
    background: {
      primary: "#050814",   // deeper → increases contrast
      panel:   "#0a0f1f",
      border:  "#141a30",
    },

    text: {
      primary:   "#e6ecff",  // ↑ stronger contrast
      secondary: "#8a94c0",
      muted:     "#4a5280",
    },

    accent: {
      blue:    "#5a7aff",
      blueDim: "#4a6adf",
      gold:    "#e0b840",
      green:   "#40ff80",
      red:     "#ff5050",
      purple:  "#9a6aff",
    },

    state: {
      // ── Fills — sequential ramp across the real lifecycle, low → high
      // importance (perceptual hierarchy) ──────────────────────────────
      CREATED:  "#12182f",   // just discovered, very low importance
      FETCHED:  "#1f6f52",   // page downloaded
      FILTERED: "#1f5a66",   // links deduped / accept-reject decided
      SCORED:   "#3a2f5a",   // cascade produced a priority
      EXPANDED: "#3f8f2a",   // children resolved — HIGH importance (focus)

      // cascade candidates that never became (or haven't yet become) a
      // full node -- see tokens.js docstring
      DROPPED:  "#2a1420",   // deliberately excluded — recedes, not alarming
      TRUSTED:  "#4a3a10",   // fast-tracked without an LLM call

      // indicator, not a lifecycle state — see tokens.js docstring
      ERROR:    "#6a1f2a",

      // ── Stroke / labels ─────────────────────────────────────────────
      label: {
        CREATED:  "#3a4880",
        FETCHED:  "#4affb0",
        FILTERED: "#4ad9e0",
        SCORED:   "#b89cff",
        EXPANDED: "#9aff60",
        DROPPED:  "#8a4a5a",
        TRUSTED:  "#e0b840",
        ERROR:    "#ff6060",
      },

      // ── Glow (strong, visible) ───────────────────────────────────────
      glow: {
        CREATED:  "rgba(58,72,128,0.25)",
        FETCHED:  "rgba(89,255,74,0.6)",
        FILTERED: "rgba(74,217,224,0.3)",
        SCORED:   "rgba(184,156,255,0.25)",
        EXPANDED: "rgba(154,255,96,0.9)",   // dominant glow
        DROPPED:  "rgba(138,74,90,0.18)",   // faint — recedes into the background
        TRUSTED:  "rgba(224,184,64,0.35)",
        ERROR:    "rgba(255,96,96,0.6)",
      },
    },

    // Pipeline Monitor stage indicators — one semantic ramp reused across
    // every stage rather than seven different hues.
    pipeline: {
      idle:      "#1a2245",
      active:    "#4aa3ff",
      completed: "#40ff80",
      failed:    "#ff5050",
    },

    status: {
      running: {
        bg:     "rgba(64,255,128,0.12)",
        border: "rgba(64,255,128,0.35)",
        dot:    "#40ff80",
      },
      stopped: {
        bg:     "rgba(255,80,80,0.12)",
        border: "rgba(255,80,80,0.35)",
        dot:    "#ff5050",
      },
      idle: {
        bg:     "rgba(120,120,160,0.12)",
        border: "rgba(120,120,160,0.3)",
        dot:    "#8080a0",
      },
    },

    replay: {
      bg:         "rgba(255,200,80,0.12)",
      border:     "rgba(255,200,80,0.4)",
      text:       "#ffd060",
      currentRow: "rgba(255,200,80,0.08)",
    },

    // ── Graph clarity ─────────────────────────────────────────────────
    edge:     "#3a4a70",   // ↑ visible edges
    arrow:    "#4a5a80",
    nodeText: "#aab3d1",

    // ── UI elements ────────────────────────────────────────────────────
    rowBorder: "#1c2240",
    scrubber:  "#1a2040",
  },

  spacing: {
    xs: "4px",
    sm: "6px",
    md: "12px",
    lg: "16px",
    xl: "20px",
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
    panel: "0 8px 32px rgba(0,0,0,0.7)",
    glow:  "0 0 6px",   // slightly stronger base glow
  },

  // ── App shell (top bar, nav, sidebar chrome) ───────────────────────
  shell: {
    background:  "#080c18",
    surface:     "#060a14",
    border:      "#111828",
    scrollTrack: "#0a0e1a",
    textPrimary: "#c0cce0",
    textBright:  "#e0eaff",
    textMuted:   "#3a4060",
    textDim:     "#2a3050",
    accentTeal:  "#40d9a0",
  },
};

export default dark;
