import { createContext, useContext } from "react";

/** Glossary definitions by lower-case term ("seed page", "backoff"), as the backend serves them. */
export type GlossaryDefinitions = Readonly<Record<string, string>>;

const NO_DEFINITIONS: GlossaryDefinitions = {};

/** Filled by GlossaryProvider; a Term or Explain outside one sees no definitions. */
export const GlossaryContext = createContext<GlossaryDefinitions>(NO_DEFINITIONS);

/** The glossary the nearest GlossaryProvider hands down; empty when there is none. */
export function useGlossaryDefinitions(): GlossaryDefinitions {
  return useContext(GlossaryContext);
}
