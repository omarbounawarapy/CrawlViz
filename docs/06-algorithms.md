# Algorithms

Formal descriptions of CrawlViz's core scoring, priority, and resilience functions. These correspond directly to the formulas in report [Chapter 2 — Algorithmic Design Principles and Software Architecture](../report/rapport-english.pdf#page=10) and have been cross-checked against the actual implementation.

## 1. Target Relevance via Semantic Basis

A candidate link $c$ is not scored against a single topic vector, but against a **basis** of vectors

```math
\mathcal{B} = \{b_1, \ldots, b_n\}
```

representing multiple facets of the target topic, including seed pages, the configured topic description, and LLM-generated conceptual expansions.

The relevance of candidate $c$ is defined as

```math
\mathrm{relevance}(c)
=
\max_i
\mathrm{cos\_sim}\left(E(c), b_i\right)
```

where $E(c)$ is the sentence embedding of the link's composite representation, consisting of its anchor text, URL, and local context.

Using the maximum similarity rather than a mean or centroid similarity is deliberate: a link only needs to strongly match **one facet** of a multi-faceted topic to be considered relevant. Averaging similarities across facets would penalize links that are highly relevant to a narrow subtopic but weakly related to other facets.

### Cold Start

At $t=0$, the basis $\mathcal{B}$ contains only seed-page embeddings and the raw topic description. This representation is too sparse to provide a strong semantic signal and behaves in practice more like a lexical-overlap detector.

The system mitigates this cold-start problem by having the LLM generate $k$ conceptual expansions of the topic before crawling begins. In the reference run, $k=50$. Each expansion is embedded and added to the basis. This mirrors the report's framing of cold-start as an "embedding bootstrapping" strategy ([§2.1.3 — Multi-Facet Representation of the Topic](../report/rapport-english.pdf#page=11)).

The basis can then continue to grow during the crawl as the LLM produces further expansions while scoring links via `nlp/space_updater.py`. This implements an **online basis-enrichment** mechanism rather than relying on a fixed target representation.

---

## 2. Composite NLP Score

`NLPService._composite_score()` combines several named scalar signals into a single value:

```math
\mathrm{nlp\_score}(c)
=
w_1\mathrm{sim}(c)
+
w_2\mathrm{coverage}(c)
+
w_3\mathrm{novelty}(c)
+
w_4\mathrm{coherence}(c)
+
w_5\mathrm{lexical}(c)
```

This score is used **only to route candidates into the low, mid, or high cascade bucket**. It is not the value used directly for frontier priority.

Here:

* $\mathrm{sim}(c)$ is the target-semantic similarity.
* $\mathrm{coverage}(c)$ estimates how well the candidate fills an under-explored region of the semantic space.
* $\mathrm{novelty}(c)$ measures how far the candidate lies from regions already represented by visited content.
* $\mathrm{coherence}(c)$ measures semantic consistency with the surrounding content.
* $\mathrm{lexical}(c)$ captures lexical relevance.

Similarity carries the dominant weight.

`coverage` and `novelty` are derived from a DBSCAN clustering pass over embeddings of already visited content. Although both originate from the same clustering structure, they answer different questions:

* **Novelty:** Is this candidate unlike anything already seen?
* **Coverage:** Does this candidate help fill an under-explored region of the identified semantic space?

---

## 3. Cascade Bucketing

Given configurable thresholds $L$ and $H$, the bucket assigned to candidate $c$ is (the report frames the same three-way split in [§2.3.2, "Bucketing of Candidates"](../report/rapport-english.pdf#page=12)):

```math
\mathrm{bucket}(c)
=
\begin{cases}
\mathrm{low}, & \mathrm{nlp\_score}(c) < L \\[4pt]
\mathrm{mid}, & L \leq \mathrm{nlp\_score}(c) \leq H \\[4pt]
\mathrm{high}, & \mathrm{nlp\_score}(c) > H
\end{cases}
```

Sampling is then applied independently within each bucket.

### Low Bucket

A random sample of size

```math
\left\lfloor
\beta_{\text{low}}
\cdot
|\mathrm{low}|
\right\rfloor
```

is retained for LLM evaluation. The remaining candidates are discarded without further evaluation.

This sampling provides an explicit **exploration budget**. Without it, the crawler could converge prematurely on a local optimum: once a region had been classified as low-relevance, it would never be reconsidered even if that classification were incorrect.

### Mid Bucket

All mid-score candidates are sent to the LLM. This is the uncertainty band in which the inexpensive NLP signal alone is insufficient to make a reliable decision.

### High Bucket

The high bucket combines a top-$K$ selection of the most confident candidates with a random sample. These candidates are sent to the LLM both to confirm high-confidence predictions and to improve precision.

The remaining high-score candidates are tagged `trusted_no_llm` and bypass LLM evaluation entirely.

---

## 4. Priority Function

The frontier priority is a **separate computation** from the composite NLP score described above, matching the general form $P(n) = \lambda_1 S_{\text{NLP}}(n) + \lambda_2 S_{\text{LLM}}(n)$ given in the report's [§2.3 — Two-Stage Scoring Architecture](../report/rapport-english.pdf#page=12).

Rather than consuming the single bucketing scalar $\mathrm{nlp_score}(c)$, the priority calculation operates on the raw NLP feature vector and, when available, the LLM score.

`priority/strategy.py` defines three named strategies.

### Aggressive

```math
\begin{aligned}
\mathrm{priority}_{\text{aggressive}}(n,c)
={}&
\lambda_{\text{llm}}\mathrm{llm}(c)
\\
&+
\lambda_{\text{nlp}}
\left(
0.40\mathrm{sim}(c)
+
0.15\mathrm{novelty}(c)
+
0.10\mathrm{coherence}(c)
+
0.05\mathrm{lexical}(c)
\right)
\\
&-
\gamma\mathrm{depth}(n)
\end{aligned}
```

### Balanced

```math
\mathrm{priority}_{\text{balanced}}(n,c)
=
0.5\mathrm{llm}(c)
+
0.5\mathrm{nlp\_blend}(c)
```

### Exploration

```math
\mathrm{priority}_{\text{exploration}}(n,c)
=
0.85\mathrm{nlp\_blend}_{\text{novelty-weighted}}(c)
+
0.15\mathrm{llm}(c)
```

The parameters $\lambda_{\text{nlp}}$ and $\lambda_{\text{llm}}$ are supplied by the caller rather than hard-coded into the strategy function.

In the live pipeline, `PriorityPipeline` always supplies

```math
(\lambda_{\text{nlp}},\lambda_{\text{llm}})
=
(60,40)
```

for LLM-scored candidates, and

```math
(\lambda_{\text{nlp}},\lambda_{\text{llm}})
=
(1,0)
```

for `trusted_no_llm` candidates, thereby disabling the LLM contribution.

The default keyword arguments defined by the individual strategy functions, such as the $0.5/0.5$ weighting in the balanced strategy, are the values exercised when those functions are called directly, for example in unit tests. They are **not** the values used by the live crawl when `PriorityPipeline` explicitly supplies its own parameters.

### Priority Scale

Because the live pipeline uses

```math
(\lambda_{\text{nlp}},\lambda_{\text{llm}})
=
(60,40)
```

rather than normalized weights summing to $1$, priority values naturally fall on an approximate $0$--$100$ scale.

This does not affect correctness. Priority is used only for **relative ordering within the frontier** and is never compared against an absolute threshold.

Consequently, a UI or log value such as `82` should not be interpreted as an $82%$ probability or confidence score. It is simply a ranking key.

---

## 5. Exponential Backoff with Jitter

Retry delay is modeled as (the report gives the same $\Delta t_k$ form in [§2.5 — Resilience Strategies](../report/rapport-english.pdf#page=14)):

```math
\mathrm{delay}(k)
=
\min\left(
\mathrm{delay}_0 2^k,
\mathrm{delay}_{\max}
\right)
+
J,
\qquad
J \sim \mathcal{U}(0,0.2)
```

where:

* $k$ is the consecutive-failure count for the pipeline;
* $\mathrm{delay}_0$ is the initial backoff delay;
* $\mathrm{delay}_{\max}$ is the configured maximum delay;
* $J$ is an independently sampled jitter term.

The failure count is shared across the pipeline's workers rather than maintained independently for each request.

After a successful operation, the delay decreases gradually rather than immediately resetting to $\mathrm{delay}_0$. This prevents a worker that has just escaped a rate-limit window from instantly returning to its maximum request rate.

Jitter is sampled independently for each worker. Its purpose is to prevent workers whose exponential backoff windows happen to align from retrying simultaneously, thereby reducing the risk of a **thundering-herd effect**.

---

## 6. Replay: Checkpoint-Assisted State Reconstruction

Given an event log (the report's formal projection $S_t = \operatorname{project}(S_{t-1}, e_t)$, [§2.7.1 — The Log as a Causal Record](../report/rapport-english.pdf#page=17), is the naive $O(t)$ case below before checkpointing is introduced):

```math
\{e_1,e_2,\ldots,e_n\}
```

and a pure reducer

```math
f:\text{State}\times\text{Event}\rightarrow\text{State}
```

naive replay to event index $t$ requires applying every preceding event:

```math
S_t
=
f\left(
f\left(
\cdots
f(S_0,e_1),
\ldots,
e_{t-1}
\right),
e_t
\right)
```

with time complexity

```math
O(t)
```

CrawlViz stores a checkpoint every $c$ events. In the reference implementation,

```math
c=200
```

Let

```math
\hat{t}
=
\left\lfloor
\frac{t}{c}
\right\rfloor c
```

be the nearest checkpoint index at or before $t$.

Replay can then begin from the stored state $S_{\hat{t}}$:

```math
S_t
=
f\left(
f\left(
\cdots
f(S_{\hat{t}},e_{\hat{t}+1}),
\ldots,
e_{t-1}
\right),
e_t
\right)
```

The amount of work becomes

```math
O(t\bmod c)
```

with a worst-case replay cost of

```math
O(c)
```

The trade-off is additional storage of approximately

```math
O(n/c)
```

checkpoint states.

This design is particularly appropriate for a scrubbable timeline UI, where bounded seek latency is more important than minimizing the memory required to store checkpoints for a single crawl session.

---

## Complexity Notes

### Per-Link Semantic Scoring

Per-link NLP scoring requires cached embedding lookups and comparison of the candidate embedding against every basis vector:

```math
O\left(|\mathcal{B}|\right)
```

per candidate.

The cost therefore grows linearly with the basis size. However, the basis is bounded by the number of LLM-generated conceptual expansions rather than by the number of graph nodes or discovered links.

### LLM Evaluation Cost

The cascade is specifically designed to ensure that the expensive LLM operation scales with a controlled **evaluation budget per visited node**, rather than with the total number of discovered links.

In the reference run:

```math
50{,}828\ \text{links discovered}
\qquad\text{vs.}\qquad
539\ \text{nodes explored}
```

The ratio between these quantities illustrates why evaluating every discovered link with an LLM would be impractical.

The cascade limits LLM evaluation through thresholding, selective sampling, top-$K$ confirmation, and `trusted_no_llm` bypasses. Consequently, LLM cost is intended to remain approximately proportional to the number of nodes actually explored rather than to the number of links discovered.
