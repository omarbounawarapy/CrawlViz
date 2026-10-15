import { Page } from "../common/Page";
import { Button } from "../common/Form";

/** An address that matches no section. Shown inside the shell so the nav stays usable. */
export default function NotFoundPage({ route, onNavigate }) {
  return (
    <Page title="This page does not exist" width={560}
      lead={`Nothing lives at #/${route}. The address may be mistyped or from an older version of the app.`}>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <Button variant="primary" onClick={() => onNavigate("graph")}>Go to the graph</Button>
        <Button onClick={() => onNavigate("run")}>Start a run</Button>
      </div>
    </Page>
  );
}
