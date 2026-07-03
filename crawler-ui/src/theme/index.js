// /theme/index.js
// Simple theme selector — no providers, no context, no runtime complexity.
// Change ACTIVE_THEME to switch themes project-wide.

import dark  from "./themes/dark";
import light from "./themes/light";

const themes = { dark, light };

const ACTIVE_THEME = "dark"; // "dark" | "light"

export function getTheme(themeName = ACTIVE_THEME) {
  return themes[themeName] ?? themes.dark;
}
