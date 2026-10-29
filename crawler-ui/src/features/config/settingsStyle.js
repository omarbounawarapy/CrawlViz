import { getTheme } from "../../theme";

const theme = getTheme();

export const slug = (t) => `cfg-${t.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;

export const badgeStyle = {
  display: "inline-block",
  fontSize: 11,
  fontWeight: 600,
  letterSpacing: 0.3,
  textTransform: "uppercase",
  padding: "1px 6px",
  borderRadius: theme.radii.sm,
  border: `1px solid ${theme.colors.background.border}`,
  color: theme.colors.text.muted,
  marginLeft: 8,
  verticalAlign: "middle",
};
