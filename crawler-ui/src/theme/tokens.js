// /theme/tokens.js
// Base token shape — all themes must implement these keys.

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
      CREATED:   null,
      QUEUED:    null,
      FETCHING:  null,
      FETCHED:   null,
      EXPANDING: null,
      EXPANDED:  null,
      STORED:    null,
      ERROR:     null,
      // node state label / stroke colors
      label: {
        CREATED:   null,
        QUEUED:    null,
        FETCHING:  null,
        FETCHED:   null,
        EXPANDING: null,
        EXPANDED:  null,
        STORED:    null,
        ERROR:     null,
      },
      // node glow colors
      glow: {
        CREATED:   null,
        QUEUED:    null,
        FETCHING:  null,
        FETCHED:   null,
        EXPANDING: null,
        EXPANDED:  null,
        STORED:    null,
        ERROR:     null,
      },
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
