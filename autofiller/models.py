from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CardRow:
    """Normalized vocabulary card row for TSV export and Anki note creation."""

    word: str
    meaning: str
    reading: str


@dataclass(frozen=True)
class SearchCandidate:
    """Dictionary candidate extracted from Jisho JSON results."""

    meaning: str
    reading: str


@dataclass(frozen=True)
class ExampleSentence:
    """Example sentence pair from Jisho sentence pages."""

    japanese: str
    english: str


@dataclass(frozen=True)
class SentenceCardRow:
    """Companion sentence card row for separate sentence note generation."""

    front: str
    back: str
