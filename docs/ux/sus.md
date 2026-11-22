# SUS session script

A script for Omar to run the System Usability Scale (Brooke, 1996) with himself and with
real testers. Agents do not fill this in: an agent walkthrough is not a satisfaction score
(ISO 9241-11 counts satisfaction as the user's own response). Results go into a new entry
in `docs/usability-log.md`.

## When

- Baseline: once, before Phase C changes reach the UI. Entry 0 in the log has no SUS score
  yet; the first scored session becomes its follow-up entry.
- Again at the end of Phase F, and at Phase H (summative evaluation).
- Use the same tasks, the same blueprint and the same mode each time, or the scores are
  not comparable.

## Setup (10 minutes)

1. `CRAWLVIZ_OFFLINE=1 make dev`. If other agents are editing worktrees, run the API
   without `--reload` (see the usability log, entry 0, environment note), or the server
   restarts mid-session.
2. Open `http://localhost:5173/` in a fresh browser profile, window at least 1366 px wide.
3. Stored settings at the defaults (Config page, Reset all), no extra blueprints.
4. Have a timer and this sheet. Note the tester's group: U1 crawl researcher, U2 score
   reviewer, U3 developer, U4 demo visitor (`PRODUCT.md`, Context of use).

## Briefing (read aloud)

> "We are testing the tool, not you. Please think aloud: say what you are looking for and
> what you expect to happen. I will not help unless you are stuck for two minutes. You can
> stop at any time."

## Tasks

Read each task card aloud, then start the timer. Stop it when the tester says they are done
or gives up. Record: success (yes, with help, no), time, and what they said.

| # | Task card | Success means |
|---|---|---|
| 1 | "Start a crawl about the ISI institute using the offline demo blueprint." | The graph shows pages from `offline_demo.json` |
| 2 | "While it runs, tell me whether the crawl is healthy and how many pages it has actually fetched." | Says a fetched count (not the found count) and a health judgement |
| 3 | "Pick a page the crawler rated highly. Tell me why it got that score." | Gives a reason grounded in what the UI shows |
| 4 | "Find a link the crawler decided not to follow, and tell me why." | Points at a skipped link and a reason |
| 5 | "Go back to the moment the crawl had found about 100 pages." | Uses the timeline to reach that point |
| 6 | "Make the crawler wait longer between requests, for future crawls." | Saves a higher minimum delay |
| 7 | "Get the extracted pages out of the tool so you could open them in a spreadsheet." | Finds an export, or says where the data is (today there is no UI export) |
| 8 | "On the Benchmark page, tell me what the arms are and whether any results exist." | Names at least two arms and says there are no valid runs |

Tasks 4 and 7 are expected to fail today; keep them so later sessions show the change.
Live change (core task T5), local LLM (T6) and run comparison (T4 compare) are added once
the requirements behind them land; until then the session would only measure their absence.

## Questionnaire

After the tasks, hand over the ten statements. Answer each on a scale of 1 (strongly
disagree) to 5 (strongly agree). Ask for a first impression, not long thought, and an answer
to every item (3 if unsure).

1. I think that I would like to use this system frequently.
2. I found the system unnecessarily complex.
3. I thought the system was easy to use.
4. I think that I would need the support of a technical person to be able to use this system.
5. I found the various functions in this system were well integrated.
6. I thought there was too much inconsistency in this system.
7. I would imagine that most people would learn to use this system very quickly.
8. I found the system very cumbersome to use.
9. I felt very confident using the system.
10. I needed to learn a lot of things before I could get going with this system.

"System" means CrawlViz as used today.

## Scoring

- Odd items (1, 3, 5, 7, 9): score minus 1.
- Even items (2, 4, 6, 8, 10): 5 minus score.
- Sum the ten values and multiply by 2.5. The result is 0 to 100.
- Rough reading (Bangor, Kortum and Miller, 2009): about 68 is average; under 50 is poor;
  over 80 is good. Report the number, not only the label.
- With fewer than five testers, report each score and the median; do not report a mean
  with a confidence interval.

## Debrief (5 minutes)

- "What was the hardest part?"
- "Was there a word you did not understand?" Note each term; it feeds `docs/glossary.md`.
- "What did you expect to find and did not?"

## Recording sheet

```
Date:            Tester group (U1-U4):     Tester id (no names):
Build (git rev): Mode: offline / live      Window width:

Task  Success (y / help / n)  Time (s)  Notes
1
2
3
4
5
6
7
8

SUS answers 1-10:  _ _ _ _ _ _ _ _ _ _     SUS score: ___
Terms not understood:
Expected but missing:
```

Copy the sheet into the new log entry. Do not record names or anything that identifies a
tester.
