"""Prompts as versioned files: `prompts/<id>.md`, TOML front matter, a templated body.

The file format is described in `prompts/README.md`. Rendering returns the
messages and the sha256 of exactly what is sent, which every manifest and call
record carries (LLM-2, REPRO-1).

Untrusted text (page content, link text, anything a crawled site wrote) is
only ever placed in the user message, inside `<untrusted_data>` delimiters,
and is never re-read as a template (SEC-2). The system message is static
text from the front matter and cannot hold placeholders.
"""

import hashlib
import json
import re
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .types import ChatRole, LlmMessage, LlmRequest

FRONT_MATTER_FENCE = "+++"
MAX_PROMPT_FILE_BYTES = 256 * 1024
PROMPT_ID_PATTERN = re.compile(r"[a-z][a-z0-9_]{0,63}")
PLACEHOLDER = re.compile(r"\{\{\s*([a-z][a-z0-9_]*)\s*\}\}")
UNTRUSTED_TAG = "untrusted_data"
_UNTRUSTED_CLOSE = re.compile(rf"</\s*({UNTRUSTED_TAG})", re.IGNORECASE)


class PromptFileError(ValueError):
    """A prompt file that cannot be used; the message names the file and the fix."""


class PromptFrontMatter(BaseModel):
    """The TOML header of a prompt file."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    version: int = Field(ge=1)
    description: str = Field(min_length=1)
    variables: tuple[str, ...] = ()
    untrusted: tuple[str, ...] = ()
    system: str | None = None

    @model_validator(mode="after")
    def _check_variables(self) -> Self:
        unknown = set(self.untrusted) - set(self.variables)
        if unknown:
            raise ValueError(f"untrusted names undeclared variables: {sorted(unknown)}")
        if self.system is not None and PLACEHOLDER.search(self.system):
            raise ValueError("system must be static text: page data never goes in the system role")
        return self


class PromptTemplate(BaseModel):
    """A loaded prompt file: its header, body and the sha256 of the file bytes."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    front_matter: PromptFrontMatter
    body: str
    template_sha256: str


class RenderedPrompt(BaseModel):
    """Messages ready to send and the hash that identifies them.

    `sha256` is over the messages as canonical JSON (roles and contents, in
    order), so two renders hash the same exactly when they send the same text.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    prompt_id: str
    prompt_version: int
    template_sha256: str
    messages: tuple[LlmMessage, ...]
    sha256: str

    def request_for(self, provider: str, model: str) -> LlmRequest:
        """A request carrying these messages, the prompt id and the hash.

        Set temperature, token limit and log context with `model_copy(update=...)`.
        """
        return LlmRequest(
            provider=provider,
            model=model,
            messages=self.messages,
            prompt_id=self.prompt_id,
            prompt_hash=self.sha256,
        )


def parse_prompt_file(text: str, source: str) -> PromptTemplate:
    """Parse one prompt file's text; `source` names it in error messages.

    Raises:
        PromptFileError: If the front matter is missing or invalid, or the body's
            placeholders differ from the declared variables.
    """
    header, body = _split_front_matter(text.replace("\r\n", "\n"), source)
    try:
        front_matter = PromptFrontMatter.model_validate(tomllib.loads(header))
    except (tomllib.TOMLDecodeError, ValidationError) as error:
        raise PromptFileError(f"{source}: front matter is invalid: {error}") from error
    used = set(PLACEHOLDER.findall(body))
    declared = set(front_matter.variables)
    if used != declared:
        raise PromptFileError(
            f"{source}: placeholders and declared variables differ; "
            f"undeclared {sorted(used - declared)}, unused {sorted(declared - used)}"
        )
    return PromptTemplate(
        front_matter=front_matter,
        body=body,
        template_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
    )


def _split_front_matter(text: str, source: str) -> tuple[str, str]:
    opening = FRONT_MATTER_FENCE + "\n"
    closing = "\n" + FRONT_MATTER_FENCE + "\n"
    end = text.find(closing, len(opening) - 1)
    if not text.startswith(opening) or end < 0:
        raise PromptFileError(
            f"{source}: no front matter; start the file with a line '{FRONT_MATTER_FENCE}', "
            f"the TOML header, then another '{FRONT_MATTER_FENCE}' line"
        )
    return text[len(opening) : end + 1], text[end + len(closing) :].strip()


def render_prompt(template: PromptTemplate, variables: Mapping[str, str]) -> RenderedPrompt:
    """Fill the body with `variables`, delimiting the untrusted ones.

    Each placeholder is replaced in one pass, so text inside a value is never
    expanded as a placeholder.

    Raises:
        ValueError: If `variables` does not name exactly the declared variables.
    """
    front_matter = template.front_matter
    declared = set(front_matter.variables)
    if set(variables) != declared:
        raise ValueError(
            f"prompt {front_matter.id!r} takes {sorted(declared)}, got {sorted(variables)}"
        )
    untrusted = set(front_matter.untrusted)

    def fill(match: re.Match[str]) -> str:
        name = match.group(1)
        value = variables[name]
        return delimit_untrusted(name, value) if name in untrusted else value

    user = LlmMessage(role=ChatRole.USER, content=PLACEHOLDER.sub(fill, template.body))
    messages: tuple[LlmMessage, ...] = (
        (LlmMessage(role=ChatRole.SYSTEM, content=front_matter.system), user)
        if front_matter.system
        else (user,)
    )
    return RenderedPrompt(
        prompt_id=front_matter.id,
        prompt_version=front_matter.version,
        template_sha256=template.template_sha256,
        messages=messages,
        sha256=hash_messages(messages),
    )


def delimit_untrusted(name: str, value: str) -> str:
    """`value` inside `<untrusted_data>` tags it cannot close itself."""
    escaped = _UNTRUSTED_CLOSE.sub(r"<\\/\1", value)
    return f'<{UNTRUSTED_TAG} name="{name}">\n{escaped}\n</{UNTRUSTED_TAG}>'


def hash_messages(messages: tuple[LlmMessage, ...]) -> str:
    """sha256 of the messages as canonical JSON; the rendered-prompt hash."""
    canonical = json.dumps(
        [{"role": str(message.role), "content": message.content} for message in messages],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class PromptRegistry:
    """Loads prompt files from one directory, once each, and renders them.

    Loading reads the disk; load the prompts a crawl needs before it starts,
    not from a scoring worker.
    """

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self._templates: dict[str, PromptTemplate] = {}

    def load_template(self, prompt_id: str) -> PromptTemplate:
        """The template for `prompt_id`, read from disk on first use.

        Raises:
            PromptFileError: If the id is not a plain name, the file is missing,
                too large or invalid, or its front matter names another id.
        """
        cached = self._templates.get(prompt_id)
        if cached is not None:
            return cached
        if not PROMPT_ID_PATTERN.fullmatch(prompt_id):
            raise PromptFileError(
                f"prompt id {prompt_id!r} is not a lowercase name of letters, digits and _"
            )
        path = self.directory / f"{prompt_id}.md"
        template = parse_prompt_file(_read_prompt_file(path), str(path))
        if template.front_matter.id != prompt_id:
            raise PromptFileError(
                f"{path}: front matter id is {template.front_matter.id!r}; "
                f"it must match the file name, {prompt_id!r}"
            )
        self._templates[prompt_id] = template
        return template

    def render(self, prompt_id: str, variables: Mapping[str, str]) -> RenderedPrompt:
        """Render `prompt_id` with `variables`; see `render_prompt`."""
        return render_prompt(self.load_template(prompt_id), variables)


def _read_prompt_file(path: Path) -> str:
    try:
        size = path.stat().st_size
    except FileNotFoundError as error:
        raise PromptFileError(f"{path}: no such prompt file") from error
    if size > MAX_PROMPT_FILE_BYTES:
        raise PromptFileError(f"{path}: {size} bytes, over the {MAX_PROMPT_FILE_BYTES} limit")
    return path.read_text(encoding="utf-8")
