---
name: CrawlViz
description: An analytical plate of a crawl. Cool paper, blue-black ink, hairline rules, one vermilion mark for relevance.
colors:
  paper: "#f3f5f7"
  sheet: "#fbfcfd"
  rule: "#d3d9e0"
  row-rule: "#e3e8ee"
  ink: "#0f1b2d"
  ink-2: "#33435a"
  muted: "#566478"
  vermilion: "#c7311a"
  plum-error: "#7a1f5c"
  stage-created: "#e3e8ee"
  stage-fetched: "#b7c1cd"
  stage-filtered: "#8794a5"
  stage-scored: "#56657a"
  edge: "#a3adba"
  scrollbar: "#aab4c0"
typography:
  wordmark:
    fontFamily: "'Source Serif 4', Georgia, serif"
    fontSize: "20px"
    fontWeight: 600
    letterSpacing: "-0.01em"
  display-stat:
    fontFamily: "'Source Serif 4', Georgia, serif"
    fontSize: "22px"
    fontWeight: 600
  annotation:
    fontFamily: "'Source Serif 4', Georgia, serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.45
  landing-display:
    fontFamily: "'Source Serif 4', Georgia, serif"
    fontSize: "clamp(40px, 5.6vw, 76px)"
    fontWeight: 600
    letterSpacing: "-0.025em"
    lineHeight: 1.04
  landing-lead:
    fontFamily: "'Public Sans', system-ui, sans-serif"
    fontSize: "19px"
    fontWeight: 400
    lineHeight: 1.55
  nav:
    fontFamily: "'Public Sans', system-ui, sans-serif"
    fontSize: "14px"
    fontWeight: 500
  body:
    fontFamily: "'Public Sans', system-ui, sans-serif"
    fontSize: "13px"
    fontWeight: 400
  label:
    fontFamily: "'Public Sans', system-ui, sans-serif"
    fontSize: "12px"
    fontWeight: 500
    letterSpacing: "0"
  data:
    fontFamily: "'JetBrains Mono', ui-monospace, monospace"
    fontSize: "12px"
    fontWeight: 400
    fontFeature: "tabular-nums"
rounded:
  sm: "2px"
  md: "3px"
  lg: "4px"
  full: "50%"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "24px"
components:
  nav-tab:
    backgroundColor: "transparent"
    textColor: "{colors.ink-2}"
    typography: "{typography.nav}"
    height: "48px"
    padding: "0 14px"
  nav-tab-active:
    textColor: "{colors.ink}"
  button-outline:
    backgroundColor: "transparent"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    height: "30px"
    padding: "0 12px"
  button-outline-pressed:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.sheet}"
  button-destructive-armed:
    backgroundColor: "{colors.plum-error}"
    textColor: "#ffffff"
    rounded: "{rounded.md}"
    height: "30px"
  floating-key:
    backgroundColor: "{colors.sheet}"
    textColor: "{colors.ink-2}"
    rounded: "{rounded.lg}"
    padding: "10px 14px"
  timeline-dock:
    backgroundColor: "{colors.sheet}"
    textColor: "{colors.ink-2}"
    height: "56px"
    padding: "0 20px"
  annotation-panel:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    width: "380px"
  state-chip:
    backgroundColor: "{colors.rule}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "2px 7px"
---

# Design System: CrawlViz

## Overview

**Creative North Star: "The Specimen Plate"**

CrawlViz reads as a data-graphics plate (Bertin and Tufte, not dashboard chrome). The graph is the specimen, the docked timeline is the measurement record, and the right panel is the margin annotation that says why the crawler went where it did. Ground is cool grey-white paper, ink is blue-black, structure is hairline rules. Everything is flat.

Colour is rationed. Lifecycle stage is one neutral ink ramp ordered by lightness. Structural and outcome distinctions (dropped, trusted, selected, errored) ride on shape, stroke and word, never on hue. The single chromatic voice is vermilion, reserved for relevance: how promising the crawler judged a link.

Density is operator-grade: 13px body, 12px labels, tabular figures for every number. Plain literal labels ("Crawling", "Finished", "Skipped as off-topic") replace codes and jargon wherever a person reads them.

**Key Characteristics:**
- Cool paper ground, blue-black ink, 1px rules; no gradients, no glow.
- Vermilion appears only as the relevance ring, leader line and score figure.
- Stage by lightness, role by shape, errors by plum plus a word.
- Serif for voice (wordmark, annotation sentence), sans for UI, mono for data.
- Numbers in tabular figures; annotations as leader lines with values.

## Colors

A near-monochrome ink-on-paper palette with one hot spot colour.

### Primary
- **Vermilion Mark** (`vermilion`): relevance only. Node relevance ring (stroke width 0.75 to 4px, opacity 0.35 to 1 scaled with score), the leader line and score figure for links rated 70+ out of 100, caret colour in inputs, and the text selection tint at 18%. Its rarity is the point.

### Secondary
- **Plum Error** (`plum-error`): errors and failures only (error count, NODE_ERROR ticks, failed pipeline stage, armed "Confirm stop"). Always paired with a word or shape.

### Neutral
- **Cool Paper** (`paper`): app ground and annotation panel.
- **Sheet** (`sheet`): raised-by-tone surfaces: top rule, timeline dock, floating key and filter bar.
- **Hairline Rule** (`rule`): every border and divider. `row-rule` for quieter row dividers.
- **Blue-Black Ink** (`ink`): primary text, active nav, focus outline, the EXPANDED node fill.
- **Slate Ink** (`ink-2`): body and secondary text (8.6:1 on paper).
- **Muted Slate** (`muted`): tertiary text and captions (5.4:1 on paper).
- **Stage Ramp** (`stage-created` to `stage-scored`, then `ink`): node fills, light = early, dark = further along. Node strokes use a darker companion per stage.
- **Edge Grey** (`edge`): graph edges at 1.2px, 0.7 opacity.

### Named Rules
**The Relevance-Only Vermilion Rule.** Vermilion means "the crawler thinks this is promising" and nothing else. Never use it for buttons, links, errors, warnings or branding.

**The Lightness-Is-Progress Rule.** Lifecycle stage is encoded by one neutral ramp, never by new hues.

**The Shape-Not-Hue Rule.** Dropped candidates are hollow dashed squares, trusted-on-NLP candidates are filled diamonds, selection is a dashed ring. Add a new distinction by shape or stroke, not colour.

## Typography

**Display Font:** Source Serif 4 (with Georgia, serif)
**Body Font:** Public Sans (with system-ui, sans-serif)
**Label/Mono Font:** JetBrains Mono (with ui-monospace, monospace), used for URLs, timestamps and graph scores.

**Character:** A printed-plate voice: a book serif for the wordmark and the one-sentence "why", a neutral grotesque for the working UI, a mono for raw data.

### Hierarchy
- **Wordmark** (600, 20px, -0.01em): "CrawlViz" in the top rule.
- **Display stat** (600, 22px, serif): metric values in the Measurements drawer; legacy stat tiles use 30px.
- **Landing display** (600, 40 to 76px fluid, -0.025em, 1.04): the landing headline only; section headings are serif 600 at 28 to 44px. **Landing lead** (400, 19px, 1.55, 52ch). Landing body is 16px; captions 13 to 14px, never below 12px.
- **Annotation** (400, 15px, 1.45): the serif "why" sentence at the top of the annotation panel, and panel header titles.
- **Nav** (500, 14px; 600 when active): top-rule section tabs.
- **Body** (400, 13px): default UI text, buttons (13px, 500 to 600).
- **Label** (500, 12px, no tracking, sentence case): legend headings, row keys, chips, captions. 11px for dense inspector rows.
- **Data** (400 to 600, 12px, mono, tabular): URLs, timestamps, graph score figures.

### Named Rules
**The Tabular Figure Rule.** Every number, score and count is set in tabular figures (`.num`, tables, `output`).

**The Plain Words Rule.** State is a literal word beside its mark ("Crawling", "Finished", "Waiting for backend"). Labels stay sentence case.

## Layout

Full-bleed canvas under a 48px top rule (wordmark, text nav, right-aligned summary, status, actions). The graph fills the remaining viewport; a 56px timeline dock sits at the bottom (expands to a 260px event list); a 380px annotation panel docks right only when a node is selected. The key (bottom-left) and filter bar (top-left) float over the graph at 16px inset. Spacing scale is 4, 8, 12, 16, 24px; shell gutters are 20px. The graph workspace is desktop-first: below 820px the top rule wraps, and the Page frame stacks, but the graph itself is not designed for touch. The landing page is fully responsive (single column under 820px, 16 to 20px gutters). Measurements is a toggled drawer, not a page.

The graph is a radial tree, and its layout is deterministic: the same crawl and the same screen always give the same plate, and a fold, unfold or replay seek moves every page to its goal along a short eased glide (about 450ms, or at once on very big plates) rather than settling under physics. Dragging a page is allowed; letting go sends it back to its place. Seed at the centre, one ring per depth, each page inside its parent's angular sector (stretched sideways to the canvas). Edges are drawn as radial-tree links (out along the parent's spoke, across at the middle ring, in along the child's), so siblings share the start of their path and fan out instead of overlapping as straight lines. What is drawn follows one model of what a screen can show, not a set of thresholds. Pages are laid out at least 30px apart; two pages are only tellable apart if the whole-plate zoom keeps them 20px apart on screen. When the whole crawl would not be, the least important pages (the crawler's rating, how far the page got, closeness to the seed) fold into dashed "+N pages" nodes until it is, found by bisection; the seed, the selection and its neighbourhood, search hits and branches the viewer opened are pinned and never fold, and a kept page keeps its path to the seed. A big screen therefore shows more than a small one. "Show all" lifts the fold. Rules are screen-pixel rules: edges are 1px hairlines (fainter as links multiply, arrowheads only on links long enough to carry one), and the relevance ring, page outline and selection ring keep their weight at every zoom. Text is annotation, set in screen space at 11px at every zoom and placed in one pass once the plate rests: the viewport can carry only a fixed share of its area in labels, the most important pages in view compete for it, each annotation tries its spoke position then below, above and either side, takes the first spot clear of other text and of every page (preferring the one crossing the fewest edges), and is simply not drawn if none is clear. Scores are placed before labels, and the selection is always labelled. The route `#/` is a separate landing page in the same world (see Components).

## Elevation & Depth

Flat by tonal layering. Depth is paper versus sheet plus a 1px rule; floating key and filter bar are sheet with a hairline border, no shadow. Focus is a 2px ink outline with 2px offset. Motion in the workspace is minimal: a 1.6s opacity "breathe" on the running status mark, 300 ms fit-to-view glides, 500 ms node entry (none on large plates). The two authored moments elsewhere are the loader (spider drop, web drawing out) and the landing plate growing in within about a second. All are shortened or removed under `prefers-reduced-motion`; state changes never depend on them.

### Named Rules
**The No-Glow Rule.** No gradients, glows or blurred shadows on the plate surfaces; separation is tone and hairline only.

## Shapes

Near-square: 2px (chips), 3px (buttons), 4px (floating panels); 50% only for node circles and status dots. Nodes are circles sized by lifecycle (radius 5 to 11px, seed 11px); the relevance ring sits 3.5px outside the body. Status marks are 10px SVG shapes: filled circle (running), filled square (finished), hollow ring (idle).

## Components

### Top rule and navigation
Sheet bar, 1px bottom rule. Tabs are 48px tall text buttons with a 2px ink underline when active, ink-2 otherwise. The Run tab carries a 6px plum square when errors exist.

### Buttons
Outline buttons: 30px, 3px radius, 1px ink border, transparent; pressed state inverts to ink fill with sheet text (Measurements, Return to live). Stop crawl is a two-click confirm: first click arms it (plum fill, white text, "Confirm stop"), auto-disarms after 4s.

### Floating key and filter bar
Sheet, 1px rule, 4px radius. The key has three groups: stage ramp with "Found" to "Expanded", relevance rings "Low" to "High", and "Never fetched" (dashed square, diamond). The filter bar has an underline-only search input and a checkbox.

### Timeline dock
"Live" or "Return to live", then a transport group (first event, previous, play/pause, next, return to live, and a 1x/4x/16x speed toggle; 30px outline buttons, pressed = ink fill), then the scrubber: the event record drawn as a band of 3px bars with 2px gaps, 22px tall, each bar as tall as the activity in its slice of the record (pipeline chatter is not counted). Played slices are ink, the rest pale slate (the stage-fetched grey), slices holding an error are plum and a stop stands at full height. The playhead is a 2px ink rule with a downward notch on top (wider while focused). Hovering or dragging shows a margin-note tooltip (sheet, hairline, 4px radius) with the event number, clock time and pages found at that point. It is a single `role="slider"`: arrows step one event, Shift ten, Page keys fifty, Home the start, End back to live. Playback ends by handing back to live. Then an "Event N of M" tabular readout and a Show/Hide events toggle. Event filter chips are 12px, 2px radius, struck through when off.

### Annotation panel
380px paper column with a left hairline. Header is host (serif 600) over path (muted). Below it a 15px serif why-sentence, then Overview / Scoring / Activity tabs (2px ink underline). Scoring shows NLP sub-signals as 6px bars: solid ink for positive, hatched ink-2 for negative.

### State chip
Rule-grey fill, ink text, 2px radius, preceded by a 9px swatch of the state's own fill and stroke so text never sits on the dark ramp.

### Graph node (signature)
Stage-ramp disc, darker stroke (2px when EXPANDED), optional vermilion relevance ring, vermilion leader line and mono score for scores of 70+, dashed ink selection ring at radius+9, labels only for seeds, expanded, selected or 60+ relevance nodes with halo-stroke and overlap decluttering. Non-neighbourhood nodes dim to 0.12 opacity on selection.

### Landing page
Persuade surface at `#/`, same paper, ink, hairline and vermilion rules as the plate; no cards, no gradients. Serif display headline, a generated illustrative plate in the hero (captioned as illustrative), a same-seed comparison of following every link against following the relevant ones, ruled rows for the two-stage cascade, the reference-run evidence as a 100-cell grid with one cell filled, a real screenshot of the workspace on the synthetic sample, a blueprint excerpt, limits, and a closing call to action. No testimonials or claims beyond PRODUCT.md evidence.

### Spider mark and loader
A drawn ink spider (`features/loading/Spider.jsx`) is the brand mark beside the wordmark (static) and the subject of the page-wide loader: it drops on a thread onto a web that draws itself, and one vermilion ring closes the load. The loader plays once per browser session (about 1.8s; 1.1s into the app), is skippable (button, Esc, Enter, click), announces itself as a status, and its bar is a timed reveal, not a measurement. The ring at the end is the only vermilion in it.

### Zoom utility
A vertical group at the graph's bottom-right (16px inset): the zoom level as a tabular percentage, then four 30px outline buttons drawn with 1.5px strokes: zoom in, zoom out, fit the whole plate, centre on the selected page. It sits on a sheet panel with a hairline border and 4px radius, like the key. Each step is a x1.4 change about the middle of the view; keys do the same (+, -, 0 to fit, F to centre on the selection) and are ignored while typing in a field. Zoom in and out disable at the 2% and 400% limits, and centring is disabled until a page is selected. Fit also hands the plate back to automatic fitting; any manual zoom turns that off until fit is pressed again.

### Fold node
A dashed circle sized by log of its page count, labelled "+N pages", paper fill and slate dashed stroke. Activating it (click, Enter, Space) opens that branch. It carries no relevance ring.

## Do's and Don'ts

### Do:
- **Do** keep every surface on paper or sheet with a 1px `rule` border.
- **Do** reserve vermilion for relevance and pair every error with plum plus a word.
- **Do** encode any new graph distinction by shape, stroke or dash pattern.
- **Do** put numbers in tabular figures and use literal sentence-case labels.
- **Do** use the 2px ink focus outline and honour `prefers-reduced-motion`.

### Don't:
- **Don't** use dark backgrounds, neon accents, glows or gradients.
- **Don't** add hue to the stage ramp or use colour alone to carry meaning.
- **Don't** replace the labelled text nav with an icon rail.
- **Don't** set body text lighter than `muted` or below 11px.

## Known Gaps

- Run, Config and Data are redesigned in the plate grammar on a shared page frame (`src/features/common/Page.jsx`): serif title, one-sentence lead, ruled rows, no cards. Data is a specimen list (serif title, URL, excerpt, field census, expandable fields, and the LLM score plus "Open in graph" when the page is in the current graph). Blueprints is a six-step editor (About, Sources, Relevance, Extraction, Limits, Review) on shared form components (`src/features/common/Form.jsx`). Page titles are 22px serif and section titles 17px. Plum on a destructive control appears only when it is armed.
- The bridge-node ring is deferred: the backend emits no bridge signal. The crawl-topic title in the top rule is deferred: app state carries no blueprint name.

- Large crawls: edges draw on a canvas under the SVG, pages outside the window are not painted, dispatch is batched per frame. Verified to 3,000 synthetic pages (`?demo=N`); not yet on a real 50,000-link crawl. Nodes are still SVG (no WebGL), the event log is unbounded in memory, and there is no treemap fallback layout.
- The loader mascot is a pun (crawler, spider) and sits slightly outside the no-illustration rule; it is kept deliberately and stays out of the working screens except as the small wordmark mark.

Not canonized (build carries, future surfaces must not inherit): the legacy status pill (`statusBadgeWrap`/`statusDot` in `components.js`: 20px pill, glow `boxShadow` and pulse on the running dot), the `panel` drop shadow token (`0 1px 2px / 0 8px 24px`) used by the legacy floating node panel, and the leftover `pill` green and gold tones, which contradict the no-glow and colour-discipline rules.
