import { Fragment, useMemo, type ReactNode } from "react";

import { useGlossaryDefinitions, type GlossaryDefinitions } from "./glossaryContext";
import { Term } from "./Term";

export interface ExplainProps {
  /** Prose that may contain glossary words. */
  text: string;
}

/**
 * A letter in any script, a digit, an underscore or a hyphen. A match never touches one on
 * either side, so a glossary word is not found inside a longer word ("top" in "top-k").
 */
const WORD_CHARACTER = String.raw`[\p{L}\p{N}_-]`;

const escapeForPattern = (word: string) => word.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/**
 * One pattern that finds every glossary word as a whole word, in any case. The longest words
 * come first in the alternation, so "top-k" is tried before "top". Null when there is nothing
 * to find.
 */
function glossaryPattern(definitions: GlossaryDefinitions): RegExp | null {
  const words = Object.keys(definitions)
    .filter((word) => word.trim() !== "")
    .sort((a, b) => b.length - a.length);
  if (words.length === 0) return null;
  const alternatives = words.map(escapeForPattern).join("|");
  return new RegExp(`(?<!${WORD_CHARACTER})(${alternatives})(?!${WORD_CHARACTER})`, "giu");
}

/**
 * Prose with every glossary word (NAME-4) wrapped in a Term, so each explains itself where it
 * is read. Longer words win, so "top-k" is not read as "top"; a word inside a longer word is
 * left alone. Without a GlossaryProvider, or with an empty glossary, it is the text as given.
 */
export function Explain({ text }: ExplainProps): ReactNode {
  const definitions = useGlossaryDefinitions();
  const pattern = useMemo(() => glossaryPattern(definitions), [definitions]);
  if (!text) return null;
  if (!pattern) return text;
  // split() with one capture group puts the matched words at the odd positions.
  return text.split(pattern).map((part, index) =>
    index % 2 === 1 ? (
      <Term key={index} term={part}>
        {part}
      </Term>
    ) : (
      <Fragment key={index}>{part}</Fragment>
    ),
  );
}
