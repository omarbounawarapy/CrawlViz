import { useMemo } from "react";
import { useGlossary } from "./glossary";
import { Hint } from "../common/Hint";

/** A glossary word: explained when the glossary has it, plain text otherwise. */
export function Term({ term, children }) {
  const glossary = useGlossary();
  const definition = glossary[term.toLowerCase()];
  if (!definition) return children ?? term;
  return <Hint text={definition}>{children ?? term}</Hint>;
}

const escape = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/**
 * Prose with every glossary word wrapped in a Term. Longer words win, so
 * "top-k" is not read as "top"; a word inside a longer word is left alone.
 */
export function Explain({ text: prose }) {
  const glossary = useGlossary();
  const pattern = useMemo(() => {
    const keys = Object.keys(glossary).sort((a, b) => b.length - a.length);
    return keys.length ? new RegExp(`(?<![\\w-])(${keys.map(escape).join("|")})(?![\\w-])`, "gi") : null;
  }, [glossary]);
  if (!prose) return null;
  if (!pattern) return prose;
  const parts = prose.split(pattern);
  return parts.map((part, i) =>
    i % 2 === 1 ? (
      <Term key={i} term={part}>
        {part}
      </Term>
    ) : (
      part
    ),
  );
}
