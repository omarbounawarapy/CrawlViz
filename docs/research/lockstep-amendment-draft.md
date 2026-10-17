# Draft amendment: lockstep frontier pop

Status: draft for Omar's approval. Nothing below is in `benchmark/PROTOCOL.md`
until he approves it; once approved it is appended there word for word,
under Amendments.

## Text to append to PROTOCOL.md

**2026-10-17, lockstep frontier pop, before the rerun.** A review of the
behaviour pins found that the quiet frontier pop (`_QuietQueue`, section 7a)
did not wait for the previous page to be scored. Once `StoragePipeline`
marked a fetched node ready, the gate still counted the scoring worker as
parked until the worker resumed. In that gap the crawler looked quiet, so
the next page was taken from the frontier before the previous page's links
were scored and their child nodes added: the choice was made on a frontier
one page out of date. Measured offline (`isi.json`, budget 50, hashing
embeddings, a scripted LLM), this happened at 49 of 51 frontier pops for the
cascade, `bfs` and `anchor_lexical`. It was deterministic, which is why every
replay matched, and every arm had it. But it is not the order section 7a
describes, and one more event subscriber was enough to change the visit
order: the cascade on `isi.json` diverged at fetch 9.

The gate now counts the worker as parked only while the node it waits for is
not ready (`_ParkingScoring.parked` in `benchmark/runner.py`). The next page
is chosen only after the previous page's links are scored and admitted, and
an added observer no longer changes the run (tests in `tests/test_benchmark.py`).
The page sequence of best-first arms changes. `bfs` on `isi.json` at budget
50 does not. No prompt, cache key, model, threshold, metric or statistic
changes.

Consequences:

- The results frozen on 2026-10-16 were recorded with the old gate. They
  stay as recorded and are reported as produced by it. They do not replay on
  the new commit: a different page order asks different prompts.
- The rerun (re-recorded graph, all arms) uses the new gate.
- The same commit adds `extra_components` to `run_policy` and `run_cascade`
  for observers. Its default is empty, which leaves the wiring as before.
  Under section 7 this commit changes `benchmark/`, so the code under test
  for the rerun is this commit or a later one.

## Sentence for the paper's threats to validity

The results reported for the 2026-10-16 runs come from a lockstep harness
that, at almost every step, chose the next page before the previous page's
links had been scored, so every policy ranked a frontier one page out of
date. The rerun corrects this; until then, read the frozen numbers as
measuring that one-page delay for all arms alike.

## Not measured

- The 49-of-51 rate is from offline runs with hashing embeddings and a
  scripted LLM. The mechanism does not depend on the embedding model or the
  LLM, because the gap lies between a node becoming ready and its scoring
  starting. The rate on the frozen runs with the real model has not been
  measured.
- How much the delay changed the frozen harvest numbers has not been
  measured. That needs the rerun.
