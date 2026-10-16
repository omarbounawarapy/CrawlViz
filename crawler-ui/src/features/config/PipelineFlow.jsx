import { getTheme } from "../../theme";
import ExplainerFrame from "./explainers/ExplainerFrame";
import { STAGE_NAMES } from "./pipelineNames";

const theme = getTheme();
const { text, background } = theme.colors;

const W = 640, NODE_W = 112, NODE_H = 80, GAP = 18;
const ROWS = [0, 96, 192];
const col = (i) => i * (NODE_W + GAP);

// Where each stage sits. The main path runs left to right along the top row; the scheduling
// lane is the second row; retries feed back to the fetch stage; debugging is a side channel.
// Export is not a pipeline in the settings: its batch size lives in the Export section.
const STAGES = {
  requests: { name: STAGE_NAMES.requests, x: col(0), y: ROWS[0] },
  processing: { name: STAGE_NAMES.processing, x: col(1), y: ROWS[0] },
  filtering: { name: STAGE_NAMES.filtering, x: col(2), y: ROWS[0] },
  transformation: { name: STAGE_NAMES.transformation, x: col(3), y: ROWS[0] },
  exporting: { name: "Export", x: col(4), y: ROWS[0] },
  scoring: { name: STAGE_NAMES.scoring, x: col(0), y: ROWS[1] },
  priority: { name: STAGE_NAMES.priority, x: col(1), y: ROWS[1] },
  storage: { name: STAGE_NAMES.storage, x: col(2), y: ROWS[1] },
  retry: { name: STAGE_NAMES.retry, x: col(0), y: ROWS[2] },
  debugging: { name: STAGE_NAMES.debugging, x: col(1), y: ROWS[2] },
};

const MAIN = [["requests", "processing"], ["processing", "filtering"], ["filtering", "transformation"], ["transformation", "exporting"]];
const LANE = [["scoring", "priority"], ["priority", "storage"]];

const edge = (a, b) => {
  // Straight arrow between two nodes in the same row: from the right edge of a to the left edge of b.
  const A = STAGES[a], B = STAGES[b];
  return { x1: A.x + NODE_W, y1: A.y + NODE_H / 2, x2: B.x, y2: B.y + NODE_H / 2 };
};

/**
 * The pipeline stages as a picture: each box shows its workers and queue bound, which are edited
 * in the table below it. A bounded queue holds memory down and makes the stage before it wait.
 */
export default function PipelineFlow({ pipelines, batchSize, queues = null }) {
  if (!pipelines) return null;
  const describe = (key) => {
    const s = pipelines[key];
    if (!s) return [];
    const lines = [`${s.workers} worker${s.workers === 1 ? "" : "s"}`,
      s.max_queue_size ? `queue up to ${s.max_queue_size}` : "queue unbounded"];
    // While a crawl runs, the live count replaces nothing: it is one more line under the settings.
    const live = queues?.[key];
    if (live) lines.push(`${live.size} waiting now`);
    return lines;
  };
  const boxes = Object.keys(STAGES).map((key) => {
    const s = STAGES[key];
    const lines = key === "exporting" ? [`batch of ${batchSize ?? "?"} ${batchSize === 1 ? "row" : "rows"}`] : describe(key);
    return { key, ...s, lines };
  });
  const summary = `${boxes.length} stages: ${MAIN.length + 1} on the fetch path, ${LANE.length + 1} scoring and ordering the queue, plus retry and debug.`;
  const label = boxes.map((b) => `${b.name}: ${b.lines.join(", ")}`).join(". ");

  return (
    <ExplainerFrame title="How the pipeline moves a page" summary={null}>
      <svg viewBox={`0 0 ${W} ${ROWS[2] + NODE_H + 4}`} width="100%" role="img" aria-label={`${summary} ${label}.`}
           style={{ display: "block" }}>
        <defs>
          <marker id="pf-arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M0 0 L8 4 L0 8 z" fill={text.secondary} />
          </marker>
        </defs>
        {[...MAIN, ...LANE].map(([a, b]) => {
          const e = edge(a, b);
          return <line key={`${a}-${b}`} {...e} stroke={text.secondary} strokeWidth="1.5" markerEnd="url(#pf-arrow)" />;
        })}
        {boxes.map((b) => (
          <g key={b.key}>
            <rect x={b.x} y={b.y} width={NODE_W} height={NODE_H} rx="6" fill={background.primary}
                  stroke={b.key === "debugging" ? background.border : text.secondary} strokeDasharray={b.key === "debugging" ? "3 3" : undefined} />
            <text x={b.x + NODE_W / 2} y={b.y + 18} textAnchor="middle" fontSize="13" fontWeight="600" fill={text.primary}>{b.name}</text>
            {b.lines.map((line, i) => (
              <text key={line} x={b.x + NODE_W / 2} y={b.y + 36 + i * 14} textAnchor="middle" fontSize="12" fill={text.secondary}>{line}</text>
            ))}
          </g>
        ))}
      </svg>
      <p style={{ fontSize: 13, color: text.secondary, margin: "10px 0 0" }}>
        Top row: a page is fetched, its links extracted, filtered, transformed and exported. Middle row: scored, ordered in the
        queue of pages still to visit, and stored. Bottom row: a failed fetch or score goes to retry, which sends it back to
        fetch or scoring; debugging is a side channel that writes the trace.
      </p>
      <p style={{ fontSize: 13, color: text.secondary, margin: "6px 0 0" }}>
        Workers set the speed: more workers drain a stage faster and hold more work in memory at once. A queue bound caps the
        memory of a stage: once it is full, the stage before it waits, so the crawl slows instead of memory growing.
        Edit the workers and bounds in the table below. While a crawl runs, each box also shows the items waiting in its queue.
      </p>
    </ExplainerFrame>
  );
}
