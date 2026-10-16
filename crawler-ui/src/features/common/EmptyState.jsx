import { getTheme } from "../../theme";
import { createComponentStyles } from "../../theme/components";

const S = createComponentStyles(getTheme());

/** One sentence for a list or panel with nothing in it yet. */
export default function EmptyState({ children }) {
  return <div style={S.emptyState}>{children}</div>;
}
