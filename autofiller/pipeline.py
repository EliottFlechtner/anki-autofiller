"""Pipeline for Jisho lookup, row generation, and optional enrichment."""

from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

from .furigana import add_furigana
from .jisho_client import JishoClient
from .models import CardRow, ExampleSentence, SearchCandidate, SentenceCardRow
from .pitch_accent import enrich_html_with_pitch


def _to_hiragana(text: str) -> str:
    """Convert Katakana in `text` to Hiragana, preserving other characters."""
    chars: list[str] = []
    for char in text:
        code = ord(char)
        if 0x30A1 <= code <= 0x30F6:
            chars.append(chr(code - 0x60))
        else:
            chars.append(char)
    return "".join(chars)


def _highlight_target_word(sentence: str, target_word: str) -> str:
    """Highlight each exact target-word occurrence in a Japanese sentence."""
    normalized_target = target_word.strip()
    if not normalized_target:
        return sentence

    pattern = re.escape(normalized_target)
    return re.sub(
        pattern,
        lambda match: (f'<b style="color:#dc2626;">{match.group(0)}</b>'),
        sentence,
    )


def format_sentences(sentences: list[ExampleSentence], *, target_word: str = "") -> str:
    """Format sentence pairs into the HTML snippet expected by the meaning field.

    Args:
        sentences: Example sentence pairs to render.

    Returns:
        HTML string using `<br>` separators, or an empty string when no sentences exist.
    """
    if not sentences:
        return ""
    parts = [
        f"例文: {_highlight_target_word(s.japanese, target_word)} - {s.english}"
        for s in sentences
    ]
    return "<br>".join(parts)


def default_interactive_selector(
    word: str, candidates: list[SearchCandidate]
) -> SearchCandidate:
    """Prompt on stdin/stdout to let users choose the best dictionary candidate.

    Args:
        word: Source word being reviewed.
        candidates: Candidate options retrieved from Jisho.

    Returns:
        Selected candidate, or an empty candidate when `0` is chosen.
    """
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
    pitch_accent_theme: str,
    include_furigana: bool,
    furigana_format: str,
    interactive_review: bool,
    selector: Callable[[str, list[SearchCandidate]], SearchCandidate],
) -> tuple[CardRow, list[SentenceCardRow], str, str]:
    """Build generated row payloads for a single source word.

    Args:
        word: Source vocabulary word.
        candidate_limit: Max dictionary candidates to consider.
        sentence_count: Max example sentences to include.
        include_sentences: Whether to append sentences into meaning text.
        separate_sentence_cards: Whether to emit sentence rows separately.
        include_pitch_accent: Whether to enrich reading with pitch SVG.
        pitch_accent_theme: Visual theme used by pitch SVG (`dark` or `light`).
        include_furigana: Whether to annotate the word with furigana markup.
        furigana_format: Furigana rendering format (`ruby` or `anki`).
        interactive_review: Whether candidate selection is interactive.
        selector: Candidate selection callback used in interactive mode.

    Returns:
        Tuple of `(card_row, sentence_rows, rendered_reading, selected_meaning)`.
    """
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
    reading = _to_hiragana(selected.reading)
    rendered_word = word

    if include_furigana and reading:
        rendered_word = add_furigana(word, reading, fmt=furigana_format)

    if include_sentences and meaning and not separate_sentence_cards:
        sentence_text = format_sentences(sentences, target_word=word)
        if sentence_text:
            meaning = f"{meaning}<br><br>{sentence_text}"

    sentence_rows: list[SentenceCardRow] = []
    if separate_sentence_cards:
        for sentence in sentences:
            highlighted_front = _highlight_target_word(sentence.japanese, word)
            sentence_rows.append(
                SentenceCardRow(
                    front=highlighted_front,
                    back=(
                        f"{sentence.english}<br><br>"
                        f"Word: {word}<br>Reading: {selected.reading}"
                    ),
                )
            )

    if include_pitch_accent:
        pitch_html = enrich_html_with_pitch(word, reading, theme=pitch_accent_theme)
        if pitch_html:
            # In pitch mode, the reading field should only show the rendered graph,
            # since the graph already includes the reading text.
            reading = pitch_html

    row = CardRow(word=rendered_word, meaning=meaning, reading=reading)
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
    pitch_accent_theme: str,
    include_furigana: bool,
    furigana_format: str,
    max_workers: int,
    interactive_review: bool,
    selector: Callable[[str, list[SearchCandidate]], SearchCandidate] | None = None,
    progress_printer: Callable[[str], None] | None = print,
) -> tuple[list[CardRow], list[SentenceCardRow]]:
    """Build card rows for all words.

    Args:
        words: Source words to process.
        pause_seconds: Sleep duration between words in sequential mode.
        candidate_limit: Max candidates fetched per word.
        sentence_count: Max example sentences fetched per word.
        include_sentences: Whether to append sentences into meaning field.
        separate_sentence_cards: Whether to emit sentence rows as separate notes.
        include_pitch_accent: Whether to append pitch accent SVG snippets.
        pitch_accent_theme: Visual theme used by pitch SVG (`dark` or `light`).
        include_furigana: Whether to annotate words with furigana markup.
        furigana_format: Furigana rendering format (`ruby` or `anki`).
        max_workers: Max worker threads for parallel mode.
        interactive_review: Whether to enable interactive candidate review.
        selector: Optional candidate selector override.
        progress_printer: Optional callback receiving progress log lines.

    Returns:
        Tuple of `(rows, sentence_rows)` preserving input word order.
    """
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
                    pitch_accent_theme=pitch_accent_theme,
                    include_furigana=include_furigana,
                    furigana_format=furigana_format,
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
                    progress_printer(f"[{completed}/{len(words)}] {word}")

        return rows, sentence_rows

    for index, word in enumerate(words, start=1):
        row, generated_sentence_rows, reading, plain_meaning = _build_word_result(
            word=word,
            candidate_limit=candidate_limit,
            sentence_count=sentence_count,
            include_sentences=include_sentences,
            separate_sentence_cards=separate_sentence_cards,
            include_pitch_accent=include_pitch_accent,
            pitch_accent_theme=pitch_accent_theme,
            include_furigana=include_furigana,
            furigana_format=furigana_format,
            interactive_review=interactive_review,
            selector=select_candidate,
        )
        rows[index - 1] = row
        sentence_rows.extend(generated_sentence_rows)

        if progress_printer is not None:
            progress_printer(f"[{index}/{len(words)}] {word}")

        if pause_seconds > 0:
            time.sleep(pause_seconds)

    return rows, sentence_rows
