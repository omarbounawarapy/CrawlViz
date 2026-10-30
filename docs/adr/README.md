# Architecture decision records

One file per decision, `NNNN-title.md`, written by the architect. Format: Context (with
evidence), Decision, Alternatives considered, Consequences, Standards affected, Migration and
commit plan. An accepted ADR is not rewritten; a later ADR supersedes it.

| ADR | Decision | Status |
|---|---|---|
| [1](0001-folder-layout.md) | Code is grouped by domain in `src/crawlviz/` and by feature in `crawler-ui/src/features/` (cited by ARCH-1) | proposed |
| [2](0002-crawl-composition-root.md) | The crawl composition root is a stage registry and self-describing consumers | accepted |
| [3](0003-nlp-service-split.md) | NLPService keeps its interface and hands bootstrap and link features to two helpers | accepted |
| [4](0004-dependency-direction.md) | Backend layers import downwards only, and import-linter enforces the order | proposed |
| [5](0005-versioned-contracts.md) | Stored files and wire messages carry a version, migrate on read, and generate their types | proposed |
| [6](0006-pipeline-naming.md) | Every pipeline part has one name and one snake_case key, from class to UI label | proposed |
| [7](0007-split-large-modules.md) | Each setting has one definition in its domain, and the large backend modules split by responsibility | proposed |
| [8](0008-subsystem-status.md) | One status board per crawl feeds `/status` and `SUBSYSTEM_STATUS`, and the gateway starts first | proposed |
| [9](0009-ui-runtime-config.md) | The UI reads its runtime settings and the run mode from one `/ui-config` endpoint | proposed |
| [10](0010-frontend-architecture.md) | UI features own their containers, components and model; one crawl session store serves live and replay | proposed |
| [11](0011-i18n-and-formatting.md) | Numbers and dates go through `format.ts`, copy lives in typed per-feature catalogs, and the backend sends codes | proposed |
| [12](0012-api-surface.md) | API v2 is a thin HTTP layer over domain services, with one error envelope and only the resources the ranked requirements need | proposed |
