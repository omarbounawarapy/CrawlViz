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
      letterSpacing: "0",
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
      letterSpacing: "0",
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

    stateBarTrack: {
      height:       "3px",
      background:   colors.background.border,
      borderRadius: radii.sm,
    },
    stateBarFill: (stateColor, width) => ({
      height:       "100%",
      borderRadius: radii.sm,
      width:        "100%",
      background:   stateColor,
      transform:    `scaleX(${parseFloat(width) / 100})`,
      transformOrigin: "left",
      transition:   "transform 0.4s cubic-bezier(0.22, 1, 0.36, 1)",
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
      letterSpacing: "0",
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
      letterSpacing: "0",
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
    statTileGrid: (minWidth = "150px") => ({
      display:             "grid",
      gridTemplateColumns: `repeat(auto-fit, minmax(${minWidth}, 1fr))`,
      gap:                 spacing.md,
    }),
    statTile: {
      background:   colors.background.panel,
      border:       `1px solid ${colors.background.border}`,
      borderRadius: radii.lg,
      padding:      spacing.md,
    },
    statTileLabel: {
      fontSize:      typography.size.xxs,
      letterSpacing: "0",
      color:         colors.text.muted,
      textTransform: "none",
    },
    statTileValue: (accent) => ({
      fontSize:   typography.size.xxl,
      fontWeight: typography.weight.semibold,
      color:      accent || colors.text.primary,
      marginTop:  "4px",
      fontVariantNumeric: "tabular-nums",
    }),
    statTileSub: {
      fontSize:  typography.size.xxs,
      color:     colors.text.muted,
      marginTop: "2px",
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
    dataTable: {
      width:           "100%",
      borderCollapse:  "collapse",
      fontSize:        typography.size.xs,
      fontFamily:      typography.fontMono,
      fontVariantNumeric: "tabular-nums",
    },
    dataTableTh: {
      textAlign:     "left",
      padding:       `6px ${spacing.sm}`,
      color:         colors.text.muted,
      fontSize:      typography.size.xxs,
      letterSpacing: "0",
      textTransform: "none",
      borderBottom:  `1px solid ${colors.background.border}`,
      whiteSpace:    "nowrap",
    },
    dataTableTd: {
      padding:      `6px ${spacing.sm}`,
      borderBottom: `1px solid ${colors.rowBorder}`,
      color:        colors.text.secondary,
      whiteSpace:   "nowrap",
      overflow:     "hidden",
      textOverflow: "ellipsis",
      maxWidth:     "320px",
    },
    pill: (tone = "muted") => {
      const map = {
        muted:   { bg: "rgba(15,27,45,0.05)", fg: colors.text.muted },
        blue:    { bg: "rgba(15,27,45,0.06)",   fg: colors.accent.blue },
        green:   { bg: "rgba(31,111,90,0.10)",   fg: colors.accent.green },
        gold:    { bg: "rgba(122,90,0,0.10)",   fg: colors.accent.gold },
        red:     { bg: "rgba(122,31,92,0.08)",    fg: colors.accent.red },
        purple:  { bg: "rgba(15,27,45,0.05)",  fg: colors.accent.purple },
      };
      const c = map[tone] || map.muted;
      return {
        display:       "inline-flex",
        alignItems:    "center",
        padding:       "1px 7px",
        borderRadius:  radii.sm,
        fontSize:      typography.size.xxs,
        fontFamily:    typography.fontMono,
        letterSpacing: "0",
        background:    c.bg,
        color:         c.fg,
        whiteSpace:    "nowrap",
      };
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
