# Architecture decision records

One file per decision, `NNNN-title.md`, written by the architect. Format: Context (with
evidence), Decision, Alternatives considered, Consequences, Standards affected, Migration and
commit plan. An accepted ADR is not rewritten; a later ADR supersedes it.

| ADR | Decision | Status |
|---|---|---|
| 1 | Folder layout by feature and domain (cited by ARCH-1 in `docs/standards.md`) | not written yet |
| [2](0002-crawl-composition-root.md) | The crawl composition root is a stage registry and self-describing consumers | accepted |
| [3](0003-nlp-service-split.md) | NLPService keeps its interface and hands bootstrap and link features to two helpers | accepted |
