/**
 * Design tokens for code (ARCH-2: the only import path into `shared/theme`).
 *
 * Styles read the CSS custom properties in `tokens.css`, which `global.css` loads once.
 * These values are for code that cannot use CSS variables: canvas drawing, SVG attributes
 * computed in d3, and contrast checks of colours known only at run time.
 */
export {
  THEME_NAMES,
  colorVar,
  colors,
  layer,
  motion,
  radius,
  size,
  space,
  stroke,
  typography,
  type ColorToken,
  type ThemeName,
} from "./tokens";
export {
  MIN_CONTRAST_NON_TEXT,
  MIN_CONTRAST_TEXT,
  contrastRatio,
  meetsContrast,
  parseHexColour,
  relativeLuminance,
} from "./contrast";
