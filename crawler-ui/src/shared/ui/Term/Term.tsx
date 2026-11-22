import { useEffect, useId, useRef, useState, type ReactNode } from "react";

import { GlossaryContext, useGlossaryDefinitions, type GlossaryDefinitions } from "./glossaryContext";
import styles from "./Term.module.css";

export interface GlossaryProviderProps {
  definitions: GlossaryDefinitions;
  children: ReactNode;
}

/**
 * Hands the glossary to every Term below it. The container that loads the glossary renders
 * this; Term itself never fetches (ARCH-4).
 */
export function GlossaryProvider({ definitions, children }: GlossaryProviderProps) {
  return <GlossaryContext.Provider value={definitions}>{children}</GlossaryContext.Provider>;
}

export interface TermProps {
  /** The glossary term, in any case: "Seed page" finds "seed page". */
  term: string;
  /** The words shown, when they differ from the term ("seed pages"). */
  children?: ReactNode;
}

/**
 * A glossary word (NAME-4) that explains itself on hover, focus or tap. It is a real button,
 * so the keyboard reaches it; Escape, a press elsewhere, leaving it or moving focus away
 * closes the explanation (WCAG 1.4.13). A word the glossary does not have is plain text.
 */
export function Term({ term, children }: TermProps) {
  const definitions = useGlossaryDefinitions();
  const definition = definitions[term.toLowerCase()];
  const shown = children ?? term;
  if (definition === undefined) return <>{shown}</>;
  return <Explained definition={definition}>{shown}</Explained>;
}

interface ExplainedProps {
  definition: string;
  children: ReactNode;
}

function Explained({ definition, children }: ExplainedProps) {
  const [open, setOpen] = useState(false);
  const explanationId = useId();
  const wrapper = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!open) return undefined;
    const closeOutside = (event: PointerEvent) => {
      if (event.target instanceof Node && wrapper.current?.contains(event.target)) return;
      setOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", closeOutside);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeOutside);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [open]);

  const show = () => {
    setOpen(true);
  };

  return (
    <span
      ref={wrapper}
      className={styles.term}
      onMouseEnter={show}
      onMouseLeave={() => {
        setOpen(false);
      }}
    >
      {/* The explanation stays in the DOM while hidden, so the word is described on every
          focus; a tooltip trigger carries no expanded state. A press only ever opens it: on a
          touch screen the tap's emulated hover and focus open it first, so a toggle would shut
          it again at once. */}
      <button
        type="button"
        className={styles.trigger}
        aria-describedby={explanationId}
        onClick={show}
        onFocus={show}
        onBlur={(event) => {
          const next = event.relatedTarget;
          if (!(next instanceof Node && wrapper.current?.contains(next))) setOpen(false);
        }}
      >
        {children}
      </button>
      <span role="tooltip" id={explanationId} hidden={!open} className={styles.explanation}>
        {definition}
      </span>
    </span>
  );
}
