import { useEffect, useState } from "react";
import {
  fetchBenchmarkRuns, fetchBenchmarkRun, fetchBenchmarkEstimate, startBenchmarkJob, benchmarkJob, stopBenchmarkJob,
} from "../../api/client";
import { getTheme } from "../../theme";
import { SectionTitle } from "../common/Page";
import { Button, Chip, Field, Grid, Select, Status, TextInput } from "../common/Form";
import Loading from "./Loading";
import {LABEL, useLoad, num} from "./shared";

const { text, background } = getTheme().colors;

// Every invocation also re-runs the four baselines (they are deterministic per seed).
const ARMS = [
  ["cascade", "Cascade (live LLM)", { cascade: true }, "cascade"],
  ["replay", "Cascade replay (from cache, no LLM)", { cascade: true, replay_only: true }, null],
  ["llm_all", "llm_all (live LLM)", { cascade: true, llm_all: true }, "llm_all"],
  ["no_llm", "no_llm (replays the cascade's expansion)", { cascade: true, no_llm: true }, null],
  ["baselines", "Baselines only (bfs, random, anchor_lexical, oracle)", {}, null],
];

const DAILY_CAP = 200_000; // Groq's daily token cap

function JobPanel() {
  const [form, setForm] = useState({
    arm: "cascade", graph: "benchmark/data/isi.json", budget: 50, reps: 1,
    llm_cache: "benchmark/data/exp_cache.jsonl", runs_file: "benchmark/data/exp_runs.json",
  });
  const [est, setEst] = useState(null);
  const [job, setJob] = useState({ state: "idle", log: [] });
  const [error, setError] = useState(null);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  useEffect(() => {
    let live = true;
    const tick = () => benchmarkJob().then((j) => live && setJob(j), () => {});
    tick();
    const id = setInterval(tick, job.state === "running" ? 1500 : 6000);
    return () => { live = false; clearInterval(id); };
  }, [job.state]);

  useEffect(() => {
    let live = true;
    fetchBenchmarkEstimate(Number(form.budget)).then((e) => live && setEst(e), () => {});
    return () => { live = false; };
  }, [form.budget, job.state]);

  const running = job.state === "running";
  const armDef = ARMS.find((a) => a[0] === form.arm);
  const recorded = armDef[3] ? est?.arms?.[armDef[3]] : null;
  const estimate = recorded ? recorded.tokens_for_budget * Number(form.reps) : null;

  async function start() {
    setError(null);
    try {
      setJob(await startBenchmarkJob("run", {
        graph: form.graph, budget: Number(form.budget), reps: Number(form.reps),
        llm_cache: form.llm_cache, runs_file: form.runs_file, ...armDef[2],
      }));
    } catch (e) { setError(e.message); }
  }
  async function analyze() {
    setError(null);
    try { setJob(await startBenchmarkJob("analyze", {})); } catch (e) { setError(e.message); }
  }
  async function stop() {
    try { setJob(await stopBenchmarkJob()); } catch (e) { setError(e.message); }
  }

  return (
    <>
      <SectionTitle>Run an arm</SectionTitle>
      <Grid>
        <Field label="Arm">
          <Select value={form.arm} onChange={set("arm")} disabled={running}>
            {ARMS.map(([id, label]) => <option key={id} value={id}>{label}</option>)}
          </Select>
        </Field>
        <Field label="Graph file"><TextInput value={form.graph} onChange={set("graph")} disabled={running} /></Field>
        <Field label="Budget (fetched pages)"><Select value={form.budget} onChange={set("budget")} disabled={running}>
          {[10, 50, 100, 200].map((b) => <option key={b}>{b}</option>)}
        </Select></Field>
        <Field label="Repeats"><TextInput type="number" min="1" max="10" value={form.reps} onChange={set("reps")} disabled={running} /></Field>
        <Field label="LLM cache" hint="Replay and no_llm read it; keep it the same across the grid.">
          <TextInput value={form.llm_cache} onChange={set("llm_cache")} disabled={running} /></Field>
        <Field label="Recorded runs file"><TextInput value={form.runs_file} onChange={set("runs_file")} disabled={running} /></Field>
      </Grid>
      {armDef[3] && (
        <p style={{ fontSize: 13, color: estimate > DAILY_CAP * 0.5 ? getTheme().colors.accent.red : text.muted, margin: "0 0 12px" }}>
          {estimate == null
            ? `No recorded ${armDef[3]} run to estimate tokens from (Groq's daily cap is 200k).`
            : <>About {Math.round(estimate).toLocaleString()} tokens, from {recorded.runs} recorded {armDef[3]} run(s) at
              {" "}{Math.round(recorded.tokens_per_page)} per page: {Math.round((estimate / DAILY_CAP) * 100)}% of Groq's 200k daily cap.
              {estimate > DAILY_CAP * 0.5 && " Run in smaller pieces."}</>}
        </p>
      )}
      <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
        <Button variant="primary" disabled={running} onClick={start}>Start run</Button>
        <Button disabled={running} onClick={analyze}>Run analysis</Button>
        <Button variant="danger" armed disabled={!running} onClick={stop}>Stop</Button>
        {error && <Status ok={false}>{error}</Status>}
        {job.state !== "idle" && <Status ok={!["failed", "interrupted"].includes(job.state)}>{job.state} · {job.elapsed}s</Status>}
      </div>
      {job.state !== "idle" && (
        <>
          <p style={{ fontSize: 12, color: text.muted, margin: "10px 0 4px" }}>
            {job.command} · {job.new_results?.length ?? 0}{job.expected_results ? ` of ${job.expected_results}` : ""} result files
            written · {job.rate_limit_mentions} rate-limit lines
          </p>
          <pre aria-label="Job output" style={{
            fontFamily: getTheme().typography.fontData, fontSize: 12, maxHeight: 220, overflow: "auto",
            background: background.panel, border: `1px solid ${background.border}`, padding: 10, margin: 0, whiteSpace: "pre-wrap",
          }}>{job.log.join("\n")}</pre>
        </>
      )}
    </>
  );
}

function Strip({ run }) {
  // One cell per fetched page, in fetch order: the visit order is the result.
  const found = run.labels.reduce((a, l) => a + (l >= 1 ? 1 : 0), 0);
  return (
    <>
      <p style={{ fontSize: 13, color: text.secondary, margin: "8px 0" }}>
        {found} relevant of {run.labels.length} fetched
        {run.replay_misses ? ` · ${run.replay_misses} replay cache misses` : ""}
        {run.short ? " · stopped well short of the budget, do not average with full reps" : ""}
      </p>
      <div role="img" aria-label="Visit order, one cell per fetched page" style={{ display: "flex", flexWrap: "wrap", gap: 2 }}>
        {run.labels.map((l, i) => (
          <span key={i} title={`${i + 1}. ${decodeURIComponent(run.sequence[i] ?? "")} (label ${l})`} style={{
            width: 14, height: 14, background: LABEL[l]?.fill, border: l === 2 ? `2px solid ${text.primary}` : "none",
          }} />
        ))}
      </div>
      <div style={{ display: "flex", gap: 14, margin: "8px 0", fontSize: 12, color: text.muted }}>
        {[0, 1, 2].map((l) => (
          <span key={l}><span style={{ display: "inline-block", width: 10, height: 10, background: LABEL[l].fill, marginRight: 5 }} />{LABEL[l].name}</span>
        ))}
      </div>
      <details>
        <summary style={{ fontSize: 13, cursor: "pointer" }}>Manifest and settings</summary>
        <pre style={{ fontSize: 12, overflow: "auto" }}>{JSON.stringify({ manifest: run.manifest, settings: run.settings }, null, 2)}</pre>
      </details>
    </>
  );
}

export default function RunsTab() {
  const runs = useLoad(fetchBenchmarkRuns);
  const [sel, setSel] = useState(null);
  const [show, setShow] = useState({ replay: false, invalid: true });
  const detail = useLoad(() => (sel ? fetchBenchmarkRun(sel) : Promise.resolve(null)), [sel]);

  return (
    <>
      <JobPanel />
      <SectionTitle>Runs</SectionTitle>
      <div style={{ display: "flex", gap: 8, marginBottom: 10 }}>
        <Chip pressed={show.replay} onClick={() => setShow((s) => ({ ...s, replay: !s.replay }))}>Replays</Chip>
        <Chip pressed={show.invalid} onClick={() => setShow((s) => ({ ...s, invalid: !s.invalid }))}>Invalid</Chip>
        <Button variant="quiet" onClick={runs.reload}>Refresh</Button>
      </div>
      <Loading state={runs}>{(list) => (
        <div style={{ overflowX: "auto" }}>
        <table style={{ fontSize: 13, borderCollapse: "collapse", width: "100%" }}>
          <thead><tr>{["Policy", "Rep", "Budget", "Fetched", "Found", "@30", "Tokens", "Status"].map((h, i) => (
            <th key={h} style={{ textAlign: i < 2 ? "left" : "right", padding: "5px 8px", color: text.muted, fontWeight: 600 }}>{h}</th>
          ))}</tr></thead>
          <tbody>
            {list.filter((r) => (show.replay || !r.replay) && (show.invalid || r.valid)).map((r) => (
              <tr key={r.name} onClick={() => setSel(r.name)} style={{
                cursor: "pointer", borderTop: `1px solid ${background.border}`,
                background: sel === r.name ? "rgba(15,27,45,0.07)" : "transparent",
              }}>
                <td style={{ padding: "5px 8px" }}>
                  <button type="button" onClick={() => setSel(r.name)} style={{
                    background: "none", border: "none", padding: 0, font: "inherit", fontWeight: 600, color: text.primary, cursor: "pointer",
                  }}>{r.policy}{r.replay ? " (replay)" : ""}</button>
                </td>
                <td className="num" style={{ padding: "5px 8px" }}>{r.rep}</td>
                <td className="num" style={{ padding: "5px 8px", textAlign: "right" }}>{r.budget}</td>
                <td className="num" style={{ padding: "5px 8px", textAlign: "right" }}>{r.fetched}</td>
                <td className="num" style={{ padding: "5px 8px", textAlign: "right" }}>{r.found}</td>
                <td className="num" style={{ padding: "5px 8px", textAlign: "right" }}>{num(r.harvest30, 2)}</td>
                <td className="num" style={{ padding: "5px 8px", textAlign: "right" }}>{(r.input_tokens + r.output_tokens).toLocaleString()}</td>
                <td style={{ padding: "5px 8px", textAlign: "right" }}>
                  <Status ok={r.valid && !r.short}>{!r.valid ? "invalid" : r.short ? "short" : r.status}</Status>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      )}</Loading>
      {sel && (
        <>
          <SectionTitle>{sel}</SectionTitle>
          <Loading state={detail}>{(run) => (run ? <Strip run={run} /> : null)}</Loading>
        </>
      )}
    </>
  );
}
