/**
 * Copy the shared components show, kept in one catalog so it can be translated. Feature
 * copy lives in each feature's own `messages.ts`; only words a shared component writes by
 * itself belong here.
 */
export const sharedUiMessages = {
  required: "required",
  numberExpected: "Enter a number, like 0.5.",
  wholeNumberExpected: "Enter a whole number, like 12.",
} as const;
