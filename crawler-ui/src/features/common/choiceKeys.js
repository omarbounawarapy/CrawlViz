// Arrow keys move through a row of radio-style choices (Tab leaves the group, as in the WAI pattern).
const STEP = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 };

/** Index an arrow key moves to from `index` in a list of `count` choices; null for any other key. */
export function nextChoice(event, index, count) {
  const step = STEP[event.key];
  if (!step) return null;
  event.preventDefault();
  return (index + step + count) % count;
}
