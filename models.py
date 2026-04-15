from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CardRow:
    word: str
    meaning: str
    reading: str


@dataclass(frozen=True)
class SearchCandidate:
    meaning: str
    reading: str


@dataclass(frozen=True)
class ExampleSentence:
    japanese: str
    english: str


@dataclass(frozen=True)
class SentenceCardRow:
    front: str
    back: str
