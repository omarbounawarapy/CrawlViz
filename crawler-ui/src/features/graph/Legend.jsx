import { NODE_STATE_ORDER } from "../../state/nodeStates";
import { getTheme } from "../../theme";
import { createComponentStyles } from "../../theme/components";

const theme  = getTheme();
const styles = createComponentStyles(theme);

function Dot({ stateKey, label }) {
  return (
    <div style={styles.legendItem}>
      <div style={styles.legendDot(
        theme.colors.state[stateKey],
        theme.colors.state.label[stateKey],
        theme.colors.state.glow[stateKey],
      )} />
      <span style={styles.legendLabel}>{label || stateKey}</span>
    </div>
  );
}

export default function Legend() {
  return (
    <div style={styles.legendWrap}>
      {NODE_STATE_ORDER.map(s => <Dot key={s} stateKey={s} />)}
      <div style={{ width: 1, height: 12, background: theme.colors.background.border }} />
      <Dot stateKey="TRUSTED" label="trusted (no LLM)" />
      <Dot stateKey="DROPPED" label="dropped" />
    </div>
  );
}
