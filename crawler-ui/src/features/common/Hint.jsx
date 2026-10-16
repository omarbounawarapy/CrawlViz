import { useEffect, useId, useRef, useState } from "react";
import { getTheme } from "../../theme";

const theme = getTheme();

const trigger = {
  font: "inherit", color: "inherit", background: "none", border: "none", padding: 0, cursor: "help",
  textDecoration: "underline dotted", textUnderlineOffset: 3, textAlign: "inherit",
};

const bubble = {
  position: "absolute", left: 0, top: "100%", zIndex: 20, marginTop: 4, width: "max-content", maxWidth: 300,
  padding: "8px 10px", borderRadius: theme.radii.sm, background: theme.colors.background.panel,
  border: `1px solid ${theme.colors.background.border}`, boxShadow: "0 6px 18px rgba(15,27,45,0.14)",
  fontSize: 13, lineHeight: 1.45, color: theme.colors.text.primary, whiteSpace: "normal", textAlign: "left",
  fontWeight: 400, fontFamily: "inherit",
};

/**
 * Text that explains itself on hover, focus or tap. It is a real button, so the
 * keyboard reaches it, and Escape or a click elsewhere closes it.
 */
export function Hint({ text: explanation, children }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    const onPointer = (e) => { if (!ref.current?.contains(e.target)) setOpen(false); };
    const onKey = (e) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("pointerdown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <span ref={ref} style={{ position: "relative", display: "inline-block", maxWidth: "100%" }}
          onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}>
      <button
        type="button" aria-describedby={open ? id : undefined} aria-expanded={open}
        onClick={() => setOpen((v) => !v)} onFocus={() => setOpen(true)}
        onBlur={(e) => { if (!ref.current?.contains(e.relatedTarget)) setOpen(false); }}
        style={trigger}
      >
        {children}
      </button>
      {open && <span role="tooltip" id={id} style={bubble}>{explanation}</span>}
    </span>
  );
}
