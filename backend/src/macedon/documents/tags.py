"""Tag normalization: tags are compared as written, so they are stored in one canonical form."""

import re

MAX_TAGS = 20
MAX_TAG_LENGTH = 40


class InvalidTagError(ValueError):
    """A tag is too long, or there are too many."""


def normalize_tags(tags: list[str] | None) -> list[str]:
    """Lowercase, trim, join inner spaces with '-', drop blanks and duplicates (order kept)."""
    seen: dict[str, None] = {}
    for tag in tags or []:
        cleaned = re.sub(r"\s+", "-", tag.strip().lower())
        if not cleaned:
            continue
        if len(cleaned) > MAX_TAG_LENGTH:
            raise InvalidTagError(f"a tag can have at most {MAX_TAG_LENGTH} characters")
        seen.setdefault(cleaned, None)
    if len(seen) > MAX_TAGS:
        raise InvalidTagError(f"a document can have at most {MAX_TAGS} tags")
    return list(seen)
