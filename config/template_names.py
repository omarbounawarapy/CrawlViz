"""Blueprint file names: one rule for the templates routes, POST /run and the crawler.

A name reaches the filesystem (``templates/<name>``) and, through the crawl id,
the log, debug and export directories. Only a plain file name in the templates
directory is accepted, so a name can never point somewhere else.
"""

import re
from pathlib import Path

TEMPLATE_SUFFIX = ".json"
MAX_TEMPLATE_NAME_LENGTH = 100
# Starts with a letter, digit, underscore or hyphen (never a dot or a space), then
# letters, digits, spaces, dots, underscores and hyphens, ending in .json.
_TEMPLATE_NAME = re.compile(r"[A-Za-z0-9_-][A-Za-z0-9 ._-]*\.json")
_UNSAFE_ID_CHARACTERS = re.compile(r"[^A-Za-z0-9_-]")


class InvalidTemplateNameError(ValueError):
    """The name is not a plain ``.json`` file name."""


def validate_template_name(name: str) -> str:
    """Return ``name`` if it is a plain blueprint file name, else raise the error."""
    if len(name) > MAX_TEMPLATE_NAME_LENGTH or _TEMPLATE_NAME.fullmatch(name) is None:
        raise InvalidTemplateNameError(
            f"Blueprint file name {name!r} is not allowed: use letters, digits, spaces, "
            f"dots, hyphens and underscores, end with {TEMPLATE_SUFFIX}, at most "
            f"{MAX_TEMPLATE_NAME_LENGTH} characters, and no folders."
        )
    return name


def resolve_template_path(templates_dir: str | Path, name: str) -> Path:
    """The file ``name`` in ``templates_dir``; raises InvalidTemplateNameError for anything else."""
    return Path(templates_dir) / validate_template_name(name)


def template_stem(name: str) -> str:
    """The part of a validated name before its first dot, made safe for a crawl id."""
    return _UNSAFE_ID_CHARACTERS.sub("_", validate_template_name(name).split(".", 1)[0])
