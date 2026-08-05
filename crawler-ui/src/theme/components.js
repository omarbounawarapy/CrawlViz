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

    // ── App shell (V2) ──────────────────────────────────────────────────
    shellRoot: {
      display:    "flex",
      width:      "100vw",
      height:     "100vh",
      background: colors.shell.background,
      fontFamily: typography.fontMono,
      overflow:   "hidden",
    },
    activityBar: {
      display:        "flex",
      flexDirection:  "column",
      alignItems:     "center",
      width:          "52px",
      flexShrink:     0,
      background:     colors.shell.surface,
      borderRight:    `1px solid ${colors.shell.border}`,
      paddingTop:     spacing.md,
      paddingBottom:  spacing.md,
      justifyContent: "space-between",
    },
    activityBarGroup: {
      display:       "flex",
      flexDirection: "column",
      alignItems:    "center",
      gap:           "2px",
      width:         "100%",
    },
    activityBarBtn: (active) => ({
      width:         "38px",
      height:        "38px",
      margin:        "2px 7px",
      display:       "flex",
      alignItems:    "center",
      justifyContent: "center",
      borderRadius:  radii.md,
      background:    active ? "rgba(90,122,255,0.14)" : "transparent",
      border:        active ? `1px solid ${colors.accent.blueDim}` : "1px solid transparent",
      color:         active ? colors.accent.blue : colors.shell.textMuted,
      cursor:        "pointer",
      transition:    "background 0.15s, color 0.15s, border-color 0.15s",
      position:      "relative",
    }),
    activityBarBadge: {
      position:     "absolute",
      top:          "2px",
      right:        "2px",
      width:        "6px",
      height:       "6px",
      borderRadius: radii.full,
      background:   colors.accent.red,
    },
    contentColumn: {
      display:       "flex",
      flexDirection: "column",
      flex:          1,
      minWidth:      0,
      height:        "100%",
    },
    topBar: {
      display:        "flex",
      alignItems:     "center",
      justifyContent: "space-between",
      height:         "42px",
      flexShrink:     0,
      padding:        `0 ${spacing.lg}`,
      borderBottom:   `1px solid ${colors.shell.border}`,
      background:     colors.shell.surface,
    },
    topBarLeft: {
      display:    "flex",
      alignItems: "center",
      gap:        spacing.md,
      minWidth:   0,
    },
    topBarTitle: {
      fontFamily:    typography.fontDisplay,
      fontSize:      typography.size.md,
      fontWeight:    typography.weight.semibold,
      color:         colors.shell.textBright,
      letterSpacing: typography.letterSpacing.tight,
      whiteSpace:    "nowrap",
      overflow:      "hidden",
      textOverflow:  "ellipsis",
    },
    topBarSubtitle: {
      fontSize:   typography.size.xxs,
      color:      colors.shell.textMuted,
      whiteSpace: "nowrap",
      overflow:   "hidden",
      textOverflow: "ellipsis",
      maxWidth:   "40ch",
    },
    mainArea: {
      flex:     1,
      minHeight: 0,
      display:  "flex",
      overflow: "hidden",
    },
    connectionDot: (connected) => ({
      width:        "6px",
      height:       "6px",
      borderRadius: radii.full,
      background:   connected ? colors.accent.green : colors.accent.red,
      boxShadow:    connected ? "none" : `0 0 6px ${colors.accent.red}`,
      animation:    connected ? "none" : "pulse 1.4s ease-in-out infinite",
      flexShrink:   0,
    }),

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
      letterSpacing: typography.letterSpacing.wider,
      color:         colors.text.muted,
      fontFamily:    typography.fontMono,
      marginBottom:  spacing.md,
      textTransform: "uppercase",
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
      letterSpacing: typography.letterSpacing.wider,
      color:         colors.text.muted,
      textTransform: "uppercase",
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
      letterSpacing: typography.letterSpacing.wider,
      textTransform: "uppercase",
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
        muted:   { bg: "rgba(138,148,192,0.12)", fg: colors.text.muted },
        blue:    { bg: "rgba(90,122,255,0.14)",   fg: colors.accent.blue },
        green:   { bg: "rgba(64,255,128,0.12)",   fg: colors.accent.green },
        gold:    { bg: "rgba(224,184,64,0.14)",   fg: colors.accent.gold },
        red:     { bg: "rgba(255,80,80,0.12)",    fg: colors.accent.red },
        purple:  { bg: "rgba(154,106,255,0.14)",  fg: colors.accent.purple },
      };
      const c = map[tone] || map.muted;
      return {
        display:       "inline-flex",
        alignItems:    "center",
        padding:       "1px 7px",
        borderRadius:  radii.sm,
        fontSize:      typography.size.xxs,
        fontFamily:    typography.fontMono,
        letterSpacing: typography.letterSpacing.normal,
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
      letterSpacing: typography.letterSpacing.normal,
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
      letterSpacing: typography.letterSpacing.wide,
      color:         colors.text.muted,
      textTransform: "uppercase",
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
      width:         "340px",
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
