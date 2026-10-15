# Config page: persona findings (input to iteration 2)

Collected during the first pass of `config_pass_plan.md`. Fixes listed here are not part of that pass unless
marked "done". Personas: **Python dev** (knows code, not IR), **Researcher** (knows the domain, not Python),
**PhD** (knows science, not AI engineering), **Omar** (owner of the project; knows the code and the research
question, audits as the person who has to explain every control).

## Findings

| # | Complaint | Persona | Severity | Suggested direction | Status |
|---|-----------|---------|----------|---------------------|--------|
| 1 | Scoring cascade sliders did not work: the page was served by a backend started before the range-pair schema hints, so thresholds drew as independent sliders that could cross | Omar | high | Restart fixed it. The UI should say when the schema lacks the hints it expects instead of silently falling back | backend restarted; fallback warning open |
| 2 | Pace chart was ugly, clipped at the top, and its axes were unnamed | Omar | high | Two charts on one time axis, named axes with units, nice tick values, no clipping | done |
| 3 | "Example, not your data" badge on every explainer is redundant | Omar | low | Replace with one line naming the example crawl and its target | done |
| 4 | Priority strategies: example links were generic and the target was not stated | Omar | medium | Name the target and a concrete crawl, real-looking page titles, depth per link, legend for the bar colours | done |
| 5 | Top-k and context length need the example target stated, and a slider is cleaner than a number box | Omar | medium | Slider with bounds, example names its target and the link being scored | done |
| 6 | Pipelines section is still a plain table of numbers | Omar | medium | Redesign (workers and queue bounds explained, effect on memory and throughput). Audit next phase | open |
| 7 | Fetch screen is still a form: a chart on top of a column of numeric boxes. The settings are not shown acting on anything | Omar | medium | Make the controls part of the picture (drag the delay and cap on the timeline itself); group by what the user is trying to do (be gentler / go faster / look like a browser) | open |
| 8 | Strategy example used terms (Erasmus, doctoral programmes) not everyone knows | Omar | medium | Use an everyday target ("bananas") so the example costs no thinking | done |
| 9 | NLP and LLM biases are two independent sliders that must be read together | Omar | medium | One slider from pure NLP to pure LLM; the two always make 100 % | done |
| 10 | No ready-made request headers; user agent and accept fields are blank text boxes | Omar | low | Header sets (research bot, Chrome, Firefox, Mobile Safari, minimal) that fill every header field | done |
| 11 | Pipelines still not visual enough (opinion, not an action item) | Omar | n/a | Draw the stages as a flow with queue depth and workers, rather than a table | open |

## Hypotheses carried over from the plan (to confirm or drop)
- Glossary tooltips for LLM, embedding, cosine, DBSCAN, percentile, backoff, queue.
- Per-field "what changes if I raise this" one-liners; unit and impact hints.
- Explainers for the remaining numeric sections (Retries, Embeddings, Export).
