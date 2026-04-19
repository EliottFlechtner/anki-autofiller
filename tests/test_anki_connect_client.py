"""Tests for AnkiConnect note submission and auto-model creation behavior."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from autofiller.anki_connect_client import add_rows_to_anki
from autofiller.models import CardRow


class AnkiConnectClientTests(unittest.TestCase):
    """Validate model bootstrap and add-notes behavior for vocabulary rows."""

    def test_add_rows_skips_model_creation_when_model_exists(self) -> None:
        """Existing model should be reused without calling createModel."""
        calls: list[tuple[str, dict]] = []

        def fake_invoke(url: str, action: str, params: dict) -> object:
            calls.append((action, params))
            if action == "modelNames":
                return ["Jisho2Anki::Vocab"]
            if action == "createDeck":
                return 1
            if action == "addNotes":
                return [123]
            raise AssertionError(f"Unexpected action: {action}")

        rows = [CardRow(word="食べる", meaning="to eat", reading="たべる")]

        with patch("autofiller.anki_connect_client.invoke", side_effect=fake_invoke):
            success, failed = add_rows_to_anki(
                rows,
                url="http://127.0.0.1:8765",
                deck_name="Example",
                model_name="Jisho2Anki::Vocab",
                word_field="Word",
                meaning_field="Translation",
                reading_field="Reading",
                tags=["jp"],
                allow_duplicates=False,
            )

        self.assertEqual((success, failed), (1, 0))
        actions = [action for action, _params in calls]
        self.assertIn("modelNames", actions)
        self.assertNotIn("createModel", actions)
        self.assertIn("createDeck", actions)
        self.assertIn("addNotes", actions)

    def test_add_rows_creates_vocab_model_when_missing(self) -> None:
        """Missing model should be created with expected field order and templates."""
        calls: list[tuple[str, dict]] = []

        def fake_invoke(url: str, action: str, params: dict) -> object:
            calls.append((action, params))
            if action == "modelNames":
                return []
            if action == "createModel":
                return True
            if action == "createDeck":
                return 1
            if action == "addNotes":
                return [456]
            raise AssertionError(f"Unexpected action: {action}")

        rows = [CardRow(word="試合", meaning="match", reading="しあい")]

        with patch("autofiller.anki_connect_client.invoke", side_effect=fake_invoke):
            success, failed = add_rows_to_anki(
                rows,
                url="http://127.0.0.1:8765",
                deck_name="Example",
                model_name="Jisho2Anki::Vocab",
                word_field="Word",
                meaning_field="Translation",
                reading_field="Reading",
                tags=[],
                allow_duplicates=True,
            )

        self.assertEqual((success, failed), (1, 0))

        create_model_calls = [
            params for action, params in calls if action == "createModel"
        ]
        self.assertEqual(len(create_model_calls), 1)
        create_model_params = create_model_calls[0]
        self.assertEqual(
            create_model_params["inOrderFields"],
            ["Word", "Reading", "Translation"],
        )
        self.assertEqual(len(create_model_params["cardTemplates"]), 2)
        self.assertEqual(
            create_model_params["cardTemplates"][1]["Name"],
            "Translation -> Word+Reading",
        )
        self.assertIn(
            '<div class="meaning">{{Translation}}</div>',
            create_model_params["cardTemplates"][1]["Front"],
        )
        self.assertIn(
            '<div class="word">{{Word}}</div>',
            create_model_params["cardTemplates"][1]["Back"],
        )
        self.assertIn(
            '<div class="reading">{{Reading}}</div>',
            create_model_params["cardTemplates"][1]["Back"],
        )


if __name__ == "__main__":
    unittest.main()
