from __future__ import annotations

import time
from typing import Callable

from jisho_client import JishoClient
from models import CardRow, ExampleSentence, SearchCandidate, SentenceCardRow
from pitch_accent import enrich_html_with_pitch


def format_sentences(sentences: list[ExampleSentence]) -> str:
    if not sentences:
        return ""
    parts = [f"例文: {s.japanese} - {s.english}" for s in sentences]
    return "<br>".join(parts)


def default_interactive_selector(
    word: str, candidates: list[SearchCandidate]
) -> SearchCandidate:
    print(f"\nReview: {word}")
    for idx, candidate in enumerate(candidates, start=1):
        print(f"  {idx}. reading='{candidate.reading}' meaning='{candidate.meaning}'")
    print("  0. keep blank")

    while True:
        choice = input("Select candidate number (default 1): ").strip()
        if choice == "":
            return candidates[0]
        if choice == "0":
            return SearchCandidate(meaning="", reading="")
        if choice.isdigit():
            numeric = int(choice)
            if 1 <= numeric <= len(candidates):
                return candidates[numeric - 1]
        print("Invalid selection. Enter 0..N.")


def build_rows(
    words: list[str],
    *,
    pause_seconds: float,
    candidate_limit: int,
    sentence_count: int,
    include_sentences: bool,
    separate_sentence_cards: bool,
    include_pitch_accent: bool,
    interactive_review: bool,
    selector: Callable[[str, list[SearchCandidate]], SearchCandidate] | None = None,
    progress_printer: Callable[[str], None] | None = print,
) -> tuple[list[CardRow], list[SentenceCardRow]]:
    client = JishoClient()
    rows: list[CardRow] = []
    sentence_rows: list[SentenceCardRow] = []

    select_candidate = selector or default_interactive_selector

    for index, word in enumerate(words, start=1):
        candidates, sentences = client.search(
            word,
            candidate_limit=max(candidate_limit, 1),
            sentence_limit=max(sentence_count, 0),
        )

        if candidates:
            selected = candidates[0]
            if interactive_review:
                selected = select_candidate(word, candidates)
        else:
            selected = SearchCandidate(meaning="", reading="")

        meaning = selected.meaning
        reading = selected.reading

        if include_sentences and meaning and not separate_sentence_cards:
            sentence_text = format_sentences(sentences)
            if sentence_text:
                meaning = f"{meaning}<br><br>{sentence_text}"

        if separate_sentence_cards:
            for sentence in sentences:
                sentence_rows.append(
                    SentenceCardRow(
                        front=sentence.japanese,
                        back=(
                            f"{sentence.english}<br><br>"
                            f"Word: {word}<br>Reading: {selected.reading}"
                        ),
                    )
                )

        if include_pitch_accent:
            pitch_html = enrich_html_with_pitch(word, reading)
            if pitch_html:
                if reading:
                    reading = f"{reading}<br><br>{pitch_html}"
                else:
                    reading = pitch_html

        rows.append(CardRow(word=word, meaning=meaning, reading=reading))

        if progress_printer is not None:
            progress_printer(
                f"[{index}/{len(words)}] {word} -> reading='{reading}' meaning='{selected.meaning}'"
            )

        if pause_seconds > 0:
            time.sleep(pause_seconds)

    return rows, sentence_rows
