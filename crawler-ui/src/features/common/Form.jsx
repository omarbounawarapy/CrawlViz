import { useId, isValidElement, cloneElement } from "react";
import { getTheme } from "../../theme";

const theme = getTheme();
const { text, background, accent } = theme.colors;

// Shared form atoms for the plate pages. Same tokens as Page.jsx; every
// control keeps the global focus ring (never set `outline: none` here).

const control = {
  width: "100%", height: 34, padding: "0 10px", fontSize: 14,
  background: background.panel, color: text.primary,
  border: `1px solid ${background.border}`, borderRadius: theme.radii.sm,
};
const invalidBorder = { border: `1px solid ${accent.red}` };

/** A labelled field. Pass `error` to show the plum message under the control. */
export function Field({ label, hint, error, id, children }) {
  const auto = useId();
  const fieldId = id || auto;
  return (
    <div style={{ marginBottom: 14, minWidth: 0 }}>
      <label htmlFor={fieldId} style={{ display: "block", fontSize: 13, fontWeight: 600, color: text.primary, marginBottom: 4 }}>
        {label}
      </label>
      {(() => {
        const a = { id: fieldId, "aria-invalid": error ? true : undefined, "aria-describedby": error ? `${fieldId}-err` : undefined };
        if (typeof children === "function") return children(a);
        return isValidElement(children) ? cloneElement(children, a) : children;
      })()}
      {hint && !error && <div style={{ fontSize: 13, color: text.muted, marginTop: 4 }}>{hint}</div>}
      {error && <div id={`${fieldId}-err`} style={{ fontSize: 13, color: accent.red, marginTop: 4 }}>{error}</div>}
    </div>
  );
}

export function TextInput({ invalid, style, ...rest }) {
  return <input {...rest} style={{ ...control, ...(invalid ? invalidBorder : null), ...style }} />;
}

export function Select({ invalid, style, children, ...rest }) {
  return <select {...rest} style={{ ...control, cursor: "pointer", ...(invalid ? invalidBorder : null), ...style }}>{children}</select>;
}

/** Two-up grid that collapses to one column on narrow screens. */
export function Grid({ children }) {
  return <div className="form-grid">{children}</div>;
}

const BTN = {
  height: 30, padding: "0 12px", fontSize: 13, fontWeight: 600, borderRadius: theme.radii.md,
  whiteSpace: "nowrap",
};

/** variant: outline (default) | primary | danger | quiet */
export function Button({ variant = "outline", armed, style, ...rest }) {
  const v = {
    outline: { background: "transparent", color: text.primary, border: `1px solid ${text.primary}` },
    primary: { background: text.primary, color: background.panel, border: `1px solid ${text.primary}` },
    // Plum is for the armed, about-to-destroy state only (same as Stop crawl).
    danger:  { background: armed ? accent.red : "transparent", color: armed ? "#fff" : text.primary, border: `1px solid ${armed ? accent.red : text.primary}` },
    quiet:   { background: "transparent", color: text.secondary, border: "1px solid transparent", textDecoration: "underline", padding: "0 4px" },
  }[variant];
  const off = rest.disabled ? { color: text.muted, border: `1px solid ${background.border}`, background: "transparent", cursor: "not-allowed", textDecoration: "none" } : null;
  return <button type="button" {...rest} style={{ ...BTN, ...v, ...off, ...style }} />;
}

/** Underline tabs: one idiom for view switches (Form / JSON, Profile / Manual). */
export function Tabs({ id, label, value, options, onChange }) {
  return (
    <div
      role="tablist" aria-label={label} style={{ display: "flex", gap: 4 }}
      onKeyDown={(e) => {
        const i = options.findIndex(([optId]) => optId === value);
        const step = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
        if (!step) return;
        e.preventDefault();
        const next = options[(i + step + options.length) % options.length][0];
        onChange(next);
        document.getElementById(`${id}-tab-${next}`)?.focus();
      }}
    >
      {options.map(([optId, name]) => (
        <button
          key={optId} type="button" role="tab" aria-selected={value === optId} tabIndex={value === optId ? 0 : -1}
          id={`${id}-tab-${optId}`} aria-controls={value === optId ? `${id}-panel-${optId}` : undefined}
          onClick={() => onChange(optId)}
          style={{
            height: 34, padding: "0 10px", background: "transparent", borderTop: "none", borderLeft: "none", borderRight: "none",
            borderBottom: `2px solid ${value === optId ? text.primary : "transparent"}`,
            color: value === optId ? text.primary : text.secondary,
            fontSize: 14, fontWeight: value === optId ? 600 : 500,
          }}
        >
          {name}
        </button>
      ))}
    </div>
  );
}

/** Toggle chip (2px radius, per DESIGN.md). Pressed = filled ink. */
export function Chip({ pressed, onClick, children }) {
  return (
    <button
      type="button" aria-pressed={pressed} onClick={onClick}
      style={{
        height: 28, padding: "0 10px", fontSize: 13, fontWeight: 500, borderRadius: theme.radii.sm,
        background: pressed ? text.primary : "transparent",
        color: pressed ? background.panel : text.secondary,
        border: `1px solid ${pressed ? text.primary : background.border}`,
      }}
    >
      {children}
    </button>
  );
}

/** A repeated group (a seed, a domain, a field): ruled above, no card. */
export function Group({ title, onRemove, removeLabel = "Remove", children }) {
  return (
    <div style={{ borderTop: `1px solid ${theme.colors.rowBorder}`, paddingTop: 12, marginTop: 4 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10, minHeight: 30 }}>
        <span style={{ fontSize: 14, fontWeight: 600, color: text.primary }}>{title}</span>
        {onRemove && <Button variant="quiet" onClick={onRemove}>{removeLabel}</Button>}
      </div>
      {children}
    </div>
  );
}

/** Inline status: a mark + word. Shape carries state, not hue alone. */
export function Status({ ok, children }) {
  return (
    <span role="status" style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 13, fontWeight: 500, color: ok ? text.primary : accent.red }}>
      <svg width="9" height="9" viewBox="0 0 9 9" aria-hidden="true">
        {ok ? <rect x="0.5" y="0.5" width="8" height="8" fill="currentColor" /> : <path d="M4.5 0.5 8.5 8.5H0.5Z" fill="currentColor" />}
      </svg>
      {children}
    </span>
  );
}

/** The panel a Tabs value controls. `tabsId` must match the Tabs `id`. */
export function TabPanel({ tabsId, value, children }) {
  return (
    <div role="tabpanel" id={`${tabsId}-panel-${value}`} aria-labelledby={`${tabsId}-tab-${value}`}>
      {children}
    </div>
  );
}
