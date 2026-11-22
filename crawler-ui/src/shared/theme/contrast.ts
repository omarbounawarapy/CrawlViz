/**
 * WCAG 2.2 contrast between two colours.
 *
 * One implementation serves the token build (`crawler-ui/scripts/build-tokens.mjs` imports
 * this file directly, through Node's type stripping, so it uses only erasable TypeScript and
 * imports nothing) and the UI, for colours that are only known at run time.
 */

/** Text, and large text or non-text marks (WCAG 1.4.3 and 1.4.11). */
export const MIN_CONTRAST_TEXT = 4.5;
export const MIN_CONTRAST_NON_TEXT = 3;

const HEX_COLOUR = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i;
const CHANNEL_MAX = 255;
// sRGB to linear light, from the WCAG definition of relative luminance.
const LINEAR_THRESHOLD = 0.04045;
const LINEAR_SLOPE = 12.92;
const GAMMA_OFFSET = 0.055;
const GAMMA_SCALE = 1.055;
const GAMMA = 2.4;
const LUMINANCE_WEIGHTS = [0.2126, 0.7152, 0.0722] as const;
// Flare term in the contrast ratio, so pure black does not divide by zero.
const FLARE = 0.05;

/** The red, green and blue channels of an opaque `#rgb` or `#rrggbb` colour, from 0 to 255. */
export function parseHexColour(colour: string): [number, number, number] {
  const match = HEX_COLOUR.exec(colour.trim());
  const digits = match?.[1];
  if (digits === undefined) {
    throw new Error(
      `Contrast needs an opaque #rgb or #rrggbb colour, got "${colour}". Check translucent colours against the colour they sit on.`,
    );
  }
  const full =
    digits.length === 3
      ? digits
          .split("")
          .map((digit) => digit + digit)
          .join("")
      : digits;
  return [
    Number.parseInt(full.slice(0, 2), 16),
    Number.parseInt(full.slice(2, 4), 16),
    Number.parseInt(full.slice(4, 6), 16),
  ];
}

function toLinear(channel: number): number {
  const value = channel / CHANNEL_MAX;
  return value <= LINEAR_THRESHOLD ? value / LINEAR_SLOPE : ((value + GAMMA_OFFSET) / GAMMA_SCALE) ** GAMMA;
}

/** Relative luminance from 0 (black) to 1 (white). */
export function relativeLuminance(colour: string): number {
  const [red, green, blue] = parseHexColour(colour);
  return (
    LUMINANCE_WEIGHTS[0] * toLinear(red) +
    LUMINANCE_WEIGHTS[1] * toLinear(green) +
    LUMINANCE_WEIGHTS[2] * toLinear(blue)
  );
}

/** The contrast ratio, from 1 (same colour) to 21 (black on white); the order does not matter. */
export function contrastRatio(foreground: string, background: string): number {
  const first = relativeLuminance(foreground);
  const second = relativeLuminance(background);
  const lighter = Math.max(first, second);
  const darker = Math.min(first, second);
  return (lighter + FLARE) / (darker + FLARE);
}

/** Whether a pair reaches a minimum ratio. */
export function meetsContrast(foreground: string, background: string, minimum: number): boolean {
  return contrastRatio(foreground, background) >= minimum;
}
