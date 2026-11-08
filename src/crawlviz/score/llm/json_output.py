"""Reading a model's JSON reply: one parser, pydantic validation, at most one repair.

`parse_llm_json` is the only place a reply is turned into a JSON object. It
accepts the shapes models actually send: bare JSON, JSON in a markdown fence,
and JSON with a sentence before or after it. `validate_llm_output` then checks
the object against the caller's pydantic model and, only when repair is turned
on, gives the model one chance to answer again.
"""

import json
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

# A reply longer than this is refused before any parsing.
MAX_REPLY_CHARS = 200_000
# Validation errors quoted back to the model in a repair request.
MAX_REPAIR_ERRORS = 10

_FENCE = re.compile(r"^```[a-zA-Z]*\s*\n?(?P<body>.*?)\n?\s*```$", re.DOTALL)

# Called with the rejected reply and why it was rejected; returns the new reply.
RepairCall = Callable[[str, str], Awaitable[str]]


class LlmOutputError(ValueError):
    """A reply that is not the JSON object the caller asked for.

    The message says what was wrong, never the reply itself: the reply can
    echo page text, which does not belong in logs.
    """


@dataclass(frozen=True)
class ValidatedOutput[ModelT: BaseModel]:
    """A reply that passed validation.

    Attributes:
        value: The validated object.
        repaired: True when the first reply failed and the repair answer passed.
        reply: The reply that passed: the repair answer when `repaired`.
    """

    value: ModelT
    repaired: bool
    reply: str


def parse_llm_json(reply: str) -> dict[str, object]:
    """The JSON object in `reply`.

    Raises:
        LlmOutputError: If the reply is too long, holds no JSON object, or
            holds JSON that is not an object.
    """
    if len(reply) > MAX_REPLY_CHARS:
        raise LlmOutputError(f"reply is {len(reply)} characters, over {MAX_REPLY_CHARS}")
    text = _strip_fence(reply.strip())
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = _decode_embedded_object(text)
    if not isinstance(data, dict):
        raise LlmOutputError(f"reply is a JSON {type(data).__name__}, not an object")
    return data


def _strip_fence(text: str) -> str:
    match = _FENCE.match(text)
    return match.group("body").strip() if match else text


def _decode_embedded_object(text: str) -> object:
    """The JSON value from the first `{` to the last `}`, for replies with prose around it."""
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise LlmOutputError("reply holds no JSON object")
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError as error:
        raise LlmOutputError(f"reply is not valid JSON: {error.msg} at {error.pos}") from error


def parse_and_validate[ModelT: BaseModel](reply: str, schema: type[ModelT]) -> ModelT:
    """`reply` parsed and validated against `schema`.

    Raises:
        LlmOutputError: If it does not parse or does not validate. The message
            lists the failing fields and why, without their values.
    """
    data = parse_llm_json(reply)
    try:
        return schema.model_validate(data)
    except ValidationError as error:
        raise LlmOutputError(describe_validation_error(error)) from error


def describe_validation_error(error: ValidationError) -> str:
    """The failing fields and reasons, without the input values."""
    problems = [
        f"{'.'.join(str(part) for part in detail['loc']) or '(root)'}: {detail['msg']}"
        for detail in error.errors(include_input=False, include_url=False)
    ]
    shown = problems[:MAX_REPAIR_ERRORS]
    if len(problems) > len(shown):
        shown.append(f"and {len(problems) - len(shown)} more")
    return "; ".join(shown)


async def validate_llm_output[ModelT: BaseModel](
    reply: str,
    schema: type[ModelT],
    *,
    repair: RepairCall | None = None,
    repair_enabled: bool = False,
) -> ValidatedOutput[ModelT]:
    """Validate `reply` against `schema`, with at most one repair attempt.

    Repair is off unless `repair_enabled` is set and a `repair` call is given:
    it costs one more LLM call, and a repaired answer can differ from what the
    model would have scored first, so turning it on is a method decision.

    Raises:
        LlmOutputError: If the reply fails and repair is off, or the repair
            answer fails too.
    """
    try:
        return ValidatedOutput(parse_and_validate(reply, schema), repaired=False, reply=reply)
    except LlmOutputError as first_error:
        if not repair_enabled or repair is None:
            raise
        logger.info("LLM reply failed validation (%s); asking once for a repair", first_error)
        repaired_reply = await repair(reply, str(first_error))
    try:
        value = parse_and_validate(repaired_reply, schema)
    except LlmOutputError as second_error:
        raise LlmOutputError(f"repair answer failed too: {second_error}") from second_error
    return ValidatedOutput(value, repaired=True, reply=repaired_reply)
