"""Shared helpers for event ingestion."""
import re


def normalize_title(title: str) -> str:
    """Lowercase, strip parenthetical suffixes, collapse whitespace.

    Used to dedupe events that describe the same real-world occurrence
    but come from different sources with slightly different phrasing.
    """
    if not title:
        return ""
    t = title.lower()
    t = re.sub(r"\([^)]*\)", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t
