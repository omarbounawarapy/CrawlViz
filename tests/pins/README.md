# Behaviour pins

Pins record what a crawl does today so a later refactor can prove it changed
nothing it did not mean to. Each pin runs a full cascade crawl offline and
compares four things with golden files.

| Pin | Graph | Pages | Golden files |
|---|---|---|---|
| `isi` | `benchmark/data/isi.json` (frozen) | 50 | `golden/isi/` |
| `synthetic` | 200 pages generated in `synthetic_site.py` from a fixed seed | 60 | `golden/synthetic/` |

Per pin, one JSON-lines file each:

- `fetch_order.jsonl`: the pages in the order they were fetched.
- `link_scores.jsonl`: every link's NLP score, LLM score and priority as decided, and the links the cascade dropped or trusted without the LLM.
- `llm_requests.jsonl`: the prompt of every LLM call, in order.
- `wire_messages.jsonl`: every message the UI bridge broadcast (types in `docs/crawl_messages.ts`).

No network, keys or embedding model are used: `FrozenGraph` serves the pages,
`HashingEmbeddingEngine` embeds, and a scripted LLM answers behind `CachedLlm`.
Timestamps, durations and worker ids are replaced by `<volatile>`, floats are
rounded to 6 places, and recording stops when the last page of the budget is
requested (what follows races with the stop). See `golden_files.py` and
`pin_observer.py`.

## Run

From the repository root:

```
uv run pytest -q tests/pins
uv run pytest -q -m pins
```

`pytest.ini` puts the repository root on the import path (`pythonpath = .`), so the
same commands work in the main checkout and in a git worktree. A pin takes a few seconds. A mismatch
fails with a unified diff of the changed golden lines, for example
`fetch_order.jsonl changed (50 golden lines, 50 now)` followed by the `-` and `+` lines.

## Update

Goldens are rewritten only with `--update-pins`; without it nothing is written
and a missing file fails.

```
uv run pytest -q tests/pins --update-pins
```

The run ends with a list of the golden files it rewrote, for example
`isi/wire_messages.jsonl`; review each with `git diff`.

An update needs, in this order:

1. the cause found: which commit changed the behaviour, and is that intended;
2. a CHANGE-REQUEST to test-engineer naming that commit and the reason;
3. research-scientist sign-off when scores, ordering or prompts changed;
4. the golden changes in their own commit, never mixed with the behaviour change.

Never update a golden to make a failure go away.

## Determinism

The same commit must give byte-identical goldens. Checked by running the pins
repeatedly, under `PYTHONHASHSEED` 1 to 4, and four at a time in parallel: all
green. After an update, run `uv run pytest -q tests/pins` once more without the flag.

## Module names

`tests/pins` has no `__init__.py`, so pytest puts the folder on `sys.path` and its
modules import each other by bare name; mypy does the same through `mypy_path` in
`pyproject.toml`. A module here must therefore never share a name with a top-level
package or module of the repository (`config`, `models`, `core`, ...) or with the
standard library, or it would shadow the real one. `test_module_names.py` fails when
one does.
