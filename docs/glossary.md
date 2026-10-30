# Glossary

The words CrawlViz uses for its own ideas. The UI, the API errors, the docs and the code
comments use the word in the **Say** column, with the meaning given here (NAME-4). The
**Key** is the one snake_case name the code, settings, wire and catalogs use for it
(NAME-5). The **Not** column lists words that must not stand in for it, usually because
they already mean something else here.

Owner: design-system-engineer. A new term, or a change of meaning, is added here before it
appears in the UI. The UI's `Term` component (`crawler-ui/src/shared/ui/Term.tsx`) shows the
**Meaning** text as the explanation, so write it as one or two plain sentences a first-time
reader understands.

## Crawl setup

| Say | Key | Meaning | Not |
|---|---|---|---|
| blueprint | `blueprint` | A saved description of one crawl: its topic, its seed pages, the sites it may visit, how it scores links and what it extracts from each page. | template, config, preset |
| seed page | `seeds` | A page the crawl starts from. A blueprint lists one or more. | seed (alone), start URL, root |
| random seed | `seed` (in `run`) | The number that starts every random choice in a crawl. Two runs with the same random seed and settings make the same random choices. Empty means a new random seed each run. | seed (alone) |
| topic | `target_topic` | The subject the crawl is looking for, written as a short description. | target, query |
| settings | `settings` | The stored values that tune how every crawl runs (pacing, workers, cut-offs). A blueprint can override some of them for its own crawls. | config (in the UI) |
| preset | `preset` | A named set of settings values that can be applied to the current settings. | blueprint, profile |
| run override | `overrides` | A settings value changed for one crawl only, at start, without changing the stored settings. | |

"Template" is no longer a separate idea: every saved crawl description is a blueprint. The
`templates/` folder and the `/templates` routes keep their names until the API v2 move
(ADR 12); the UI says "blueprint" everywhere.

"Seed" on its own is ambiguous and is never shown to a user. Say "seed page" for where the
crawl starts and "random seed" for the number.

## The crawl

| Say | Key | Meaning | Not |
|---|---|---|---|
| crawl | `crawl` | One run of the crawler from its seed pages until a limit is reached, it runs out of links or you stop it. | job, session |
| run | `run` | A crawl that has been recorded and can be opened again, with its blueprint, settings and every event. Live or finished, a crawl and its run are the same thing seen at different times. | |
| page | `node` (code) | A web page the crawl has found. The code calls it a node; the UI calls it a page. | node (in the UI), item, document |
| link | `link`, `candidate` | A hyperlink found on a fetched page. A link that is being judged is a candidate in the code. | edge (in the UI), URL (for the link itself) |
| frontier | `frontier` | The pages that have been found and are waiting to be fetched, ordered by priority. | queue (in the UI), backlog |
| priority | `priority` | A page's place in the frontier. Higher priority is fetched sooner. | rank, importance |
| fetch | `fetch` | Downloading one page. "Pages fetched" counts downloads that succeeded. | crawl (for one page), visit, request |
| pages found | | Pages the crawl knows about, fetched or not. Always shown beside "pages fetched", never instead of it. | nodes, total |
| relevant page | | A page judged on topic. In the benchmark, a page labelled 1 or 2. For a live crawl the rule is not fixed yet; it is written here when the runs list (R-RUNS) defines it. | hit, good page |
| depth | `depth` | How many links away from a seed page a page is. Seed pages are depth 0. | level, distance |
| spanning tree | | The drawing of the crawl as a tree: each page hangs from the first page that linked to it, so the graph shows one path from a seed page to every page. Links from other pages exist but are not drawn as tree branches. | graph (when the tree is meant), hierarchy |

## Scoring

| Say | Key | Meaning | Not |
|---|---|---|---|
| score | | A number that says how relevant a link or page looks. Every score is shown on one scale from 0 to 100, where higher is more relevant. | rating, confidence |
| NLP score | `nlp_score` | A fast score computed on this machine from the link's text, its context and the topic, with no LLM call. | similarity, semantic score |
| LLM score | `llm_score` | A relevance judgement from the language model. Each one costs part of a request. | AI score, model score |
| final priority | `priority` | The score that orders the frontier, mixed from the NLP and LLM scores by the priority strategy. | final score, total |
| cosine | `cosine` | How closely two pieces of text point the same way in meaning, from 0 (unrelated) to 1 (the same direction). Shown only as secondary text, labelled "cosine". | similarity (alone) |
| cascade | `scoring_cascade` | The two-step filter: the NLP score settles most links, and only the uncertain ones go to the LLM. | pipeline, funnel |
| bucket | | Where the cascade put a link: **dropped** (too low to follow), **sampled** (low, but kept to explore), **sent to the LLM** (uncertain) or **trusted** (high enough to follow on the NLP score alone). | tier, band (except "middle band") |
| cut-off | `low_threshold`, `high_threshold` | A score that separates two buckets. The low cut-off drops links below it; the high cut-off trusts links above it. | threshold (in the UI) |
| priority strategy | `default_priority_strategy` | The rule that turns signals and scores into a priority. | algorithm, mode |
| run mode | `mode` | How the crawl gets its LLM answers: **offline** (scripted answers, no network, for demos and tests), **cached** (answers recorded by an earlier run, no new calls) or **live** (a real provider and model, which costs requests). | demo (for offline), environment |
| sample | | The UI-only demo crawl that never contacts the backend. It is not the offline run mode and its results are not real. | demo mode, offline |

### Score scale

Scores are stored as each source produces them and shown on one scale (R-SCALE, ADR 12):

| Score | Stored as | Shown as |
|---|---|---|
| NLP score | 0 to 1 | 0 to 100 |
| LLM score | 0 to 100 | 0 to 100 |
| final priority | 0 to 1 | 0 to 100 |

Shown scores are whole numbers ("72"), formatted only by `formatScore` in
`crawler-ui/src/shared/lib/format.ts`. Where a raw value matters, it is shown after the
score as secondary text with its name ("cosine 0.61"). The conversion factors come from the
backend (`score_scales` in `/ui-config`, ADR 9), so the UI never has its own copy of them.

### NLP signals

The NLP score is built from these signals. Each is a number from the link's text, its
context and what the crawl has seen so far. The UI shows the **Say** name and the meaning
as its `Term` explanation; the key appears only in exports and the API.

| Say | Key | Meaning |
|---|---|---|
| closeness to topic | `target_similarity` | How close the link is to the topic's reference texts. |
| anchor closeness | `anchor_similarity` | How close the link's own clickable text is to the topic. |
| context fit | `contextual_consistency` | Whether the text around the link matches the page it sits on. |
| shared words | `lexical_overlap` | Words the link's text shares with the page that linked to it, or with the topic's vocabulary. |
| parent relevance | `parent_relevance` | How relevant the page that linked to it was. |
| meaning shift | `semantic_delta` | How far the link's meaning moves from the page that linked to it. |
| novelty | `novelty_injection` | How unlike the pages already seen it is. Used as a bonus so the crawl does not keep fetching near-copies. |
| coverage gap | `coverage_gap` | Close to the topic, in a region the crawl has barely visited. Used as a bonus. |
| crowding | `region_density` | How many pages already seen lie close to it. |
| cluster distance | `cluster_distance` | How far it is from the nearest group of pages seen so far. |
| site furniture | `boilerplate_score` | How much it looks like navigation or legal text (contact, privacy, copyright). High values lower the score. |
| depth penalty | `depth_penalty` | Points taken off for each link of depth. |

## Skip reasons

Every link that was not followed has exactly one of these reasons (R-SKIP-REASON, ADR 12).
The UI shows the **Say** text; the key is the wire and API value.

| Say | Key | Meaning |
|---|---|---|
| Below the cut-off | `below_cutoff` | Its score was under the low cut-off, so the cascade dropped it as off-topic. |
| Not sampled | `not_sampled` | It was in a bucket where only a share of links is kept, and it was not picked. |
| Too deep | `depth_limit` | Following it would go past the crawl's depth limit. |
| Already found | `duplicate` | The same page was already in the crawl under this or an equivalent URL. |
| Blocked by robots.txt | `robots_disallowed` | The site's robots.txt asks crawlers not to fetch it. |
| Budget used up | `budget_exhausted` | The crawl had no page or LLM budget left when the link's turn came. |
| Not fetched before the stop | `unfetched_at_stop` | It was still waiting in the frontier when the crawl stopped. |
| Gave up after retries | `retries_exhausted` | Every attempt to fetch it failed, and the crawl stopped trying. |

## Pipeline parts

The crawler is a set of parts that pass events to each other (ADR 6, NAME-5). Each part has
one role:

| Say | Suffix | Meaning | Examples |
|---|---|---|---|
| stage | `<Verb>Stage` | Does crawl work and publishes the events that move the crawl on. | Fetch, Extract, Score, Filter, Prioritize |
| sink | `<Noun>Sink` | Writes events out to a file or database, and reports only its own result. | Storage, Export, Crawl log |
| observer | `<Noun>Observer` | Watches events and never changes the crawl. | Telemetry (the live graph feed) |
| controller | `<Noun>Controller` | Decides when the crawl starts and stops, or changes its settings while it runs. | Stop, Live settings, Crawl |
| worker | | One of the parallel loops inside a part that takes the next item from its queue. | |
| subsystem | | A long-running piece the crawl depends on (embedder, LLM, robots, fetch), each with a state on the health strip. | |

The UI names a part by its catalog label ("Fetch"), never by its key (`fetch`) or class
(`FetchStage`).

## Benchmark and evaluation

| Say | Key | Meaning | Not |
|---|---|---|---|
| frozen graph | `FrozenGraph` | A recorded copy of a site's pages and links. Every arm crawls the same copy, so the comparison is fair and needs no network. | snapshot, dataset |
| arm | `arm` | One crawling policy being compared, for example the cascade or "every link to the LLM". | policy (in the UI), variant |
| label | `label` | A page's relevance grade in the frozen graph: 0, 1 or 2, where 2 is the most relevant. Pages labelled 1 or 2 count as relevant. | score, rating |
| harvest@k | `harvest_at` | The share of the first k fetched pages that are relevant. Harvest@30 of 0.4 means 12 of the first 30 pages were relevant. | precision, hit rate |
| NDCG@k | `ndcg_at` | How close the order of the first k fetches is to the best possible order, from 0 to 1. A label-2 page counts twice as much as a label-1 page, and pages fetched earlier count more. | accuracy |
| recall@k | `recall_at` | The share of all relevant pages in the graph that were among the first k fetches. | coverage |
| replay | | A run repeated from its recorded LLM answers, making no new LLM calls. | rerun (which makes new calls) |

## Words to avoid in the UI

- **Node**, **edge**: say page and link.
- **Seed** alone: say seed page or random seed.
- **Template**: say blueprint.
- **Config**: say settings; "Config" stays only as the name of the settings page until the
  page is renamed.
- **Threshold**: say cut-off.
- **Pipeline** for one part: say stage, sink, observer or controller.
