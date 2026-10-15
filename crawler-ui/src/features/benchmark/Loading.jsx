import { getTheme } from "../../theme";

const { text } = getTheme().colors;

function Loading({ state, children }) {
  if (state.error) return <p style={{ color: getTheme().colors.accent.red, fontSize: 14 }}>{state.error}</p>;
  if (state.loading && !state.data) return <p style={{ color: text.muted, fontSize: 14 }}>Loading…</p>;
  return children(state.data);
}

// Shows the error or a placeholder, otherwise calls children(data).
export default Loading;
