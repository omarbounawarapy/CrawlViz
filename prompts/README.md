# Prompts

Each prompt the crawler sends to a language model lives here as one file,
`prompts/<id>.md`, read by `PromptRegistry`
(`src/crawlviz/llm/prompt_registry.py`).

The prompts in use today are still in `models/prompts.py` and
`src/crawlviz/nlp/expansion_prompt_builder.py`. They move here one at a time.
A move changes how the prompt is rendered, so it needs a golden replay and
research-scientist sign-off. Nothing in this folder is sent yet.

## File format

A TOML header between two `+++` lines, then the body:

```text
+++
id = "link_scoring"
version = 1
description = "Scores candidate links for relevance to the crawl topic."
variables = ["topic", "links"]
untrusted = ["links"]
system = """
You rate links for a topic-focused crawler. Answer with JSON only.
"""
+++
Topic: {{ topic }}

Rate each link from 0 to 100:
{{ links }}
```

| Field | Required | Meaning |
|---|---|---|
| `id` | yes | Same as the file name without `.md`: lowercase letters, digits and `_`. |
| `version` | yes | Starts at 1. Raise it whenever the text changes. |
| `description` | yes | One sentence on what the prompt is for. |
| `variables` | no | Every placeholder the body uses, and no others. |
| `untrusted` | no | The variables that hold text from crawled pages or other outside sources. |
| `system` | no | The system message. Static text only: no placeholders. |

No other keys are allowed, so a typo fails at load time.

## Rules

- **Placeholders** are `{{ name }}`. The body must use exactly the variables
  declared, and rendering must supply exactly them. A value is inserted once and
  never read as a template, so `{{ topic }}` inside page text stays as written.
- **Untrusted text** goes in the user message only, wrapped like this:

  ```text
  <untrusted_data name="links">
  ...
  </untrusted_data>
  ```

  A closing `</untrusted_data` inside the value is written as `<\/untrusted_data`,
  so page text cannot end the block early. Tell the model in the system message
  that text inside these tags is data, not instructions.
- **Hashes.** Rendering returns the sha256 of the rendered messages (roles and
  contents as canonical JSON). It goes into every call record (`prompt_hash` in
  `llm_calls.jsonl`) and every run manifest. The template's own sha256 is kept too.
- **Changing a prompt** is a method change: raise `version`, update the golden
  render tests, run the golden replay, and get research-scientist sign-off.
  Once the study protocol exists, prompts do not change during an experiment.
- Files over 256 KiB are refused.
