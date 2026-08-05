// /theme/tokens.js
// Base token shape — all themes must implement these keys.
//
// V2: `colors.state` used to list CREATED / QUEUED / FETCHING / FETCHED /
// EXPANDING / EXPANDED / STORED / ERROR -- four of which (QUEUED, FETCHING,
// EXPANDING, STORED) never corresponded to anything the backend actually
// sends (the real lifecycle is CREATED → FETCHED → FILTERED → SCORED →
// EXPANDED; see state/nodeStates.js), while the fifth real state,
// FILTERED, was missing entirely. NodeDetailsPanel.jsx independently
// invented its own REJECTED/SKIPPED colors reaching for the same thing.
// See docs/V2_ARCHITECTURE.md §A.1.4 for the full account of this drift.
//
// This is now the one place the palette is defined for node-related
// concepts: the five real lifecycle states, plus DROPPED / TRUSTED for
// the two cascade candidate decisions (links that were evaluated but
// never became full nodes, or were fast-tracked without an LLM call --
// see docs/crawl_messages.ts CandidateDecision). ERROR remains as an
// *indicator* color (a node can be, say, FETCHED and still have an
// associated NODE_ERROR from a later stage) rather than a lifecycle state.

export const tokenShape = {
  colors: {
    background: {
      primary: null,  // root app background
      panel:   null,  // sidebar / panel surfaces
      border:  null,  // dividers and borders
    },
    text: {
      primary:   null,
      secondary: null,
      muted:     null,
    },
    accent: {
      blue:   null,
      blueDim: null,
      gold:   null,
      green:  null,
      red:    null,
      purple: null,
    },
    state: {
      // node state colors (fill)
      CREATED:  null,
      FETCHED:  null,
      FILTERED: null,
      SCORED:   null,
      EXPANDED: null,
      // cascade candidate pseudo-states (never full nodes -- see above)
      DROPPED:  null,
      TRUSTED:  null,
      // indicator, not a lifecycle state (see module docstring)
      ERROR:    null,
      // node state label / stroke colors
      label: {
        CREATED:  null,
        FETCHED:  null,
        FILTERED: null,
        SCORED:   null,
        EXPANDED: null,
        DROPPED:  null,
        TRUSTED:  null,
        ERROR:    null,
      },
      // node glow colors
      glow: {
        CREATED:  null,
        FETCHED:  null,
        FILTERED: null,
        SCORED:   null,
        EXPANDED: null,
        DROPPED:  null,
        TRUSTED:  null,
        ERROR:    null,
      },
    },
    // pipeline stage lifecycle indicators (Pipeline Monitor) -- reuses the
    // same semantic-status idea as `status` below rather than introducing
    // per-stage hues, consistent with "pick one accent, don't multiply
    // colors" (see docs/V2_ARCHITECTURE.md / redesign audit).
    pipeline: {
      idle:      null,
      active:    null,
      completed: null,
      failed:    null,
    },
    status: {
      running: { bg: null, border: null, dot: null },
      stopped: { bg: null, border: null, dot: null },
      idle:    { bg: null, border: null, dot: null },
    },
    replay: {
      bg:         null,
      border:     null,
      text:       null,
      currentRow: null,
    },
  },
  spacing: {
    xs: null,
    sm: null,
    md: null,
    lg: null,
    xl: null,
  },
  typography: {
    fontMono:    null,
    fontDisplay: null,
    size: {
      xxs: null,
      xs:  null,
      sm:  null,
      md:  null,
      lg:  null,
      xl:  null,
    },
    weight: {
      normal:   null,
      medium:   null,
      semibold: null,
      bold:     null,
    },
    letterSpacing: {
      tight:  null,
      normal: null,
      wide:   null,
      wider:  null,
    },
  },
  radii: {
    sm:   null,
    md:   null,
    lg:   null,
    full: null,
  },
  shadows: {
    panel:  null,
    glow:   null,
  },
  shell: {
    background:  null,
    surface:     null,
    border:      null,
    scrollTrack: null,
    textPrimary: null,
    textBright:  null,
    textMuted:   null,
    textDim:     null,
    accentTeal:  null,
  },
};
