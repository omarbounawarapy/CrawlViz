import { NODE_STATES } from "../../state/constants";
import { getTheme } from "../../theme";
import { createComponentStyles } from "../../theme/components";

const theme  = getTheme();
const styles = createComponentStyles(theme);

export default function Legend() {
  return (
    <div style={styles.legendWrap}>
      {NODE_STATES.map(s => (
        <div key={s} style={styles.legendItem}>
          <div style={styles.legendDot(
            theme.colors.state[s],
            theme.colors.state.label[s],
            theme.colors.state.glow[s],
          )} />
          <span style={styles.legendLabel}>{s}</span>
        </div>
      ))}
    </div>
  );
}
