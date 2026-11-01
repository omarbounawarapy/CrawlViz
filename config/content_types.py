"""The content types a page fetch accepts, written as a comma-separated setting."""

import re

_MEDIA_TYPE = re.compile(r"^[a-z0-9][a-z0-9!#$&^_.+-]*/[a-z0-9][a-z0-9!#$&^_.+-]*$")


def parse_content_types(text: str) -> tuple[str, ...]:
    """The media types in `text`, lowercased and in order, e.g. ``text/html, text/plain``.

    Raises ValueError, in plain words, for an empty list or an entry that is not ``type/subtype``.
    """
    types = tuple(part.strip().lower() for part in text.split(",") if part.strip())
    if not types:
        raise ValueError("List at least one content type, for example text/html.")
    for media_type in types:
        if not _MEDIA_TYPE.match(media_type):
            raise ValueError(
                f"'{media_type}' is not a content type. Write each one as type/subtype, "
                "for example text/html, separated by commas."
            )
    return types
