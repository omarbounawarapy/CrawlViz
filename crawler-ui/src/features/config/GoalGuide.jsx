import { useEffect, useState } from "react";
import { getTheme } from "../../theme";
import { Button } from "../common/Form";
import { SectionTitle } from "../common/Page";
import { fetchPresets } from "../../api/client";
import { presetChanges } from "./presetModel";
import { Explain } from "./Term";

const theme = getTheme();
const { text, background } = theme.colors;

/**
 * "Start here": three starting points, each a preview of the settings it would change
 * against the draft. Apply only edits the draft; nothing is saved until Save changes.
 */
export default function GoalGuide({ draft, fields = [], onChange }) {
  const [goals, setGoals] = useState(null);
  const [open, setOpen] = useState(null);
  useEffect(() => {
    let cancelled = false;
    fetchPresets().then((p) => !cancelled && setGoals(p.goals ?? {})).catch(() => !cancelled && setGoals({}));
    return () => { cancelled = true; };
  }, []);

  if (goals === null) return <p style={{ fontSize: 14, color: text.muted }}>Loading the starting points…</p>;
  const names = Object.keys(goals);
  if (names.length === 0) return <p style={{ fontSize: 14, color: text.muted }}>No starting points are available.</p>;

  return (
    <div style={{ maxWidth: "66ch" }}>
      <SectionTitle id="cfg-start">Start here</SectionTitle>
      <p style={{ fontSize: 14, color: text.secondary, margin: "0 0 14px" }}>
        Pick what you want the crawl to do. Each card lists the settings it changes against your draft. Nothing is saved until you press Save changes.
      </p>
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        {names.map((name) => {
          const goal = goals[name];
          const changes = presetChanges(goal.values, draft, fields);
          const expanded = open === name;
          return (
            <section key={name} aria-labelledby={`goal-${name}`}
                     style={{ padding: "12px 14px", border: `1px solid ${background.border}`, borderRadius: theme.radii.lg }}>
              <h3 id={`goal-${name}`} style={{ fontSize: 15, fontWeight: 600, margin: "0 0 4px", color: text.primary }}>{goal.label}</h3>
              <p style={{ fontSize: 14, color: text.secondary, margin: "0 0 8px" }}><Explain text={goal.description} /></p>
              {changes.length === 0 ? (
                <p style={{ fontSize: 13, color: text.muted, margin: 0 }}>Your draft already matches this.</p>
              ) : (
                <>
                  <Button variant="quiet" aria-expanded={expanded} style={{ padding: 0 }}
                          onClick={() => setOpen(expanded ? null : name)}>
                    {expanded ? "Hide" : "Show"} the {changes.length} setting{changes.length === 1 ? "" : "s"} it changes
                  </Button>
                  {expanded && (
                    <ul style={{ margin: "8px 0", paddingLeft: 18, fontSize: 13, color: text.primary, display: "flex", flexDirection: "column", gap: 3 }}>
                      {changes.map((c) => (
                        <li key={c.path}>
                          {c.label}: <span style={{ color: text.muted }}>{c.fromText}</span> → {c.toText}
                        </li>
                      ))}
                    </ul>
                  )}
                  <Button variant="primary" onClick={() => changes.forEach((c) => onChange(c.path, c.to))}>Apply to draft</Button>
                </>
              )}
            </section>
          );
        })}
      </div>
    </div>
  );
}
