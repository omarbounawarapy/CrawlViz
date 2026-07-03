// /theme/components.js
// Reusable style builders. Each accepts a theme object and returns style objects.

export const createComponentStyles = (theme) => {
  const { colors, spacing, typography, radii, shadows } = theme;

  return {
    // ── Shared ─────────────────────────────────────────────────────────────
    fontMono: {
      fontFamily: typography.fontMono,
    },
    fontDisplay: {
      fontFamily: typography.fontDisplay,
    },

    // ── MetricsPanel ────────────────────────────────────────────────────────
    metricsContainer: {
      padding:   `${spacing.md} ${spacing.lg}`,
      height:    "100%",
      overflowY: "auto",
    },
    metricRowWrap: {
      display:        "flex",
      justifyContent: "space-between",
      alignItems:     "baseline",
      padding:        `${spacing.sm} 0`,
      borderBottom:   `1px solid ${colors.rowBorder}`,
    },
    metricRowLabel: {
      fontSize:      typography.size.xs,
      color:         colors.text.muted,
      fontFamily:    typography.fontMono,
      letterSpacing: typography.letterSpacing.normal,
    },
    metricRowValue: (accent) => ({
      fontSize:   typography.size.xl,
      color:      accent || colors.accent.blue,
      fontFamily: typography.fontMono,
      fontWeight: typography.weight.semibold,
    }),

    sectionLabel: {
      fontSize:      typography.size.xxs,
      color:         colors.text.muted,
      letterSpacing: typography.letterSpacing.wider,
      fontFamily:    typography.fontMono,
    },

    statusBadgeWrap: (status) => {
      const s = colors.status[statusKey(status)];
      return {
        display:      "inline-flex",
        alignItems:   "center",
        gap:          spacing.sm,
        padding:      `${spacing.xs} 10px`,
        borderRadius: "20px",
        background:   s.bg,
        border:       `1px solid ${s.border}`,
      };
    },
    statusDot: (status, isRunning) => {
      const s = colors.status[statusKey(status)];
      return {
        width:        "6px",
        height:       "6px",
        borderRadius: radii.full,
        background:   s.dot,
        boxShadow:    isRunning ? `0 0 6px ${s.dot}` : "none",
        animation:    isRunning ? "pulse 1.4s ease-in-out infinite" : "none",
      };
    },
    statusText: (status) => {
      const s = colors.status[statusKey(status)];
      return {
        fontSize:      typography.size.xs,
        letterSpacing: typography.letterSpacing.wider,
        fontFamily:    typography.fontMono,
        color:         s.dot,
      };
    },
    stopReason: {
      fontSize:   typography.size.xxs,
      color:      colors.text.muted,
      marginTop:  spacing.sm,
      fontFamily: typography.fontMono,
    },

    stateBarTrack: {
      height:       "3px",
      background:   colors.background.border,
      borderRadius: radii.sm,
    },
    stateBarFill: (stateColor, width) => ({
      height:       "100%",
      borderRadius: radii.sm,
      width,
      background:   stateColor,
      transition:   "width 0.4s ease",
      boxShadow:    `${shadows.glow} ${stateColor}`,
    }),

    // ── NodeDetail ──────────────────────────────────────────────────────────
    nodeDetailPanel: {
      position:     "absolute",
      bottom:       spacing.lg,
      left:         spacing.lg,
      zIndex:       10,
      background:   colors.background.primary,
      border:       `1px solid ${colors.background.border}`,
      borderRadius: radii.lg,
      padding:      `${spacing.md} ${spacing.lg}`,
      minWidth:     "260px",
      boxShadow:    shadows.panel,
    },
    nodeDetailHeader: {
      display:        "flex",
      justifyContent: "space-between",
      marginBottom:   "10px",
    },
    nodeDetailTitle: (stateColor) => ({
      fontSize:      typography.size.xs,
      color:         stateColor,
      fontFamily:    typography.fontMono,
      letterSpacing: typography.letterSpacing.wide,
    }),
    nodeDetailCloseBtn: {
      background: "none",
      border:     "none",
      color:      colors.text.muted,
      cursor:     "pointer",
      fontSize:   "14px",
      padding:    0,
    },
    nodeDetailRow: {
      display:      "flex",
      gap:          spacing.md,
      padding:      `3px 0`,
      borderBottom: `1px solid ${colors.rowBorder}`,
    },
    nodeDetailKey: {
      fontSize:   typography.size.xxs,
      color:      colors.text.muted,
      fontFamily: typography.fontMono,
      minWidth:   "70px",
    },
    nodeDetailVal: {
      fontSize:      typography.size.xxs,
      color:         colors.text.secondary,
      fontFamily:    typography.fontMono,
      overflow:      "hidden",
      textOverflow:  "ellipsis",
      whiteSpace:    "nowrap",
      maxWidth:      "160px",
    },

    // ── Legend ──────────────────────────────────────────────────────────────
    legendWrap: {
      display:    "flex",
      gap:        spacing.lg,
      alignItems: "center",
      flexWrap:   "wrap",
    },
    legendItem: {
      display:    "flex",
      alignItems: "center",
      gap:        "5px",
    },
    legendDot: (stateColor, labelColor, glowColor) => ({
      width:        "8px",
      height:       "8px",
      borderRadius: radii.full,
      background:   stateColor,
      border:       `1px solid ${labelColor}`,
      boxShadow:    `${shadows.glow} ${glowColor}`,
    }),
    legendLabel: {
      fontSize:   typography.size.xxs,
      color:      colors.text.muted,
      fontFamily: typography.fontMono,
    },

    // ── EventTimeline ────────────────────────────────────────────────────────
    timelineWrap: {
      display:        "flex",
      flexDirection:  "column",
      height:         "100%",
    },
    timelineHeader: {
      display:        "flex",
      alignItems:     "center",
      justifyContent: "space-between",
      padding:        `10px 14px 6px`,
      borderBottom:   `1px solid ${colors.background.border}`,
    },
    timelineHeaderLabel: {
      fontSize:      typography.size.xs,
      letterSpacing: typography.letterSpacing.wider,
      color:         colors.text.secondary,
      fontFamily:    typography.fontMono,
    },
    exitReplayBtn: {
      background:   colors.replay.bg,
      border:       `1px solid ${colors.replay.border}`,
      borderRadius: radii.md,
      padding:      `2px 8px`,
      fontSize:     typography.size.xs,
      color:        colors.replay.text,
      cursor:       "pointer",
      fontFamily:   typography.fontMono,
    },
    timelineList: {
      flex:      1,
      overflowY: "auto",
      padding:   `${spacing.xs} 0`,
    },
    timelineEntry: (isCurrent, isPast, isReplaying) => ({
      display:     "flex",
      alignItems:  "baseline",
      gap:         "8px",
      padding:     `${spacing.xs} 14px`,
      cursor:      "pointer",
      background:  isCurrent ? colors.replay.currentRow : "transparent",
      opacity:     isReplaying && !isCurrent && !isPast ? 0.3 : 1,
      borderLeft:  isCurrent
        ? `2px solid ${colors.replay.text}`
        : "2px solid transparent",
      transition:  "background 0.15s",
    }),
    timelineTs: {
      fontSize:   typography.size.xxs,
      fontFamily: typography.fontMono,
      color:      colors.text.muted,
      minWidth:   "78px",
      flexShrink: 0,
    },
    timelineBadge: (badge) => ({
      fontSize:   typography.size.xxs,
      fontFamily: typography.fontMono,
      background: badge.bg,
      color:      badge.fg,
      padding:    "1px 5px",
      borderRadius: radii.sm,
      minWidth:   "44px",
      textAlign:  "center",
      flexShrink: 0,
    }),
    timelineSummary: (isPast, isReplaying) => ({
      fontSize:      typography.size.xs,
      color:         isPast || !isReplaying ? colors.text.secondary : colors.text.muted,
      fontFamily:    typography.fontMono,
      overflow:      "hidden",
      textOverflow:  "ellipsis",
      whiteSpace:    "nowrap",
    }),
    timelineScrubberWrap: {
      padding:     `8px 14px`,
      borderTop:   `1px solid ${colors.background.border}`,
    },
    timelineScrubberRange: {
      width:       "100%",
      accentColor: colors.replay.text,
      cursor:      "pointer",
    },
    timelineScrubberLabels: {
      display:        "flex",
      justifyContent: "space-between",
      marginTop:      "3px",
    },
    timelineScrubberLabel: {
      fontSize:   typography.size.xxs,
      color:      colors.text.muted,
      fontFamily: typography.fontMono,
    },

    // ── GraphView ───────────────────────────────────────────────────────────
    graphWrap: {
      width:    "100%",
      height:   "100%",
      position: "relative",
    },
    graphSvg: {
      width:      "100%",
      height:     "100%",
      background: "transparent",
    },
    replayBadge: {
      position:      "absolute",
      top:           spacing.md,
      right:         spacing.md,
      background:    colors.replay.bg,
      border:        `1px solid ${colors.replay.border}`,
      borderRadius:  radii.lg,
      padding:       `${spacing.xs} 10px`,
      fontSize:      typography.size.md,
      color:         colors.replay.text,
      fontFamily:    typography.fontMono,
      letterSpacing: typography.letterSpacing.normal,
    },
  };
};

// ── helpers ──────────────────────────────────────────────────────────────────
function statusKey(status) {
  if (status === "RUNNING") return "running";
  if (status === "STOPPED") return "stopped";
  return "idle";
}
