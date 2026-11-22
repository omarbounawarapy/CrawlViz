/** The class names that are set, joined with spaces; a CSS Module lookup can be undefined. */
export function classNames(...names: (string | false | null | undefined)[]): string {
  return names.filter(Boolean).join(" ");
}
