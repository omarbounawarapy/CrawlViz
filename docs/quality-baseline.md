# Quality baseline

What the project measured before Phase B, so later phases can show whether they made things
better or worse. Every figure says when and how it was taken. A blank row has not been
measured yet; fill it in with the command shown, never with an estimate.

Taken on 2026-10-29 at the end of Phase A, on a Fedora laptop (CPU torch 2.15.0, Node 24).

## Bundle size

`cd crawler-ui && npm run build` (Vite 8).

| File | Size | Gzip |
|---|---|---|
| `dist/assets/index-*.js` | 546.78 kB | 170.54 kB |
| `dist/assets/index-*.css` | 16.54 kB | 4.63 kB |
| `dist/index.html` | 1.83 kB | 0.87 kB |

Vite warns that the JS chunk is over 500 kB. PERF-1 asks for a bundle budget; set it in
Phase F, starting from these numbers.

## Tests

| Suite | Command | Tests | Time |
|---|---|---|---|
| Python (pytest, includes pins and hook tests) | `uv run pytest -q` | 665 | 187 s |
| Behaviour pins only | `uv run pytest -q -m pins` | 78 | 31 s |
| UI (vitest) | `cd crawler-ui && npm run test` | 242 | 21 s |

## Accessibility (axe)

`crawler-ui/src/a11y.test.jsx` runs axe under jsdom on the landing page, the loader, each route and the not-found page, and passes,
so those pages have no axe violations in jsdom. A browser run on the live app is not
done yet.

jsx-a11y reports 10 open findings in 7 files. They are listed in `crawler-ui/eslint.config.js`
and may only shrink.

## Static checks

| Check | State |
|---|---|
| ruff, `ruff format` | clean; remaining per-file ignores are in `pyproject.toml` |
| mypy strict | clean; the legacy module list in `pyproject.toml` may only shrink |
| ESLint, Stylelint, html-validate, Prettier, tsc | clean |
| pip-audit, npm audit (high) | clean; `npm audit` still lists 2 moderate advisories |

## Not measured yet

| Figure | How to take it |
|---|---|
| LCP, CLS, INP with an empty graph | Chrome performance trace of the sample replay on `make dev` |
| LCP, CLS, INP with 3000 nodes | The same with the 3000-node replay fixture |
| axe on the running app, both themes | axe-core against `make dev` in a browser |
| RSS and event-loop lag for a 5000-page crawl | `CRAWLVIZ_OFFLINE=1` crawl of a 10000-page synthetic site, sampling `ru_maxrss` and the loop's wake-up delay |

The last row has no tool yet; a first draft hung and is not in the repository.
