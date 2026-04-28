"""Auto-tagging and topic classification service."""

from __future__ import annotations

import re


def normalize_tags(tags: list[str], max_tags: int = 5) -> list[str]:
    """Normalize tags: lowercase, deduplicate, limit count."""
    seen = set()
    normalized = []
    for tag in tags:
        if len(normalized) >= max_tags:
            break
        tag = tag.lower().strip()
        tag = re.sub(r"[^\w\s-]", "", tag)
        tag = re.sub(r"\s+", "-", tag)
        if tag and tag not in seen:
            seen.add(tag)
            normalized.append(tag)
    return normalized
