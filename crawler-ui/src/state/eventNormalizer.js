import { KNOWN_TYPES } from "./constants";

export function normalizeEvent(raw) {
  try {
    const msg = typeof raw === "string" ? JSON.parse(raw) : raw;
    if (!msg || typeof msg !== "object") return null;
    if (!KNOWN_TYPES.has(msg.type)) return null;
    return { ...msg, _receivedAt: Date.now() };
  } catch {
    return null;
  }
}