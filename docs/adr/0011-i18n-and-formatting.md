# ADR 11: Numbers and dates go through `format.ts`, copy lives in typed per-feature catalogs, and the backend sends codes

Status: proposed, 2026-10-30

## Context

- Formatting is spread out. Outside `crawler-ui/src/utils/formatters.js`, the UI has 26
  `toFixed(` calls and 20 `toLocaleString` or `Intl.` calls (grep, tests excluded,
  2026-10-30). Only 6 files import `formatters.js`. The same number can show as "1234" on one
  page and "1,234" on another.
- Copy is written inline in JSX (for example the lead text in
  `features/benchmark/BenchmarkPage.jsx:29`), next to constants such as `DAILY_CAP`
  (`features/benchmark/RunsTab.jsx:29`).
- The backend sends sentences that the UI shows as they are: `detail=str(exc)` in
  `routes/run.py:83` and `:88`, so users see raw exception text with no next step.
- There is one language (`index.html` has `lang="en"`), and no requirement asks for a
  second. No i18n library is installed.
- Showing every score on one scale needs one score formatter. The planned health strip needs
  the backend's subsystem reason codes (ADR 8) turned into sentences with a next step.

## Decision

1. **`shared/lib/format.ts` is the only code that calls `Intl`** or formats a number or date:
   `formatCount`, `formatPercent`, `formatDuration`, `formatTimestamp`, `formatRelativeTime`,
   `formatTokens`, `formatCost` (always labelled as an estimate), `formatScore` and `plural`
   (through `Intl.PluralRules`). Formatter instances are cached per locale. ESLint
   (`no-restricted-syntax`) rejects `toFixed`, `toLocaleString` and `new Intl.*` anywhere else.
2. **Locale.** Numbers and dates follow the browser locale (`navigator.language`, falling back
   to `en`), for example "1,234" in `en` and "1 234" in `fr`. The copy is English
   only. There is no language switcher.
3. **Catalogs.** Each feature has `messages.ts`: a typed object of strings and functions that
   take typed parameters, for example `exportFailed({ reason })`. Plurals go through `plural`.
   Copy shared by several features, such as the API error messages, is in `shared/i18n/`.
   Domain terms come from the project glossary (`docs/glossary.md`).
4. **Backend codes, UI words.** The backend sends a code and parameters, never a sentence for
   the UI. This covers API errors (ADR 12), subsystem reasons (ADR 8), crawl outcomes and skip
   reasons. The UI maps each code through a `Record<Code, Message>` typed
   against the generated enums (ADR 5), so a new backend code that has no message fails
   `tsc`. An unknown code at run time shows a generic message that names the code. The
   backend's English `message` field is for the CLI and the logs.
5. **Scores** are shown only through `formatScore(kind, value)`. It applies the display scale
   that ADR 12 defines and the number format of this ADR.

## Alternatives considered

- **react-intl, i18next or Lingui.** They solve many languages and ICU plurals; there is one
  language, `Intl.PluralRules` covers the plurals, and nothing is built before a requirement
  asks for it. If a second language becomes a requirement, the catalogs are already keyed, and
  an ADR chooses a library then.
- **One global catalog.** Every feature's copy in one file goes against grouping code by
  feature, and the file would become a merge hotspot.
- **Sentences from the backend.** One fewer mapping, but the UI could not keep its voice or
  its next-step wording, and raw exception text would leak into the UI.

## Consequences

- `formatters.js` splits. The formatting functions move into `format.ts`; `eventSummary` is
  copy, so it moves to the timeline catalog; `shortId`, `hostnameOf` and `pathOf` move to
  `shared/lib/url.ts`.
- `format.ts` gets unit tests: each function in `en` and `fr`.
- A copy review reads one `messages.ts` per feature instead of searching JSX.
- A planned command-line tool prints the backend `message`, so its wording is written in the
  backend error table (ADR 12) and checked there: it says what happened and what to do next.

## Standards affected

- All number and date formatting goes through `shared/lib/format.ts`; user-facing strings
  live in per-feature catalogs.
- Every error says what happened and what to do next; no raw errors.
- Domain terms come from the glossary.
- No magic numbers: named constants live in the module that owns them.
- Strict TypeScript with no `any`.
- No logic in two places.
- Only what a requirement asks for is built.

## Migration and commit plan

1. `UI format`: `format.ts` with `en` and `fr` tests; `formatters.js` re-exports its
   formatting functions from it.
2. `UI lint`: the `Intl` and `toFixed` rule, as a warning with a baseline.
3. `UI errors`: `shared/i18n/errors.ts` maps the API error codes once the error envelope exists
   (ADR 12).
4. Per feature, inside its ADR 10 series: copy moves to `messages.ts`, and formatting moves to
   `format.ts`.
5. `UI`: `formatters.js` is deleted, and the rule becomes an error.
