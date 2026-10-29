import { Component } from "react";
import { getTheme } from "../../theme";

const { text, background } = getTheme().colors;
const { typography: type } = getTheme();

/**
 * Last line of defence: a render error shows this instead of a blank page.
 * It uses plain inline styles and no app components, so it cannot fail the
 * same way the thing it is catching did.
 */
export default class ErrorBoundary extends Component {
  state = { error: null };

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    console.error("Unhandled UI error:", error, info?.componentStack);
  }

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;
    const btn = {
      height: 34,
      padding: "0 14px",
      fontSize: 14,
      fontWeight: 600,
      borderRadius: 4,
      cursor: "pointer",
      border: `1px solid ${text.primary}`,
    };
    return (
      <div
        role="alert"
        style={{
          minHeight: "100vh",
          display: "grid",
          placeItems: "center",
          padding: 24,
          background: background.primary,
          color: text.primary,
          fontFamily: type.fontMono,
        }}
      >
        <div style={{ maxWidth: 520 }}>
          <h1 style={{ fontFamily: type.fontDisplay, fontSize: 22, fontWeight: 600, margin: "0 0 10px" }}>
            Something went wrong
          </h1>
          <p style={{ fontSize: 15, lineHeight: 1.55, color: text.secondary, margin: "0 0 16px" }}>
            The interface hit an error and stopped drawing. A crawl running in the backend is not affected.
          </p>
          <pre
            style={{
              fontFamily: type.fontData,
              fontSize: 12,
              whiteSpace: "pre-wrap",
              margin: "0 0 18px",
              padding: 10,
              background: background.panel,
              border: `1px solid ${background.border}`,
            }}
          >
            {String(error?.message ?? error)}
          </pre>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button
              type="button"
              style={{ ...btn, background: text.primary, color: background.panel }}
              onClick={() => window.location.reload()}
            >
              Reload
            </button>
            <button
              type="button"
              style={{ ...btn, background: "transparent", color: text.primary }}
              onClick={() => {
                window.location.hash = "#/graph";
                this.setState({ error: null });
              }}
            >
              Back to the graph
            </button>
          </div>
        </div>
      </div>
    );
  }
}
