"""
Source verification: checks that each sentence of an answer is supported by the cited PDF text.

Method (no extra Gemini call): for every sentence, the share of its meaningful words that also
appear in the cited excerpts. A high share means the sentence is supported.

This is a word-overlap check. It catches invented facts that share no vocabulary with the PDF,
but it cannot prove that a paraphrase is correct. The app says so in its wording.

Verdicts
- supported:   every checked sentence is supported.
- partial:     some sentences are not supported. The answer is shown with a warning.
- unsupported: no sentence is supported. The answer is replaced by "couldn't find" wording.
- not_checked: nothing long enough to check (for example "Yes."). Nothing is changed.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from app.core.config import get_settings
from app.services.text_tokens import content_tokens

MIN_WORDS_TO_CHECK = 4
GENERAL_PREFIX = "general knowledge"
_BULLET = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+")


@dataclass
class SentenceCheck:
    text: str
    supported: bool | None   # None = not checked (general knowledge or too short)
    overlap: float           # share of the sentence's meaningful words found in the cited text


@dataclass
class Verification:
    verdict: str = "not_checked"
    checked: int = 0
    supported: int = 0
    unsupported: int = 0
    sentences: list[SentenceCheck] = field(default_factory=list)

    def summary(self) -> dict:
        """Small dictionary for responses (without the sentence list)."""
        data = asdict(self)
        data.pop("sentences")
        return data


def split_sentences(answer: str) -> list[str]:
    pieces: list[str] = []
    for line in (answer or "").splitlines():
        line = _BULLET.sub("", line).strip()
        if not line:
            continue
        pieces.extend(part.strip() for part in re.split(r"(?<=[.!?])\s+", line) if part.strip())
    return pieces


def verify_answer(answer: str, cited_texts: list[str]) -> Verification:
    threshold = get_settings().verification_threshold
    corpus = set(content_tokens(" ".join(cited_texts)))
    result = Verification()
    for sentence in split_sentences(answer):
        if sentence.lower().startswith(GENERAL_PREFIX):
            result.sentences.append(SentenceCheck(text=sentence, supported=None, overlap=0.0))
            continue
        words = set(content_tokens(sentence))
        if len(words) < MIN_WORDS_TO_CHECK:
            result.sentences.append(SentenceCheck(text=sentence, supported=None, overlap=0.0))
            continue
        overlap = round(len(words & corpus) / len(words), 3)
        supported = overlap >= threshold
        result.sentences.append(SentenceCheck(text=sentence, supported=supported, overlap=overlap))
        result.checked += 1
        result.supported += int(supported)
        result.unsupported += int(not supported)

    if result.checked == 0:
        result.verdict = "not_checked"
    elif result.supported == 0:
        result.verdict = "unsupported"
    elif result.unsupported > 0:
        result.verdict = "partial"
    else:
        result.verdict = "supported"
    return result
