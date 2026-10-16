// /theme/components.js
// Reusable style builders. Each accepts a theme object and returns style objects.

export const createComponentStyles = (theme) => {
  const { colors, spacing, typography, radii } = theme;

  return {
    // ── Shared ─────────────────────────────────────────────────────────────
    fontMono: {
      fontFamily: typography.fontMono,
    },
    fontDisplay: {
      fontFamily: typography.fontDisplay,
    },

    // ── MetricsPanel ────────────────────────────────────────────────────────

    statusText: (status) => {
      const s = colors.status[statusKey(status)];
      return {
        fontSize:      typography.size.xs,
        letterSpacing: "0",
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

    // ── NodeDetail ──────────────────────────────────────────────────────────
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

    // ── EventTimeline ────────────────────────────────────────────────────────
    timelineList: {
      flex:      1,
      overflowY: "auto",
      padding:   `${spacing.xs} 0`,
    },
    timelineEntry: (isCurrent) => ({
      display:     "flex",
      alignItems:  "baseline",
      gap:         "8px",
      padding:     `${spacing.xs} 14px`,
      cursor:      "pointer",
      background:  isCurrent ? colors.replay.currentRow : "transparent",
      // Events after the replay point are told apart by the muted summary, not by fading the
      // row: opacity would drop the text under 4.5:1 (WCAG 1.4.3).
      borderLeft:  isCurrent
        ? `2px solid ${colors.replay.text}`
        : "2px solid transparent",
      transition:  "background 0.15s",
    }),
    timelineTs: {
      fontSize:   typography.size.xxs,
      fontFamily: typography.fontData,
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
      letterSpacing: "0",
    },

    // ── Generic panel / section primitives (V2) ────────────────────────────
    panel: {
      display:       "flex",
      flexDirection: "column",
      height:        "100%",
      overflow:      "hidden",
      background:    colors.background.primary,
    },
    panelScroll: {
      flex:      1,
      minHeight: 0,
      overflowY: "auto",
      padding:   spacing.lg,
    },
    panelHeader: {
      display:        "flex",
      alignItems:      "center",
      justifyContent: "space-between",
      padding:        `10px ${spacing.lg}`,
      borderBottom:   `1px solid ${colors.background.border}`,
      flexShrink:     0,
    },
    panelHeaderTitle: {
      fontFamily:    typography.fontDisplay,
      fontSize:      typography.size.lg,
      fontWeight:    typography.weight.semibold,
      color:         colors.text.primary,
    },
    panelHeaderSubtitle: {
      fontSize:   typography.size.xs,
      color:      colors.text.muted,
      marginTop:  "2px",
    },
    sectionCard: {
      background:    colors.background.panel,
      border:        `1px solid ${colors.background.border}`,
      borderRadius:  radii.lg,
      padding:       spacing.lg,
    },
    sectionCardTitle: {
      fontSize:      typography.size.xs,
      letterSpacing: "0",
      color:         colors.text.muted,
      fontFamily:    typography.fontMono,
      marginBottom:  spacing.md,
      textTransform: "none",
    },
    emptyState: {
      display:        "flex",
      flexDirection:  "column",
      alignItems:     "center",
      justifyContent: "center",
      gap:            spacing.sm,
      padding:        `${spacing.xl} ${spacing.lg}`,
      color:          colors.text.muted,
      fontSize:       typography.size.sm,
      textAlign:      "center",
    },
    tabRow: {
      display:      "flex",
      gap:          "2px",
      borderBottom: `1px solid ${colors.background.border}`,
      padding:      `0 ${spacing.lg}`,
      flexShrink:   0,
    },
    tabBtn: (active) => ({
      padding:       `8px 12px`,
      fontSize:      typography.size.xs,
      fontFamily:    typography.fontMono,
      letterSpacing: "0",
      color:         active ? colors.text.primary : colors.text.muted,
      background:    "transparent",
      border:        "none",
      borderBottom:  active ? `2px solid ${colors.accent.blue}` : "2px solid transparent",
      cursor:        "pointer",
      marginBottom:  "-1px",
    }),

    // ── Pipeline Monitor (V2) ───────────────────────────────────────────────
    stageRow: {
      display:       "flex",
      alignItems:    "stretch",
      gap:           spacing.sm,
      overflowX:     "auto",
      paddingBottom: spacing.xs,
    },
    stageBox: (phase) => {
      const c = colors.pipeline[phase] || colors.pipeline.idle;
      return {
        flex:         "1 0 130px",
        background:   colors.background.panel,
        border:       `1px solid ${c}`,
        borderRadius: radii.md,
        padding:      spacing.sm,
        minWidth:     "130px",
      };
    },
    stageBoxLabel: {
      fontSize:      typography.size.xxs,
      letterSpacing: "0",
      color:         colors.text.muted,
      textTransform: "none",
    },
    stageBoxArrow: {
      display:    "flex",
      alignItems: "center",
      color:      colors.text.muted,
      fontSize:   typography.size.md,
      padding:    `0 2px`,
    },

    // ── Node Inspector (V2, docked) ─────────────────────────────────────────
    inspectorDock: {
      width:         "380px",
      flexShrink:    0,
      borderLeft:    `1px solid ${colors.background.border}`,
      background:    colors.background.primary,
      display:       "flex",
      flexDirection: "column",
      height:        "100%",
    },
    inspectorHeader: {
      display:        "flex",
      alignItems:     "flex-start",
      justifyContent: "space-between",
      padding:        `${spacing.md} ${spacing.lg}`,
      borderBottom:   `1px solid ${colors.background.border}`,
    },
    inspectorUrl: {
      fontFamily:   typography.fontData,
      fontSize:     typography.size.xs,
      color:        colors.text.primary,
      wordBreak:    "break-all",
      lineHeight:   1.4,
    },
    breakdownRow: {
      display:       "flex",
      alignItems:    "center",
      gap:           spacing.sm,
      padding:       "3px 0",
    },
    breakdownLabel: {
      fontSize:  typography.size.xxs,
      color:     colors.text.muted,
      minWidth:  "128px",
      flexShrink: 0,
    },
    breakdownBarTrack: {
      flex:         1,
      height:       "6px",
      borderRadius: radii.sm,
      background:   colors.background.border,
      overflow:     "hidden",
    },
    breakdownBarFill: (width, color) => ({
      width,
      height:     "100%",
      background: color,
    }),
    breakdownValue: {
      fontSize:  typography.size.xxs,
      color:     colors.text.secondary,
      minWidth:  "34px",
      textAlign: "right",
      fontVariantNumeric: "tabular-nums",
    },
  };
};

// ── helpers ──────────────────────────────────────────────────────────────────
function statusKey(status) {
  if (status === "RUNNING") return "running";
  if (status === "STOPPED") return "stopped";
  return "idle";
}
