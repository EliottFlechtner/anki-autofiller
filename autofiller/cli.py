"""CLI entrypoint and argument parsing for the Jisho2Anki pipeline."""

from __future__ import annotations

import argparse
from pathlib import Path

from .anki_connect_client import add_rows_to_anki, add_sentence_rows_to_anki
from .config import (
    DEFAULT_DECK_NAME,
    DEFAULT_MODEL_NAME,
    load_settings,
)
from .io_utils import read_words_from_file, write_tsv
from .pipeline import build_rows


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments, merging defaults from preset/env-file settings."""
    bootstrap = argparse.ArgumentParser(add_help=False)
    bootstrap.add_argument(
        "--preset",
        default=None,
        help="Preset name from presets/<name>.env.",
    )
    bootstrap.add_argument(
        "--env-file",
        default=None,
        help="Path to env-style config file with ANKI_JISHO2ANKI_* values.",
    )
    pre_args, _ = bootstrap.parse_known_args()
    defaults = load_settings(preset_name=pre_args.preset, env_file=pre_args.env_file)

    parser = argparse.ArgumentParser(
        description="Create an Anki TSV file from Japanese words.",
        parents=[bootstrap],
    )
    parser.add_argument(
        "--input",
        default=defaults["input"],
        help="Path to text file with one Japanese word per line.",
    )
    parser.add_argument(
        "--output",
        default=defaults["output_path"],
        help="Output TSV path (default: anki_import.tsv).",
    )
    parser.add_argument("--include-header", dest="include_header", action="store_true")
    parser.add_argument("--no-header", dest="include_header", action="store_false")
    parser.set_defaults(include_header=bool(defaults["include_header"]))
    parser.add_argument(
        "--pause-seconds",
        type=float,
        default=defaults["pause_seconds"],
        help="Delay between requests to reduce API throttling.",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=defaults["max_workers"],
        help="Parallel workers for lookups (used when interactive mode is off and pause is 0).",
    )
    parser.add_argument(
        "--interactive-review", dest="interactive_review", action="store_true"
    )
    parser.add_argument(
        "--no-interactive-review", dest="interactive_review", action="store_false"
    )
    parser.set_defaults(interactive_review=bool(defaults["interactive_review"]))
    parser.add_argument(
        "--candidate-limit",
        type=int,
        default=defaults["candidate_limit"],
        help="Maximum number of Jisho candidates to show/use.",
    )
    parser.add_argument(
        "--sentence-count",
        type=int,
        default=defaults["sentence_count"],
        help="How many Jisho example sentences to append to Meaning.",
    )
    parser.add_argument(
        "--separate-sentence-cards", dest="separate_sentence_cards", action="store_true"
    )
    parser.add_argument(
        "--no-separate-sentence-cards",
        dest="separate_sentence_cards",
        action="store_false",
    )
    parser.set_defaults(
        separate_sentence_cards=bool(defaults["separate_sentence_cards"])
    )

    parser.add_argument(
        "--include-sentences", dest="include_sentences", action="store_true"
    )
    parser.add_argument(
        "--no-sentences", dest="include_sentences", action="store_false"
    )
    parser.set_defaults(include_sentences=bool(defaults["include_sentences"]))

    parser.add_argument(
        "--pitch-accent", dest="include_pitch_accent", action="store_true"
    )
    parser.add_argument(
        "--no-pitch-accent", dest="include_pitch_accent", action="store_false"
    )
    parser.set_defaults(include_pitch_accent=bool(defaults["include_pitch_accent"]))

    parser.add_argument("--anki-connect", dest="anki_connect", action="store_true")
    parser.add_argument("--no-anki-connect", dest="anki_connect", action="store_false")
    parser.set_defaults(anki_connect=bool(defaults["anki_connect"]))
    parser.add_argument(
        "--anki-url",
        default=defaults["anki_url"],
        help="AnkiConnect endpoint.",
    )
    parser.add_argument(
        "--deck-name",
        default=defaults["deck_name"],
        help=f"Deck name for AnkiConnect mode (default: {DEFAULT_DECK_NAME}).",
    )
    parser.add_argument(
        "--model-name",
        default=defaults["model_name"],
        help=f"Note type/model name for AnkiConnect mode (default: {DEFAULT_MODEL_NAME}).",
    )
    parser.add_argument(
        "--field-word",
        default=defaults["field_word"],
        help="Expression field name in your Anki note type (default: Expression).",
    )
    parser.add_argument(
        "--field-meaning",
        default=defaults["field_meaning"],
        help="Meaning field name in your Anki note type (default: Meaning).",
    )
    parser.add_argument(
        "--field-reading",
        default=defaults["field_reading"],
        help="Reading field name in your Anki note type (default: Reading).",
    )
    parser.add_argument(
        "--tags",
        default=defaults["tags"],
        help="Comma-separated tags to apply in AnkiConnect mode.",
    )
    parser.add_argument(
        "--allow-duplicates", dest="allow_duplicates", action="store_true"
    )
    parser.add_argument(
        "--disallow-duplicates", dest="allow_duplicates", action="store_false"
    )
    parser.set_defaults(allow_duplicates=bool(defaults["allow_duplicates"]))
    parser.add_argument(
        "--sentence-deck-name",
        default=defaults["sentence_deck_name"],
        help="Deck for separate sentence cards (default: Keio::TestApp::Examples).",
    )
    parser.add_argument(
        "--sentence-model-name",
        default=defaults["sentence_model_name"],
        help="Model for separate sentence cards (default: Basic).",
    )
    parser.add_argument(
        "--sentence-front-field",
        default=defaults["sentence_front_field"],
        help="Front field for separate sentence cards (default: Front).",
    )
    parser.add_argument(
        "--sentence-back-field",
        default=defaults["sentence_back_field"],
        help="Back field for separate sentence cards (default: Back).",
    )
    return parser.parse_args()


def main() -> None:
    """Run the end-to-end CLI flow: load words, generate rows, write/export."""
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
        include_sentences=args.include_sentences,
        separate_sentence_cards=args.separate_sentence_cards,
        include_pitch_accent=args.include_pitch_accent,
        max_workers=max(1, args.max_workers),
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
