from __future__ import annotations

import argparse
from pathlib import Path

from anki_connect_client import add_rows_to_anki, add_sentence_rows_to_anki
from io_utils import read_words_from_file, write_tsv
from pipeline import build_rows

DEFAULT_DECK_NAME = "Keio::TestApp"
DEFAULT_MODEL_NAME = "Japanese (Basic & Reversed)"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create an Anki TSV file from Japanese words."
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Path to text file with one Japanese word per line.",
    )
    parser.add_argument(
        "--output",
        default="anki_import.tsv",
        help="Output TSV path (default: anki_import.tsv).",
    )
    parser.add_argument(
        "--include-header",
        action="store_true",
        help="Write a header row: Word, Meaning, Reading.",
    )
    parser.add_argument(
        "--pause-seconds",
        type=float,
        default=0.15,
        help="Delay between requests to reduce API throttling (default: 0.15).",
    )
    parser.add_argument(
        "--interactive-review",
        action="store_true",
        help="Prompt to select from multiple reading/meaning candidates per word.",
    )
    parser.add_argument(
        "--candidate-limit",
        type=int,
        default=3,
        help="Maximum number of Jisho candidates to show/use (default: 3).",
    )
    parser.add_argument(
        "--sentence-count",
        type=int,
        default=2,
        help="How many Jisho example sentences to append to Meaning (default: 2).",
    )
    parser.add_argument(
        "--separate-sentence-cards",
        action="store_true",
        help="Create sentence examples as separate notes instead of appending to Meaning.",
    )
    parser.add_argument(
        "--no-sentences",
        action="store_true",
        help="Disable appending example sentences into the Meaning field.",
    )
    parser.add_argument(
        "--no-pitch-accent",
        action="store_true",
        help="Disable automatic pitch accent SVG generation.",
    )
    parser.add_argument(
        "--anki-connect",
        action="store_true",
        help="Also add notes directly to Anki via AnkiConnect.",
    )
    parser.add_argument(
        "--anki-url",
        default="http://127.0.0.1:8765",
        help="AnkiConnect endpoint (default: http://127.0.0.1:8765).",
    )
    parser.add_argument(
        "--deck-name",
        default=DEFAULT_DECK_NAME,
        help=f"Deck name for AnkiConnect mode (default: {DEFAULT_DECK_NAME}).",
    )
    parser.add_argument(
        "--model-name",
        default=DEFAULT_MODEL_NAME,
        help=f"Note type/model name for AnkiConnect mode (default: {DEFAULT_MODEL_NAME}).",
    )
    parser.add_argument(
        "--field-word",
        default="Expression",
        help="Expression field name in your Anki note type (default: Expression).",
    )
    parser.add_argument(
        "--field-meaning",
        default="Meaning",
        help="Meaning field name in your Anki note type (default: Meaning).",
    )
    parser.add_argument(
        "--field-reading",
        default="Reading",
        help="Reading field name in your Anki note type (default: Reading).",
    )
    parser.add_argument(
        "--tags",
        default="",
        help="Comma-separated tags to apply in AnkiConnect mode.",
    )
    parser.add_argument(
        "--allow-duplicates",
        action="store_true",
        help="Allow duplicate notes when adding via AnkiConnect.",
    )
    parser.add_argument(
        "--sentence-deck-name",
        default=f"{DEFAULT_DECK_NAME}::Examples",
        help="Deck for separate sentence cards (default: Keio::TestApp::Examples).",
    )
    parser.add_argument(
        "--sentence-model-name",
        default="Basic",
        help="Model for separate sentence cards (default: Basic).",
    )
    parser.add_argument(
        "--sentence-front-field",
        default="Front",
        help="Front field for separate sentence cards (default: Front).",
    )
    parser.add_argument(
        "--sentence-back-field",
        default="Back",
        help="Back field for separate sentence cards (default: Back).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    words = read_words_from_file(input_path)
    if not words:
        raise ValueError("Input file has no words.")

    rows, sentence_rows = build_rows(
        words=words,
        pause_seconds=args.pause_seconds,
        candidate_limit=args.candidate_limit,
        sentence_count=args.sentence_count,
        include_sentences=not args.no_sentences,
        separate_sentence_cards=args.separate_sentence_cards,
        include_pitch_accent=not args.no_pitch_accent,
        interactive_review=args.interactive_review,
    )

    write_tsv(rows=rows, output_path=output_path, include_header=args.include_header)
    print(f"\nWrote {len(rows)} rows to: {output_path}")

    if args.anki_connect:
        if not args.deck_name or not args.model_name:
            raise ValueError("--deck-name and --model-name must not be blank.")

        tags = [tag.strip() for tag in args.tags.split(",") if tag.strip()]
        success, failed = add_rows_to_anki(
            rows,
            url=args.anki_url,
            deck_name=args.deck_name,
            model_name=args.model_name,
            word_field=args.field_word,
            meaning_field=args.field_meaning,
            reading_field=args.field_reading,
            tags=tags,
            allow_duplicates=args.allow_duplicates,
        )
        print(
            f"Added notes via AnkiConnect: success={success}, failed={failed}, endpoint={args.anki_url}"
        )

        if args.separate_sentence_cards:
            sent_success, sent_failed = add_sentence_rows_to_anki(
                sentence_rows,
                url=args.anki_url,
                deck_name=args.sentence_deck_name,
                model_name=args.sentence_model_name,
                front_field=args.sentence_front_field,
                back_field=args.sentence_back_field,
                tags=tags,
                allow_duplicates=args.allow_duplicates,
            )
            print(
                "Added sentence notes via AnkiConnect: "
                f"success={sent_success}, failed={sent_failed}, deck={args.sentence_deck_name}"
            )


if __name__ == "__main__":
    main()
