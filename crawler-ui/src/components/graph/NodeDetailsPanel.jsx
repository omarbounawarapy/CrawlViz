// NodeDetailsPanel.jsx
// Props: { node, onClose }
// Reads directly from the node object passed in (caller derives it from state.nodes.get(selectedNodeId))

const STATE_COLORS = {
  CREATED:  "#5a7aff",
  FETCHED:  "#40d9a0",
  EXPANDED: "#e0b840",
  SCORED:   "#c084fc",
  REJECTED: "#f87171",
  SKIPPED:  "#64748b",
};

function StateChip({ state }) {
  const color = STATE_COLORS[state] || "#3a4060";
  return (
    <span
      style={{
        display: "inline-block",
        padding: "2px 8px",
        borderRadius: 3,
        fontSize: 9,
        letterSpacing: "0.1em",
        fontWeight: 600,
        color,
        border: `1px solid ${color}40`,
        background: `${color}18`,
      }}
    >
      {state}
    </span>
  );
}

function Row({ label, value }) {
  return (
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "flex-start",
        padding: "7px 0",
        borderBottom: "1px solid #111828",
        gap: 8,
      }}
    >
      <span
        style={{
          fontSize: 9,
          color: "#3a4060",
          letterSpacing: "0.08em",
          textTransform: "uppercase",
          flexShrink: 0,
          paddingTop: 1,
        }}
      >
        {label}
      </span>
      <span
        style={{
          fontSize: 10,
          color: "#8090b0",
          wordBreak: "break-all",
          textAlign: "right",
          maxWidth: 200,
        }}
      >
        {value ?? "—"}
      </span>
    </div>
  );
}

export default function NodeDetailsPanel({ node, onClose }) {
  if (!node) return null;

  return (
    <div
      style={{
        position: "absolute",
        top: 12,
        right: 12,
        width: 300,
        background: "#060a14",
        border: "1px solid #1a2248",
        borderRadius: 6,
        fontFamily: "'JetBrains Mono', monospace",
        zIndex: 100,
        boxShadow: "0 4px 32px #000a",
      }}
    >
      {/* Header */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "10px 14px",
          borderBottom: "1px solid #111828",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 9, color: "#3a4060", letterSpacing: "0.1em", textTransform: "uppercase" }}>
            Node
          </span>
          <StateChip state={node.state} />
        </div>
        <button
          onClick={onClose}
          style={{
            background: "none",
            border: "none",
            color: "#3a4060",
            fontSize: 16,
            cursor: "pointer",
            lineHeight: 1,
            padding: "0 2px",
          }}
          aria-label="Close panel"
        >
          ×
        </button>
      </div>

      {/* URL block */}
      {node.url && (
        <div
          style={{
            padding: "8px 14px",
            borderBottom: "1px solid #111828",
          }}
        >
          <div style={{ fontSize: 9, color: "#3a4060", letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 4 }}>
            URL
          </div>
          <a
            href={node.url}
            target="_blank"
            rel="noopener noreferrer"
            style={{
              fontSize: 10,
              color: "#5a7aff",
              wordBreak: "break-all",
              textDecoration: "none",
              lineHeight: 1.5,
            }}
            onMouseEnter={e => e.target.style.textDecoration = "underline"}
            onMouseLeave={e => e.target.style.textDecoration = "none"}
          >
            {node.url}
          </a>
        </div>
      )}

      {/* Rows */}
      <div style={{ padding: "0 14px 4px" }}>
        <Row label="ID"       value={node.node_id} />
        <Row label="Parent"   value={node.parent_id || "—"} />
        <Row label="Links ✓"  value={node.links_accepted ?? 0} />
        <Row label="Links ✗"  value={node.links_rejected ?? 0} />
        <Row label="Scored"   value={node.scored_count ?? 0} />
      </div>
    </div>
  );
}
