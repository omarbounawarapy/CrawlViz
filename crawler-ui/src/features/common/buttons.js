import { getTheme } from "../../theme";

const theme = getTheme();

export const buttonPrimary = (disabled) => ({
  height: 38, padding: "0 20px", borderRadius: theme.radii.md, fontSize: 14, fontWeight: 600,
  background: disabled ? theme.colors.background.border : theme.colors.text.primary,
  color: disabled ? theme.colors.text.muted : theme.colors.background.panel,
  border: "none", cursor: disabled ? "not-allowed" : "pointer",
});

export const buttonOutline = (disabled) => ({
  height: 38, padding: "0 20px", borderRadius: theme.radii.md, fontSize: 14, fontWeight: 600,
  background: "transparent",
  color: disabled ? theme.colors.text.muted : theme.colors.text.primary,
  border: `1px solid ${disabled ? theme.colors.background.border : theme.colors.text.primary}`,
  cursor: disabled ? "not-allowed" : "pointer",
});
