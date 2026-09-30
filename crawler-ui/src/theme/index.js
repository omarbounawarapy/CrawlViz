// /theme/index.js
// One theme. Components read tokens through getTheme(); there are no
// providers or context.

import plate from "./themes/plate";

export function getTheme() {
  return plate;
}
