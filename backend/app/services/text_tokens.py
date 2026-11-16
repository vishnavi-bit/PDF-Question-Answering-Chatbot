"""
Simple text helpers shared by keyword search, duplicate filtering and source verification.

Tokens keep numbers and technical terms (for example "XR-500", "3.5", "co-op"),
because those are exactly the words keyword search must find.
"""

from __future__ import annotations

import re

STOPWORDS = frozenset(
    """a an and are as at be been but by can could did do does for from had has have how i in
    into is it its of on or our so such than that the their them then there these they this to
    was we were what when where which who why will with would you your about also any each
    may might must shall should only other some more most very just not no yes if""".split()
)

_TOKEN = re.compile(r"[a-z0-9]+(?:[.\-_][a-z0-9]+)*")


def tokenize(text: str) -> list[str]:
    """Lower-case word tokens, keeping numbers and hyphenated or dotted terms."""
    return _TOKEN.findall((text or "").lower())


def content_tokens(text: str) -> list[str]:
    """Tokens without stop words (what a question or sentence is really about)."""
    return [token for token in tokenize(text) if token not in STOPWORDS and len(token) > 1]


def normalized(text: str) -> str:
    """Lower case, single spaces, no punctuation: used to compare chunks."""
    return " ".join(tokenize(text))


def shingles(text: str, size: int = 5) -> set[tuple[str, ...]]:
    """Overlapping groups of `size` words. Two texts with many shared groups are near-duplicates."""
    words = tokenize(text)
    if len(words) < size:
        return {tuple(words)} if words else set()
    return {tuple(words[index : index + size]) for index in range(len(words) - size + 1)}


def jaccard(first: set, second: set) -> float:
    if not first or not second:
        return 0.0
    return len(first & second) / len(first | second)
