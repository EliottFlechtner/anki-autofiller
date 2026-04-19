"""Review-item and preview serialization helpers for the web workflow."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable

from ..jisho_client import JishoClient
from ..models import CardRow, SearchCandidate, SentenceCardRow
from ..pitch_accent import enrich_html_with_pitch


def serialize_rows_preview(rows: list[Any], limit: int = 60) -> list[dict[str, str]]:
    """Serialize generated rows into a lightweight preview payload."""
    return [
        {"word": row.word, "meaning": row.meaning, "reading": row.reading}
        for row in rows[:limit]
    ]


def serialize_sentence_rows_preview(
    rows: list[Any], limit: int = 60
) -> list[dict[str, str]]:
    """Serialize generated sentence rows into a lightweight preview payload."""
    return [{"front": row.front, "back": row.back} for row in rows[:limit]]


def deserialize_card_rows(payload_rows: list[dict[str, str]]) -> list[CardRow]:
    """Rebuild CardRow objects from serialized payload dictionaries."""
    return [
        CardRow(
            word=str(item.get("word", "")),
            meaning=str(item.get("meaning", "")),
            reading=str(item.get("reading", "")),
        )
        for item in payload_rows
    ]


def deserialize_sentence_rows(
    payload_rows: list[dict[str, str]],
) -> list[SentenceCardRow]:
    """Rebuild SentenceCardRow objects from serialized payload dictionaries."""
    return [
        SentenceCardRow(
            front=str(item.get("front", "")),
            back=str(item.get("back", "")),
        )
        for item in payload_rows
    ]


def to_hiragana(text: str) -> str:
    """Convert Katakana in text to Hiragana, preserving other characters."""
    chars: list[str] = []
    for char in text:
        code = ord(char)
        if 0x30A1 <= code <= 0x30F6:
            chars.append(chr(code - 0x60))
        else:
            chars.append(char)
    return "".join(chars)


def build_review_items(
    *,
    words: list[str],
    candidate_limit: int,
    include_pitch_accent: bool,
    pitch_accent_theme: str,
    generated_rows: list[CardRow],
    max_workers: int = 1,
    search_review: (
        Callable[[str, int], tuple[list[SearchCandidate], list[dict[str, Any]]]] | None
    ) = None,
    render_pitch: Callable[[str, str, str], str | None] | None = None,
) -> list[dict[str, Any]]:
    """Build per-word candidate options used by web review-before-add workflow."""
    safe_workers = max(1, max_workers)

    def _build_single_item(index: int, word: str) -> dict[str, Any]:
        if search_review is None:
            client = JishoClient()
            candidates, related_candidates = client.search_review(
                word,
                candidate_limit=max(candidate_limit, 1),
            )
        else:
            candidates, related_candidates = search_review(
                word,
                max(candidate_limit, 1),
            )
        if not candidates:
            candidates = [SearchCandidate(meaning="", reading="")]

        options: list[dict[str, str]] = []
        for candidate in candidates:
            reading = to_hiragana(candidate.reading)
            reading_preview = reading
            if include_pitch_accent:
                if render_pitch is None:
                    pitch_html = enrich_html_with_pitch(
                        word,
                        reading,
                        theme=pitch_accent_theme,
                    )
                else:
                    pitch_html = render_pitch(word, reading, pitch_accent_theme)
                if pitch_html:
                    reading_preview = pitch_html

            options.append(
                {
                    "meaning": candidate.meaning,
                    "reading": reading,
                    "reading_preview": reading_preview,
                }
            )

        selected_index = 0
        if index < len(generated_rows):
            generated_meaning = generated_rows[index].meaning
            for opt_index, option in enumerate(options):
                if option["meaning"] == generated_meaning:
                    selected_index = opt_index
                    break

        return {
            "word": generated_rows[index].word if index < len(generated_rows) else word,
            "source_word": word,
            "options": options,
            "related_words": [
                {
                    "word": str(item.get("word", "")),
                    "meaning": str(item.get("meaning", "")),
                    "reading": to_hiragana(str(item.get("reading", ""))),
                    "reading_preview": (
                        (
                            enrich_html_with_pitch(
                                str(item.get("word", "")),
                                to_hiragana(str(item.get("reading", ""))),
                                theme=pitch_accent_theme,
                            )
                            if render_pitch is None
                            else render_pitch(
                                str(item.get("word", "")),
                                to_hiragana(str(item.get("reading", ""))),
                                pitch_accent_theme,
                            )
                        )
                        if include_pitch_accent
                        else to_hiragana(str(item.get("reading", "")))
                    )
                    or to_hiragana(str(item.get("reading", ""))),
                }
                for item in related_candidates
                if str(item.get("word", "")).strip()
            ],
            "selected_index": selected_index,
        }

    if safe_workers == 1 or len(words) <= 1:
        return [_build_single_item(index, word) for index, word in enumerate(words)]

    ordered_items: list[dict[str, Any] | None] = [None] * len(words)
    with ThreadPoolExecutor(max_workers=min(safe_workers, len(words))) as executor:
        futures = {
            executor.submit(_build_single_item, index, word): index
            for index, word in enumerate(words)
        }
        for future in as_completed(futures):
            index = futures[future]
            ordered_items[index] = future.result()

    return [item for item in ordered_items if item is not None]
