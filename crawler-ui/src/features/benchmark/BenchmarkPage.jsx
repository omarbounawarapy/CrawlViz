/**
 * Benchmark: the experiment behind the crawler's cascade, in one place.
 * Overview (design, graph, hypotheses), Results (harvest@k), Runs (start and
 * inspect), Graph (the labelled frozen graph) and Audit (blind annotation).
 */
import { useState } from "react";
import { Page } from "../common/Page";
import { Tabs, TabPanel } from "../common/Form";
import OverviewTab from "./OverviewTab";
import ResultsTab from "./ResultsTab";
import RunsTab from "./RunsTab";
import GraphTab from "./GraphTab";
import AuditTab from "./AuditTab";

const TABS = [
  ["overview", "Overview"], ["results", "Results"], ["runs", "Runs"], ["graph", "Graph"], ["audit", "Audit"],
];

export default function BenchmarkPage() {
  const [tab, setTab] = useState("overview");
  return (
    <Page title="Benchmark" width={820}
      lead="Does the cascade find more relevant pages per fetch than the baselines, and at what token cost? Results, runs, the labelled graph and the human audit of the judge.">
      <Tabs id="bench" label="Benchmark sections" value={tab} onChange={setTab} options={TABS} />
      <div style={{ marginTop: 8 }}>
        <TabPanel tabsId="bench" value={tab}>
          {tab === "overview" && <OverviewTab />}
          {tab === "results" && <ResultsTab />}
          {tab === "runs" && <RunsTab />}
          {tab === "graph" && <GraphTab />}
          {tab === "audit" && <AuditTab />}
        </TabPanel>
      </div>
    </Page>
  );
}
