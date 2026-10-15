import { useEffect, useMemo, useRef, useState } from "react";
import { fetchAudit, putAuditLabel, fetchAuditScore } from "../../api/client";
import { getTheme } from "../../theme";
import { SectionTitle } from "../common/Page";
import { Button, Chip, Tabs, Status } from "../common/Form";
import Loading from "./Loading";
import {useLoad, num} from "./shared";

const { text, background } = getTheme().colors;

const RUBRIC = [
  ["2", "The ISI Ariana itself, or a page devoted to its programmes, departments or buildings."],
  ["1", "A degree-granting higher-education institution in Tunisia, the Tunisian system, its ministry, or a list of institutions. Not the target."],
  ["0", "Everything else. If the excerpt does not make Tunisia clear, 0."],
];

function Score({ annotator, refreshKey }) {
  const state = useLoad(() => fetchAuditScore(annotator), [annotator, refreshKey]);
  if (state.error) return <p style={{ fontSize: 13, color: text.muted }}>No score yet: {state.error}</p>;
  if (!state.data) return null;
  const s = state.data;
  return (
    <>
      <p style={{ fontSize: 13, color: text.secondary }}>
        {s.n} of {s.sampled} annotated · binary agreement {num(s.agreement_binary)} · kappa {num(s.kappa)}
        {" "}[{num(s.kappa_ci?.[0], 2)}, {num(s.kappa_ci?.[1], 2)}] · relevant: precision {num(s.relevant_precision, 2)}, recall {num(s.relevant_recall, 2)}
      </p>
      {s.human_vs_annotator1 && (
        <p style={{ fontSize: 13, color: text.secondary }}>
          Annotator 2 against annotator 1 on {s.human_vs_annotator1.n} items: agreement {num(s.human_vs_annotator1.agreement)},
          kappa {num(s.human_vs_annotator1.kappa)} (binary {num(s.human_vs_annotator1.kappa_binary)}).
        </p>
      )}
      <table style={{ fontSize: 13, borderCollapse: "collapse" }}>
        <thead><tr><th style={{ padding: "4px 10px", color: text.muted }}>judge \ human</th>
          {[0, 1, 2].map((c) => <th key={c} style={{ padding: "4px 10px", color: text.muted }}>{c}</th>)}</tr></thead>
        <tbody>{s.confusion.map((row, r) => (
          <tr key={r}><th style={{ padding: "4px 10px", color: text.muted }}>{r}</th>
            {row.map((v, c) => <td key={c} className="num" style={{
              padding: "4px 10px", textAlign: "right", fontWeight: r === c ? 700 : 400,
              borderTop: `1px solid ${background.border}`,
            }}>{v}</td>)}</tr>
        ))}</tbody>
      </table>
    </>
  );
}

export default function AuditTab() {
  const [annotator, setAnnotator] = useState("1");
  const state = useLoad(() => fetchAudit(annotator), [annotator]);
  return (
    <>
      <p style={{ fontSize: 14, color: text.secondary, maxWidth: "62ch" }}>
        Label each page without seeing the judge's answer. Keys 0, 1, 2 answer and move on; arrow keys move; Backspace clears.
        Answers are saved as you go, separately from the original audit_filled.tsv. Annotator 2 labels the first 50 items only (PROTOCOL.md section 8.4).
      </p>
      <Tabs id="annot" label="Annotator" value={annotator} onChange={setAnnotator}
        options={[["1", "Annotator 1"], ["2", "Annotator 2"]]} />
      <Loading state={state}>{(d) => <Annotator key={annotator} data={d} annotator={annotator} />}</Loading>
    </>
  );
}

function Annotator({ data, annotator }) {
  const [answers, setAnswers] = useState(() => Object.fromEntries(
    data.items.filter((i) => i.human_label != null).map((i) => [i.id, i.human_label])));
  const [cur, setCur] = useState(0);
  const [onlyOpen, setOnlyOpen] = useState(false);
  const [err, setErr] = useState(null);
  const [rev, setRev] = useState(0);
  const refs = useRef([]);
  const visible = useMemo(
    () => data.items.map((it, i) => ({ it, i })).filter(({ it }) => !onlyOpen || answers[it.id] === undefined),
    [data.items, answers, onlyOpen]);
  const done = Object.keys(answers).length;

  async function answer(id, value) {
    setErr(null);
    const prev = answers[id];
    setAnswers((a) => { const n = { ...a }; if (value === null) delete n[id]; else n[id] = value; return n; });
    try { await putAuditLabel(id, value, annotator); setRev((r) => r + 1); } catch (e) {
      setErr(e.message);
      setAnswers((a) => { const n = { ...a }; if (prev === undefined) delete n[id]; else n[id] = prev; return n; });
    }
  }

  function onKey(e) {
    if (e.target.tagName === "INPUT") return;
    const item = data.items[cur];
    if (["0", "1", "2"].includes(e.key)) {
      e.preventDefault();
      answer(item.id, Number(e.key));
      setCur((c) => Math.min(data.items.length - 1, c + 1));
    } else if (e.key === "Backspace") { e.preventDefault(); answer(item.id, null); }
    else if (e.key === "ArrowDown") { e.preventDefault(); setCur((c) => Math.min(data.items.length - 1, c + 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setCur((c) => Math.max(0, c - 1)); }
  }
  useEffect(() => { refs.current[cur]?.scrollIntoView?.({ block: "nearest" }); }, [cur]);

  return (
    <div onKeyDown={onKey} tabIndex={0} aria-label="Audit annotation list" style={{ outline: "none" }}>
      <SectionTitle>Rubric</SectionTitle>
      {RUBRIC.map(([k, v]) => <p key={k} style={{ fontSize: 13, margin: "2px 0" }}><b>{k}</b> {v}</p>)}
      <div style={{ display: "flex", gap: 10, alignItems: "center", margin: "16px 0 8px" }}>
        <span className="num" style={{ fontSize: 13 }}>{done} / {data.items.length}</span>
        <Chip pressed={onlyOpen} onClick={() => setOnlyOpen((o) => !o)}>Unanswered only</Chip>
        <Button variant="quiet" onClick={() => {
          const n = data.items.findIndex((i) => answers[i.id] === undefined);
          if (n >= 0) setCur(n);
        }}>Next unanswered</Button>
        {err && <Status ok={false}>{err}</Status>}
      </div>
      <div role="list">
        {visible.map(({ it, i }) => (
          <div key={it.id} role="listitem" ref={(el) => (refs.current[i] = el)} onClick={() => setCur(i)} style={{
            display: "grid", gridTemplateColumns: "2.5rem 1fr", gap: "2px 8px", padding: "10px 8px",
            borderBottom: `1px solid ${background.border}`,
            background: i === cur ? "rgba(15,27,45,0.07)" : answers[it.id] !== undefined ? "rgba(15,27,45,0.025)" : "transparent",
            borderLeft: `3px solid ${i === cur ? text.primary : "transparent"}`,
          }}>
            <span className="num" style={{ color: text.muted, fontSize: 13 }}>{it.id}</span>
            <div style={{ minWidth: 0 }}>
              <div style={{ fontWeight: 600, fontSize: 14 }}>{it.title}</div>
              <div style={{ fontSize: 13, color: text.secondary, marginTop: 2 }}>{it.excerpt.slice(0, 420)}</div>
              <div role="radiogroup" aria-label={`Label for ${it.title}`} style={{ display: "flex", gap: 6, marginTop: 8 }}>
                {[0, 1, 2].map((v) => (
                  <Chip key={v} pressed={answers[it.id] === v} onClick={() => answer(it.id, v)}>{v}</Chip>
                ))}
              </div>
            </div>
          </div>
        ))}
      </div>
      <SectionTitle>Judge against you</SectionTitle>
      <Score annotator={annotator} refreshKey={rev} />
    </div>
  );
}
