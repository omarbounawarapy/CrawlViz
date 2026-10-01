import { useMemo } from "react";
import { buildPlate } from "./plate";
import Spider from "../loading/Spider";
import "../loading/loading.css";
import "./landing.css";

const REPO = "https://github.com/omarbounawarapy/crawlviz";
const STAGE = ["#0f1b2d", "#56657a", "#8794a5", "#b7c1cd"];
const STROKE = ["#0f1b2d", "#33435a", "#56657a", "#8794a5"];

function Plate({ seed, branches, compact = false, selective = true }) {
  const plate = useMemo(() => buildPlate({ seed, branches, w: compact ? 320 : 640, h: compact ? 260 : 520, reach: compact ? 62 : 130 }), [seed, branches, compact]);
  const byId = useMemo(() => new Map(plate.nodes.map((n) => [n.id, n])), [plate]);
  const hot = useMemo(
    () => plate.nodes.filter((n) => n.depth > 1 && n.score > 0.5 && n.x < plate.w - 230 && n.y > 90)
      .sort((a, b) => Math.hypot(b.x - plate.nodes[0].x, b.y - plate.nodes[0].y) - Math.hypot(a.x - plate.nodes[0].x, a.y - plate.nodes[0].y)),
    [plate],
  );
  const lead = hot[0];
  const note = useMemo(() => {
    if (!lead) return null;
    const W = 190, H = 58;
    const tries = [[1, -1], [-1, -1], [1, 1], [-1, 1]].map(([dx, dy]) => {
      const bx = dx > 0 ? lead.x + 34 : lead.x - 34 - W;
      const by = dy < 0 ? lead.y - 34 - H : lead.y + 34;
      const hits = plate.nodes.filter((n) => n.x > bx - 14 && n.x < bx + W + 14 && n.y > by - 14 && n.y < by + H + 14).length;
      const out = bx < plate.box.x || bx + W > plate.box.x + plate.box.w || by < plate.box.y || by + H > plate.box.y + plate.box.h ? 50 : 0;
      return { dx, dy, bx, by, hits: hits + out };
    }).sort((a, b) => a.hits - b.hits);
    return { ...tries[0], W, H };
  }, [lead, plate]);
  const k = compact ? 0.55 : 1;
  return (
    <svg className="plate-svg" viewBox={`${plate.box.x} ${plate.box.y} ${plate.box.w} ${plate.box.h}`} role="img"
      aria-label="Illustrative crawl graph. Darker discs are pages further along; vermilion rings mark links judged most relevant.">
      <g className="plate-edges">
        {plate.edges.map(([a, b], i) => {
          const p = byId.get(a), c = byId.get(b);
          return <line key={i} x1={p.x} y1={p.y} x2={c.x} y2={c.y} style={{ animationDelay: `${0.05 + c.depth * 0.12 + i * 0.004}s` }} />;
        })}
      </g>
      <g className="plate-nodes">
        {plate.nodes.map((n) => {
          const r = (n.depth === 0 ? 11 : 10 - n.depth * 1.6) * k + (compact ? 1 : 0);
          const delay = { animationDelay: `${0.1 + n.depth * 0.12 + n.id * 0.004}s` };
          if (n.kind === "dropped" && selective) {
            return <rect key={n.id} x={n.x - r} y={n.y - r} width={r * 2} height={r * 2} className="plate-drop" style={delay} />;
          }
          return (
            <g key={n.id} className="plate-node" style={delay}>
              {selective && n.depth > 0 && n.score > 0.55 && (
                <circle cx={n.x} cy={n.y} r={r + 3.5} fill="none" stroke="#c7311a"
                  strokeWidth={0.75 + n.score * 3} opacity={0.35 + n.score * 0.65} />
              )}
              {n.kind === "trusted" && selective
                ? <rect x={n.x - r} y={n.y - r} width={r * 2} height={r * 2} transform={`rotate(45 ${n.x} ${n.y})`} fill={STAGE[n.depth]} stroke={STROKE[n.depth]} strokeWidth="1.5" />
                : <circle cx={n.x} cy={n.y} r={r} fill={STAGE[n.depth]} stroke={STROKE[n.depth]} strokeWidth={n.depth === 0 ? 2 : 1.5} />}
            </g>
          );
        })}
      </g>
      {!compact && lead && note && (
        <g className="plate-leader" style={{ animationDelay: "0.6s" }}>
          <line x1={lead.x + note.dx * 9} y1={lead.y + note.dy * 9} x2={note.dx > 0 ? note.bx - 4 : note.bx + note.W + 4}
            y2={note.dy < 0 ? note.by + note.H - 4 : note.by + 8} stroke="#c7311a" strokeWidth="1" />
          <rect x={note.bx - 10} y={note.by - 6} width={note.W + 20} height={note.H + 12} className="plate-card" />
          <g textAnchor={note.dx > 0 ? "start" : "end"}>
            <text x={note.dx > 0 ? note.bx : note.bx + note.W} y={note.by + 16} className="plate-score">{Math.round(lead.score * 100)}</text>
            <text x={note.dx > 0 ? note.bx : note.bx + note.W} y={note.by + 36} className="plate-note">Matches the topic; page lists</text>
            <text x={note.dx > 0 ? note.bx : note.bx + note.W} y={note.by + 52} className="plate-note">the terms the crawl asks for.</text>
          </g>
        </g>
      )}
    </svg>
  );
}

function Logo() {
  return <span className="lp-wordmark"><Spider size={28} />CrawlViz</span>;
}

export default function Landing({ onEnter, instant = false }) {
  const open = (demo) => (e) => {
    e.preventDefault();
    if (demo) {
      try { window.history.replaceState(null, "", `${window.location.pathname}?demo${window.location.hash}`); } catch { /* ignore */ }
    }
    onEnter("/graph");
  };

  // The app routes on location.hash, so in-page anchors must scroll, not navigate.
  const jump = (id) => (e) => {
    e.preventDefault();
    const el = document.getElementById(id);
    if (!el) return;
    const calm = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    el.scrollIntoView?.({ behavior: calm ? "auto" : "smooth", block: "start" });
    el.setAttribute("tabindex", "-1");
    el.focus({ preventScroll: true });
  };

  return (
    <div className={instant ? "lp lp-instant" : "lp"}>
      <a className="lp-skip" href="#lp-main" onClick={jump("lp-main")}>Skip to content</a>
      <header className="lp-top">
        <Logo />
        <nav className="lp-nav" aria-label="Sections">
          <a href="#how" onClick={jump("how")}>How it decides</a>
          <a href="#evidence" onClick={jump("evidence")}>Evidence</a>
          <a href="#replay" onClick={jump("replay")}>Replay</a>
          <a href="#limits" onClick={jump("limits")}>Limits</a>
        </nav>
        <a className="lp-btn lp-btn-sm" href="#/graph" onClick={open(false)}>Open the plate</a>
      </header>

      <main id="lp-main">
        <section className="lp-hero">
          <div className="lp-hero-copy">
            <h1>Crawl only the links worth following.</h1>
            <p className="lp-lead">
              CrawlViz is a topic-focused web crawler. It scores every candidate link before it is fetched,
              draws the crawl as a live graph, and keeps the reason for every decision so you can replay it.
            </p>
            <div className="lp-actions">
              <a className="lp-btn lp-btn-solid" href="#/graph" onClick={open(false)}>Open the plate</a>
              <a className="lp-btn" href="#/graph?demo" onClick={open(true)}>Load a sample replay</a>
            </div>
            <p className="lp-fine">Runs locally. Open source, Apache 2.0.</p>
          </div>
          <figure className="lp-plate">
            <Plate seed={12489193} branches={5} />
            <figcaption>Illustrative plate, not a real crawl. Darker discs are further along; vermilion rings mark links judged relevant.</figcaption>
          </figure>
        </section>

        <section className="lp-sec lp-drift" aria-labelledby="drift-h">
          <div className="lp-sec-head">
            <h2 id="drift-h">A breadth-first crawl has no idea what the page means.</h2>
            <p>
              Start from “Black Hole” on Wikipedia and a structural crawl drifts into science fiction and video games
              within a few hops. Those pages are densely linked to the seed and entirely off topic.
            </p>
          </div>
          <div className="lp-pair">
            <figure>
              <Plate seed={77} branches={7} compact selective={false} />
              <figcaption><strong>Follow every link.</strong> The frontier grows by structure alone.</figcaption>
            </figure>
            <figure>
              <Plate seed={77} branches={7} compact />
              <figcaption><strong>Follow the relevant ones.</strong> Low scorers are dropped before they are fetched.</figcaption>
            </figure>
          </div>
        </section>

        <section id="how" className="lp-sec" aria-labelledby="how-h">
          <div className="lp-sec-head">
            <h2 id="how-h">Two stages, so the expensive one stays rare.</h2>
            <p>Every candidate link runs the same cascade. Cheap judgment first, costly judgment only where it is needed.</p>
          </div>
          <ol className="lp-rows">
            <li>
              <h3>Embed locally</h3>
              <p>A sentence-embedding model on your machine scores each link against the topic in milliseconds, with no network call. Clear wins and clear misses are decided here.</p>
            </li>
            <li>
              <h3>Ask a language model, on a budget</h3>
              <p>Only a strategy-dependent sample of the mid-confidence links is sent to an LLM. The budget keeps cost and latency from becoming the crawl’s bottleneck.</p>
            </li>
            <li>
              <h3>Write down why</h3>
              <p>Each score, its signals and the decision land in an event log. Select a page on the graph and read the reason as a one-sentence annotation.</p>
            </li>
          </ol>
        </section>

        <section id="evidence" className="lp-sec lp-evidence" aria-labelledby="ev-h">
          <div className="lp-sec-head">
            <h2 id="ev-h">On the reference run, about one link in a hundred was worth a visit.</h2>
            <p>
              A wikimd.org crawl identified <span className="num">50,828</span> links and explored <span className="num">539</span> of them.
              That narrows the search space while keeping the graph’s topical structure.
            </p>
          </div>
          <figure className="lp-cells">
            <div className="lp-cells-grid" role="img" aria-label="One hundred cells, one filled: about 1 in 100 links was explored.">
              {Array.from({ length: 100 }, (_, i) => <i key={i} className={i === 0 ? "on" : ""} />)}
            </div>
            <figcaption><span className="num">539</span> explored of <span className="num">50,828</span> identified. Each cell is one link in a hundred.</figcaption>
          </figure>
          <p className="lp-caveat">
            This is a structural observation. The evaluation reports no precision or recall against ground-truth labels,
            and CrawlViz does not claim to beat other approaches. Method and numbers are in <code>docs/07-research-and-evaluation.md</code>.
          </p>
        </section>

        <section id="replay" className="lp-sec lp-replay" aria-labelledby="re-h">
          <div className="lp-sec-head">
            <h2 id="re-h">Live and history are the same view.</h2>
            <p>
              The interface is built by replaying an event log through a reducer. Drag the timeline back and the graph
              returns to how it looked, with the same annotations. Errors sit on the scrubber as marked ticks.
            </p>
          </div>
          <figure className="lp-shot">
            <img src="/workspace-sample.webp" width="1440" height="900" loading="lazy"
              alt="The CrawlViz graph workspace showing a sample crawl: pages as discs, vermilion rings and scores on the most relevant, and a timeline scrubber along the bottom." />
            <figcaption>The workspace, loaded with the built-in synthetic sample. Not a real crawl.</figcaption>
          </figure>
        </section>

        <section className="lp-sec" aria-labelledby="bp-h">
          <div className="lp-sec-head">
            <h2 id="bp-h">A crawl is a blueprint you can read.</h2>
            <p>
              Sources, topic, extraction rules and limits live in a declarative JSON file. The repository ships two:
              <code> templates/wikiMD.json</code> and <code>templates/isi.json</code>. A six-step editor builds them for you.
            </p>
          </div>
          <pre className="lp-code" aria-label="Excerpt of templates/wikiMD.json"><code>{`{
  "target_topic": "Type 2 Diabetes",
  "seeds": [{ "url": "https://www.wikimd.org/wiki/Diabetes" }],
  "scoring": { "strategy": "TOPICAL" },
  "extraction": { "mode": "document" }
}`}</code></pre>
          <p className="lp-small">Excerpt of <code>templates/wikiMD.json</code>.</p>
        </section>

        <section id="limits" className="lp-sec" aria-labelledby="lim-h">
          <div className="lp-sec-head">
            <h2 id="lim-h">What it is not.</h2>
          </div>
          <ul className="lp-rows lp-limits">
            <li><h3>Single process</h3><p>One asyncio process with a local SQLite store. It is not distributed.</p></li>
            <li><h3>Research scope</h3><p>Built to make scoring decisions traceable, not to crawl the web at scale.</p></li>
            <li><h3>Desktop first</h3><p>The graph workspace is designed for desktop screens.</p></li>
          </ul>
        </section>

        <section className="lp-cta" aria-labelledby="cta-h">
          <h2 id="cta-h">See why it went where it went.</h2>
          <p className="lp-run">Clone the repository, then run <code>make dev</code> and open <span className="num">localhost:5173</span>.</p>
          <div className="lp-actions">
            <a className="lp-btn lp-btn-solid" href="#/graph" onClick={open(false)}>Open the plate</a>
            <a className="lp-btn" href={REPO} target="_blank" rel="noreferrer">Read the source</a>
          </div>
        </section>
      </main>

      <footer className="lp-foot">
        <Logo />
        <span>Apache 2.0</span>
        <a href={REPO} target="_blank" rel="noreferrer">GitHub</a>
      </footer>
    </div>
  );
}
