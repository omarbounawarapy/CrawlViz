import { useEffect, useMemo, useRef, useState } from "react";
import { fetchAudit, putAuditLabel, fetchAuditScore } from "../../api/client";
import { getTheme } from "../../theme";
import { SectionTitle } from "../common/Page";
import { Button, Chip, Tabs, TabPanel, Status } from "../common/Form";
import { nextChoice } from "../common/choiceKeys";
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
        <caption className="sr-only">Judge label in rows, your label in columns</caption>
        <thead><tr><th scope="col" style={{ padding: "4px 10px", color: text.muted }}>judge \ human</th>
          {[0, 1, 2].map((c) => <th scope="col" key={c} style={{ padding: "4px 10px", color: text.muted }}>{c}</th>)}</tr></thead>
        <tbody>{s.confusion.map((row, r) => (
          <tr key={r}><th scope="row" style={{ padding: "4px 10px", color: text.muted }}>{r}</th>
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
        Label each page without seeing the judge's answer. Keys 0, 1, 2 answer and move to the next item; Tab moves between
        items; arrow keys change an answer; Backspace clears.
        Answers are saved as you go, separately from the original audit_filled.tsv. Annotator 2 labels the first 50 items only (PROTOCOL.md section 8.4).
      </p>
      <Tabs id="annot" label="Annotator" value={annotator} onChange={setAnnotator}
        options={[["1", "Annotator 1"], ["2", "Annotator 2"]]} />
      <TabPanel tabsId="annot" value={annotator}>
        <Loading state={state}>{(d) => <Annotator key={annotator} data={d} annotator={annotator} />}</Loading>
      </TabPanel>
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
  const [said, setSaid] = useState("");
  const refs = useRef([]);
  const visible = useMemo(
    () => data.items.map((it, i) => ({ it, i })).filter(({ it }) => !onlyOpen || answers[it.id] === undefined),
    [data.items, answers, onlyOpen]);
  const done = Object.keys(answers).length;

  async function answer(id, value) {
    setErr(null);
    const prev = answers[id];
    setAnswers((a) => { const n = { ...a }; if (value === null) delete n[id]; else n[id] = value; return n; });
    setSaid(value === null ? `Item ${id} cleared.` : `Item ${id} labelled ${value}.`);
    try { await putAuditLabel(id, value, annotator); setRev((r) => r + 1); } catch (e) {
      setErr(e.message);
      setAnswers((a) => { const n = { ...a }; if (prev === undefined) delete n[id]; else n[id] = prev; return n; });
    }
  }

  // Focus the answer buttons of item i: its checked radio, or its first.
  const focusItem = (i) => refs.current[i]?.querySelector('[role="radio"][tabindex="0"]')?.focus();

  // Single-key answers work only while focus is inside the list (WCAG 2.1.4), never in a text box.
  // Arrow keys belong to the radios (they change the answer); Tab moves between items.
  function onKey(e) {
    if (e.target.tagName === "INPUT" || e.ctrlKey || e.metaKey || e.altKey) return;
    const item = data.items[cur];
    if (["0", "1", "2"].includes(e.key)) {
      e.preventDefault();
      answer(item.id, Number(e.key));
      const next = Math.min(data.items.length - 1, cur + 1);
      setCur(next);
      requestAnimationFrame(() => focusItem(next));
    } else if (e.key === "Backspace") { e.preventDefault(); answer(item.id, null); }
  }
  useEffect(() => { refs.current[cur]?.scrollIntoView?.({ block: "nearest" }); }, [cur]);

  return (
    <div>
      <SectionTitle>Rubric</SectionTitle>
      <dl style={{ margin: 0 }}>
        {RUBRIC.map(([k, v]) => (
          <div key={k} style={{ display: "flex", gap: 6, fontSize: 13, margin: "2px 0" }}>
            <dt style={{ fontWeight: 700 }}>{k}</dt><dd style={{ margin: 0 }}>{v}</dd>
          </div>
        ))}
      </dl>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center", margin: "16px 0 8px" }}>
        <span className="num" style={{ fontSize: 13 }}>{done} of {data.items.length} answered</span>
        <Chip pressed={onlyOpen} onClick={() => setOnlyOpen((o) => !o)}>Unanswered only</Chip>
        <Button variant="quiet" onClick={() => {
          const n = data.items.findIndex((i) => answers[i.id] === undefined);
          if (n >= 0) { setCur(n); requestAnimationFrame(() => focusItem(n)); }
        }}>Next unanswered</Button>
        {err && <Status ok={false}>{err}</Status>}
      </div>
      <p role="status" className="sr-only">{said}</p>
      <p id="audit-keys" className="sr-only">Keys 0, 1 and 2 answer the item in focus and move to the next; Backspace clears.</p>
      <ol aria-label="Audit items" aria-describedby="audit-keys" onKeyDown={onKey}
          style={{ listStyle: "none", margin: 0, padding: 0 }}>
        {visible.map(({ it, i }) => {
          const value = answers[it.id];
          return (
            <li key={it.id} ref={(el) => (refs.current[i] = el)}
                aria-current={i === cur ? "true" : undefined}
                onClick={() => setCur(i)} onFocus={() => setCur(i)} style={{
              display: "grid", gridTemplateColumns: "2.5rem minmax(0, 1fr)", gap: "2px 8px", padding: "10px 8px",
              borderBottom: `1px solid ${background.border}`,
              background: i === cur ? "rgba(15,27,45,0.07)" : value !== undefined ? "rgba(15,27,45,0.025)" : "transparent",
              borderLeft: `3px solid ${i === cur ? text.primary : "transparent"}`,
            }}>
              <span className="num" style={{ color: text.muted, fontSize: 13 }}>{it.id}</span>
              <div style={{ minWidth: 0 }}>
                <h3 id={`audit-${it.id}`} style={{ fontWeight: 600, fontSize: 14, margin: 0 }}>{it.title}</h3>
                <div style={{ fontSize: 13, color: text.secondary, marginTop: 2 }}>{it.excerpt.slice(0, 420)}</div>
                <LabelChoice id={it.id} value={value} onPick={(v) => answer(it.id, v)} />
              </div>
            </li>
          );
        })}
      </ol>
      <SectionTitle>Judge against you</SectionTitle>
      <Score annotator={annotator} refreshKey={rev} />
    </div>
  );
}

// 0, 1 or 2 as a radio group (WAI pattern): every arrow key moves the answer, Tab leaves the group.
function LabelChoice({ id, value, onPick }) {
  const refs = useRef([]);
  const options = [0, 1, 2];
  const anyOn = options.includes(value);
  return (
    <div role="radiogroup" aria-labelledby={`audit-${id}`} style={{ display: "flex", gap: 6, marginTop: 8 }}>
      {options.map((v, i) => {
        const on = value === v;
        return (
          <button key={v} type="button" role="radio" aria-checked={on} aria-label={`Label ${v}`}
                  tabIndex={on || (!anyOn && i === 0) ? 0 : -1} ref={(el) => { refs.current[i] = el; }}
                  onClick={() => onPick(v)}
                  onKeyDown={(e) => {
                    const n = nextChoice(e, i, options.length);
                    if (n === null) return;
                    e.stopPropagation();
                    onPick(options[n]);
                    refs.current[n]?.focus();
                  }}
                  style={{
                    minWidth: 32, minHeight: 28, fontSize: 13, fontWeight: 600, borderRadius: 2,
                    background: on ? text.primary : "transparent", color: on ? background.panel : text.secondary,
                    border: `1px solid ${on ? text.primary : getTheme().colors.control}`,
                  }}>
            {v}
          </button>
        );
      })}
    </div>
  );
}
