// V1 hard-dropped any message whose `type` wasn't in a hand-maintained
// allowlist -- meaning a new backend message type was invisible on the
// frontend, with no warning, until someone remembered to update three
// separate files in lockstep (see docs/V2_ARCHITECTURE.md §A.1.7). This
// only validates *shape* now (an object with a string `type`); the
// reducer's own `default` case is what decides whether a given type does
// anything, exactly as it already did for types this function let through
// in V1 -- nothing downstream gets less safe, unrecognized types just stop
// vanishing silently before they reach it.
export function normalizeEvent(raw) {
  try {
    const msg = typeof raw === "string" ? JSON.parse(raw) : raw;
    if (!msg || typeof msg !== "object") return null;
    if (typeof msg.type !== "string" || msg.type.length === 0) return null;
    return { ...msg, _receivedAt: Date.now() };
  } catch {
    return null;
  }
}