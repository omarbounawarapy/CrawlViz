import { getTheme } from "../../theme";

const theme = getTheme();

// Shared page frame for the non-graph sections: a serif title, one plain
// sentence of lead, then a left-aligned reading column. No cards.
export function Page({ title, lead, width = 760, aside, children }) {
  return (
    <div style={{ height: "100%", overflowY: "auto", background: theme.colors.background.primary }}>
      {/* The aside column is always reserved, so every page's title starts at the same x. */}
      <div className="page-inner" style={{
        display: "grid", gridTemplateColumns: `200px minmax(0, ${width}px)`, columnGap: 56,
        padding: "40px 40px 64px", width: "fit-content", maxWidth: "100%", margin: "0 auto",
      }}>
        <div className="page-aside">{aside}</div>
        <div style={{ minWidth: 0 }}>
          <h1 style={{
            fontFamily: theme.typography.fontDisplay, fontWeight: 600, fontSize: 22, lineHeight: 1.2,
            color: theme.colors.text.primary, textWrap: "balance", marginBottom: lead ? 10 : 28,
          }}>
            {title}
          </h1>
          {lead && (
            <p style={{ fontSize: 15, lineHeight: 1.55, color: theme.colors.text.secondary, maxWidth: "62ch", marginBottom: 32 }}>
              {lead}
            </p>
          )}
          {children}
        </div>
      </div>
    </div>
  );
}

export function SectionTitle({ id, children }) {
  return (
    <h2 id={id} style={{
      fontFamily: theme.typography.fontDisplay, fontWeight: 600, fontSize: 17, lineHeight: 1.3,
      color: theme.colors.text.primary, margin: "32px 0 8px", scrollMarginTop: 24,
    }}>
      {children}
    </h2>
  );
}

// One ruled row: label (+ optional note) on the left, figure on the right.
export function Row({ label, note, children }) {
  return (
    <div style={{
      display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 24,
      padding: "11px 0", borderBottom: `1px solid ${theme.colors.rowBorder}`,
    }}>
      <div style={{ minWidth: 0 }}>
        <div style={{ fontSize: 14, color: theme.colors.text.primary }}>{label}</div>
        {note && <div style={{ fontSize: 13, color: theme.colors.text.muted, marginTop: 2, maxWidth: "60ch" }}>{note}</div>}
      </div>
      <div className="num" style={{ fontSize: 14, fontWeight: 600, color: theme.colors.text.primary, textAlign: "right", flexShrink: 0 }}>
        {children}
      </div>
    </div>
  );
}
