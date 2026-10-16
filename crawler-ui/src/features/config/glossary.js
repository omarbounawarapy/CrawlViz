// The glossary comes from the backend schema (`ui_glossary`). Pages that already
// fetched the schema prime it; otherwise the first Term that renders fetches it.
import { useEffect, useSyncExternalStore } from "react";
import { fetchConfigSchema } from "../../api/client";

let value = null;
let pending = null;
const listeners = new Set();

const notify = () => listeners.forEach((l) => l());

export function primeGlossary(glossary) {
  if (!glossary || typeof glossary !== "object") return;
  value = glossary;
  notify();
}

export function loadGlossary() {
  if (value) return Promise.resolve(value);
  if (!pending) {
    pending = fetchConfigSchema()
      .then((schema) => { primeGlossary(schema.ui_glossary ?? {}); return value; })
      .catch(() => { pending = null; return {}; });
  }
  return pending;
}

/** The glossary as { term: definition }; {} until it has loaded. */
export function useGlossary() {
  const glossary = useSyncExternalStore(
    (cb) => { listeners.add(cb); return () => listeners.delete(cb); },
    () => value,
  );
  useEffect(() => { if (!value) loadGlossary(); }, []);
  return glossary ?? {};
}

/** Test helper: forget what was primed. */
export function resetGlossaryForTests() {
  value = null;
  pending = null;
  notify();
}
