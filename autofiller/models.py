"""Shared immutable data models used across pipeline, I/O, and API layers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CardRow:
    """Normalized vocabulary card row for TSV export and Anki note creation.

    Attributes:
        word: Source vocabulary word.
        meaning: Selected dictionary meaning text.
        reading: Reading text, optionally enriched with pitch HTML.
    """

    word: str
    meaning: str
    reading: str


@dataclass(frozen=True)
class SearchCandidate:
    """Dictionary candidate extracted from Jisho JSON results.

    Attributes:
        meaning: Candidate meaning text.
        reading: Candidate reading text.
    """

    meaning: str
    reading: str


@dataclass(frozen=True)
class ExampleSentence:
    """Example sentence pair from Jisho sentence pages.

    Attributes:
        japanese: Japanese sentence text.
        english: English translation text.
    """

    japanese: str
    english: str


@dataclass(frozen=True)
class SentenceCardRow:
    """Companion sentence card row for separate sentence note generation.

    Attributes:
        front: Sentence text for the front side.
        back: Translation/context content for the back side.
    """

    front: str
    back: str
