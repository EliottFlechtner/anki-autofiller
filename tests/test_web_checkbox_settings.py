from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from autofiller.models import CardRow, SentenceCardRow

try:
    from autofiller.web_app import _bool_from_form, _build_from_form

    _WEB_APP_IMPORT_ERROR = None
except ModuleNotFoundError as exc:
    _bool_from_form = None  # type: ignore[assignment]
    _build_from_form = None  # type: ignore[assignment]
    _WEB_APP_IMPORT_ERROR = exc


def _base_settings() -> dict[str, object]:
    return {
        "output_path": "anki_import.tsv",
        "include_header": True,
        "pause_seconds": 0.0,
        "max_workers": 2,
        "candidate_limit": 3,
        "sentence_count": 2,
        "separate_sentence_cards": True,
        "include_sentences": True,
        "include_pitch_accent": False,
        "anki_connect": True,
        "anki_url": "http://127.0.0.1:8765",
        "deck_name": "Example",
        "model_name": "Japanese (Basic & Reversed)",
        "field_word": "Expression",
        "field_meaning": "Meaning",
        "field_reading": "Reading",
        "tags": "",
        "allow_duplicates": True,
        "sentence_deck_name": "Example::Sentences",
        "sentence_model_name": "Basic",
        "sentence_front_field": "Front",
        "sentence_back_field": "Back",
    }


@unittest.skipIf(
    _WEB_APP_IMPORT_ERROR is not None,
    "Flask dependency missing for web_app tests. Install requirements or run make test-docker.",
)
class CheckboxBehaviorTests(unittest.TestCase):
    def test_bool_parser_accepts_true_false_forms(self) -> None:
        self.assertTrue(_bool_from_form("true"))
        self.assertTrue(_bool_from_form("on"))
        self.assertTrue(_bool_from_form("1"))
        self.assertFalse(_bool_from_form("no", default=True))
        self.assertFalse(_bool_from_form("off", default=True))
        self.assertFalse(_bool_from_form("false", default=True))
        self.assertFalse(_bool_from_form("0", default=True))
        self.assertTrue(_bool_from_form("unexpected", default=True))
        self.assertFalse(_bool_from_form("unexpected", default=False))

    def test_build_rows_uses_settings_default_when_checkbox_missing(self) -> None:
        settings = _base_settings()
        form_data = {
            "words": "食べる",
            "output_path": "output/test.tsv",
            # include_sentences missing on purpose -> fallback to settings default (True)
            # include_pitch_accent missing on purpose -> fallback to settings default (False)
            "anki_connect": "false",
        }

        rows = [CardRow(word="食べる", meaning="eat", reading="たべる")]

        with (
            patch(
                "autofiller.web_app._resolved_settings_for_request",
                return_value=settings,
            ),
            patch(
                "autofiller.web_app.build_rows", return_value=(rows, [])
            ) as build_rows_mock,
            patch("autofiller.web_app.write_tsv"),
        ):
            _build_from_form(form_data, progress_printer=lambda _line: None)

        kwargs = build_rows_mock.call_args.kwargs
        self.assertTrue(kwargs["include_sentences"])
        self.assertFalse(kwargs["include_pitch_accent"])

    def test_legacy_on_off_values_are_honored(self) -> None:
        settings = _base_settings()
        form_data = {
            "words": "勉強",
            "output_path": "output/test.tsv",
            "include_header": "on",
            "include_sentences": "off",
            "include_pitch_accent": "on",
            "separate_sentence_cards": "off",
            "anki_connect": "off",
            "allow_duplicates": "off",
        }

        rows = [CardRow(word="勉強", meaning="study", reading="べんきょう")]

        with (
            patch(
                "autofiller.web_app._resolved_settings_for_request",
                return_value=settings,
            ),
            patch(
                "autofiller.web_app.build_rows", return_value=(rows, [])
            ) as build_rows_mock,
            patch("autofiller.web_app.write_tsv") as write_tsv_mock,
            patch("autofiller.web_app.add_rows_to_anki") as add_rows_mock,
        ):
            _build_from_form(form_data, progress_printer=lambda _line: None)

        kwargs = build_rows_mock.call_args.kwargs
        self.assertFalse(kwargs["include_sentences"])
        self.assertTrue(kwargs["include_pitch_accent"])
        self.assertFalse(kwargs["separate_sentence_cards"])

        write_kwargs = write_tsv_mock.call_args.kwargs
        self.assertTrue(write_kwargs["include_header"])
        add_rows_mock.assert_not_called()

    def test_build_rows_receives_checkbox_overrides(self) -> None:
        settings = _base_settings()
        form_data = {
            "words": "食べる",
            "output_path": "output/test.tsv",
            "include_header": "false",
            "include_sentences": "false",
            "include_pitch_accent": "true",
            "separate_sentence_cards": "false",
            "anki_connect": "false",
            "allow_duplicates": "false",
        }

        rows = [CardRow(word="食べる", meaning="eat", reading="たべる")]

        with (
            patch(
                "autofiller.web_app._resolved_settings_for_request",
                return_value=settings,
            ),
            patch(
                "autofiller.web_app.build_rows", return_value=(rows, [])
            ) as build_rows_mock,
            patch("autofiller.web_app.write_tsv") as write_tsv_mock,
            patch("autofiller.web_app.add_rows_to_anki") as add_rows_mock,
        ):
            _build_from_form(form_data, progress_printer=lambda _line: None)

        kwargs = build_rows_mock.call_args.kwargs
        self.assertFalse(kwargs["include_sentences"])
        self.assertTrue(kwargs["include_pitch_accent"])
        self.assertFalse(kwargs["separate_sentence_cards"])

        write_kwargs = write_tsv_mock.call_args.kwargs
        self.assertFalse(write_kwargs["include_header"])
        self.assertEqual(write_kwargs["output_path"], Path("output/test.tsv"))

        add_rows_mock.assert_not_called()

    def test_anki_connect_respects_allow_duplicates_false(self) -> None:
        settings = _base_settings()
        form_data = {
            "words": "試合",
            "output_path": "output/test.tsv",
            "include_header": "true",
            "include_sentences": "true",
            "include_pitch_accent": "false",
            "separate_sentence_cards": "true",
            "anki_connect": "true",
            "allow_duplicates": "false",
        }

        rows = [CardRow(word="試合", meaning="match", reading="しあい")]
        sentence_rows = [SentenceCardRow(front="試合だ。", back="It is a match.")]

        with (
            patch(
                "autofiller.web_app._resolved_settings_for_request",
                return_value=settings,
            ),
            patch(
                "autofiller.web_app.build_rows",
                return_value=(rows, sentence_rows),
            ),
            patch("autofiller.web_app.write_tsv"),
            patch(
                "autofiller.web_app.add_rows_to_anki",
                return_value=(1, 0),
            ) as add_rows_mock,
            patch(
                "autofiller.web_app.add_sentence_rows_to_anki",
                return_value=(1, 0),
            ) as add_sentence_rows_mock,
        ):
            result = _build_from_form(form_data, progress_printer=lambda _line: None)

        add_rows_kwargs = add_rows_mock.call_args.kwargs
        self.assertFalse(add_rows_kwargs["allow_duplicates"])

        add_sentence_kwargs = add_sentence_rows_mock.call_args.kwargs
        self.assertFalse(add_sentence_kwargs["allow_duplicates"])

        self.assertIn("Added to Anki: success=1, failed=0", result["anki_summary"])
        self.assertIn("Sentence cards: success=1, failed=0", result["anki_summary"])


if __name__ == "__main__":
    unittest.main()
