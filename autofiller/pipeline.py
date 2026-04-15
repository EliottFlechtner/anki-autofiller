"""Pipeline for Jisho lookup, row generation, and optional enrichment."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

from .jisho_client import JishoClient
from .models import CardRow, ExampleSentence, SearchCandidate, SentenceCardRow
from .pitch_accent import enrich_html_with_pitch


def format_sentences(sentences: list[ExampleSentence]) -> str:
    """Format sentence pairs into the HTML snippet expected by the meaning field."""
    if not sentences:
        return ""
    parts = [f"例文: {s.japanese} - {s.english}" for s in sentences]
    return "<br>".join(parts)


def default_interactive_selector(
    word: str, candidates: list[SearchCandidate]
) -> SearchCandidate:
    """Prompt on stdin/stdout to let users choose the best dictionary candidate."""
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


def _build_word_result(
    *,
    word: str,
    candidate_limit: int,
    sentence_count: int,
    include_sentences: bool,
    separate_sentence_cards: bool,
    include_pitch_accent: bool,
    interactive_review: bool,
    selector: Callable[[str, list[SearchCandidate]], SearchCandidate],
) -> tuple[CardRow, list[SentenceCardRow], str, str]:
    """Build the generated row(s) for a single source word."""
    client = JishoClient()
    candidates, sentences = client.search(
        word,
        candidate_limit=max(candidate_limit, 1),
        sentence_limit=max(sentence_count, 0),
    )

    if candidates:
        selected = candidates[0]
        if interactive_review:
            selected = selector(word, candidates)
    else:
        selected = SearchCandidate(meaning="", reading="")

    meaning = selected.meaning
    reading = selected.reading

    if include_sentences and meaning and not separate_sentence_cards:
        sentence_text = format_sentences(sentences)
        if sentence_text:
            meaning = f"{meaning}<br><br>{sentence_text}"

    sentence_rows: list[SentenceCardRow] = []
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

    row = CardRow(word=word, meaning=meaning, reading=reading)
    return row, sentence_rows, reading, selected.meaning


def build_rows(
    words: list[str],
    *,
    pause_seconds: float,
    candidate_limit: int,
    sentence_count: int,
    include_sentences: bool,
    separate_sentence_cards: bool,
    include_pitch_accent: bool,
    max_workers: int,
    interactive_review: bool,
    selector: Callable[[str, list[SearchCandidate]], SearchCandidate] | None = None,
    progress_printer: Callable[[str], None] | None = print,
) -> tuple[list[CardRow], list[SentenceCardRow]]:
    """Build card rows for all words, optionally in parallel with progress reporting."""
    rows: list[CardRow] = [
        CardRow(word="", meaning="", reading="") for _ in range(len(words))
    ]
    sentence_rows: list[SentenceCardRow] = []

    select_candidate = selector or default_interactive_selector

    can_parallelize = max_workers > 1 and not interactive_review and pause_seconds <= 0

    if can_parallelize:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {
                executor.submit(
                    _build_word_result,
                    word=word,
                    candidate_limit=candidate_limit,
                    sentence_count=sentence_count,
                    include_sentences=include_sentences,
                    separate_sentence_cards=separate_sentence_cards,
                    include_pitch_accent=include_pitch_accent,
                    interactive_review=interactive_review,
                    selector=select_candidate,
                ): (index, word)
                for index, word in enumerate(words)
            }

            completed = 0
            for future in as_completed(future_map):
                index, word = future_map[future]
                row, generated_sentence_rows, reading, plain_meaning = future.result()
                rows[index] = row
                sentence_rows.extend(generated_sentence_rows)
                completed += 1
                if progress_printer is not None:
                    progress_printer(
                        f"[{completed}/{len(words)}] {word} -> reading='{reading}' meaning='{plain_meaning}'"
                    )

        return rows, sentence_rows

    for index, word in enumerate(words, start=1):
        row, generated_sentence_rows, reading, plain_meaning = _build_word_result(
            word=word,
            candidate_limit=candidate_limit,
            sentence_count=sentence_count,
            include_sentences=include_sentences,
            separate_sentence_cards=separate_sentence_cards,
            include_pitch_accent=include_pitch_accent,
            interactive_review=interactive_review,
            selector=select_candidate,
        )
        rows[index - 1] = row
        sentence_rows.extend(generated_sentence_rows)

        if progress_printer is not None:
            progress_printer(
                f"[{index}/{len(words)}] {word} -> reading='{reading}' meaning='{plain_meaning}'"
            )

        if pause_seconds > 0:
            time.sleep(pause_seconds)

    return rows, sentence_rows
