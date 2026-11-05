import { GlossaryProvider } from "../../shared/ui";
import { useGlossary } from "./glossary";

/**
 * Loads the glossary from the backend schema (once, shared by every scope) and hands it to
 * every Term and Explain below. The app renders one around its pages; the config page renders
 * its own so it explains words when shown alone.
 */
export default function GlossaryScope({ children }) {
  const definitions = useGlossary();
  return <GlossaryProvider definitions={definitions}>{children}</GlossaryProvider>;
}
