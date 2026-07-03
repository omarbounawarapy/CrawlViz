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
  // ── Fills (perceptual hierarchy) ─────────────────────────────
  CREATED:   "#12182f",   // very low importance
  QUEUED:    "#1a2245",
  FETCHING:  "#1a3f66",
  FETCHED:   "#1f6f52",   // mid importance
  FILTERED: "#244a3a",   // dim green-blue → "survived but downgraded"
  SCORED:   "#3a2f5a", 
  EXPANDING: "#8a6a20",
  EXPANDED:  "#3f8f2a",   // HIGH importance (focus)
  STORED:    "#1f4f6a",
  ERROR:     "#6a1f2a",

  // ── Stroke / labels ─────────────────────────────────────────
  label: {
        FILTERED: "#4affb0",
    SCORED:   "#b89cff",
    CREATED:   "#3a4880",
    QUEUED:    "#5a6aaf",
    FETCHING:  "#4aa3ff",
    FETCHED:   "#4affb0",
    EXPANDING: "#ffd060",
    EXPANDED:  "#9aff60",
    STORED:    "#4ad0ff",
    ERROR:     "#ff6060",
  },

  // ── Glow (strong, visible) ──────────────────────────────────
  glow: {
     FILTERED: "rgba(74,255,176,0.25)",
    SCORED:   "rgba(184,156,255,0.25)",
    CREATED:   "rgba(58,72,128,0.25)",
    QUEUED:    "rgba(90,106,175,0.3)",
    FETCHING:  "rgba(0, 179, 255, 0.5)",
    FETCHED:   "rgba(89, 255, 74, 0.6)",
    EXPANDING: "rgba(255, 252, 96, 0.6)",
    EXPANDED:  "rgba(154,255,96,0.9)",  // dominant glow
    STORED:    "rgba(74,208,255,0.5)",
    ERROR:     "rgba(255,96,96,0.6)",
  },
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

// ── Graph clarity ─────────────────────────────────────────────
edge:     "#3a4a70",   // ↑ visible edges
arrow:    "#4a5a80",
nodeText: "#aab3d1",

// ── UI elements ───────────────────────────────────────────────
rowBorder: "#1c2240",
scrubber:  "#1a2040",

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
panel: "0 8px 32px rgba(0,0,0,0.7)",
glow:  "0 0 6px", // slightly stronger base glow
},

// ── App shell (top bar, nav, sidebar chrome) ────────────────────
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
