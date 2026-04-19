"""Tests for AnkiConnect note submission and auto-model creation behavior."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import autofiller.anki_connect_client as anki_client
from autofiller.anki_connect_client import add_rows_to_anki
from autofiller.models import CardRow


class AnkiConnectClientTests(unittest.TestCase):
    """Validate model bootstrap and add-notes behavior for vocabulary rows."""

    def setUp(self) -> None:
        anki_client._VOCAB_DECK_CONFIG_ID = None

    def test_add_rows_skips_model_creation_when_model_exists(self) -> None:
        """Existing model should be reused and templates synced without createModel."""
        calls: list[tuple[str, dict]] = []

        def fake_invoke(url: str, action: str, params: dict) -> object:
            calls.append((action, params))
            if action == "modelNames":
                return ["Jisho2Anki::Vocab"]
            if action == "modelTemplates":
                return {
                    "Word -> Reading+Translation": {
                        "Front": "legacy-front-1",
                        "Back": "legacy-back-1",
                    },
                    "Word+Reading -> Translation": {
                        "Front": "legacy-front-2",
                        "Back": "legacy-back-2",
                    },
                }
            if action == "deckNames":
                return ["Example"]
            if action == "getDeckConfig":
                return {
                    "id": 1,
                    "name": "Default",
                    "new": {"perDay": 30},
                    "rev": {"perDay": 500},
                }
            if action == "cloneDeckConfigId":
                return 99
            if action == "saveDeckConfig":
                return True
            if action == "updateModelTemplates":
                return None
            if action == "updateModelStyling":
                return None
            if action == "createDeck":
                return 1
            if action == "setDeckConfigId":
                return True
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
        self.assertIn("modelTemplates", actions)
        self.assertIn("deckNames", actions)
        self.assertIn("getDeckConfig", actions)
        self.assertIn("cloneDeckConfigId", actions)
        self.assertIn("saveDeckConfig", actions)
        self.assertIn("setDeckConfigId", actions)
        self.assertIn("updateModelTemplates", actions)
        self.assertIn("updateModelStyling", actions)
        self.assertIn("createDeck", actions)
        self.assertIn("addNotes", actions)

        update_templates_calls = [
            params for action, params in calls if action == "updateModelTemplates"
        ]
        self.assertEqual(len(update_templates_calls), 1)
        templates = update_templates_calls[0]["model"]["templates"]
        self.assertIn("Word+Reading -> Translation", templates)
        self.assertIn(
            '<div class="meaning">{{Translation}}</div>',
            templates["Word+Reading -> Translation"]["Front"],
        )
        self.assertIn(
            '<div class="word">{{Word}}</div>',
            templates["Word+Reading -> Translation"]["Back"],
        )
        self.assertIn(
            '<div class="reading">{{Reading}}</div>',
            templates["Word+Reading -> Translation"]["Back"],
        )

        deck_config_calls = [
            params for action, params in calls if action == "setDeckConfigId"
        ]
        self.assertEqual(len(deck_config_calls), 1)
        self.assertEqual(deck_config_calls[0]["decks"], ["Example"])
        self.assertEqual(deck_config_calls[0]["configId"], 99)

        saved_config_calls = [
            params for action, params in calls if action == "saveDeckConfig"
        ]
        self.assertEqual(len(saved_config_calls), 1)
        saved_config = saved_config_calls[0]["config"]
        self.assertEqual(saved_config["name"], "Jisho2Anki::Shared Deck Options")
        self.assertEqual(saved_config["new"]["perDay"], 20)
        self.assertEqual(saved_config["rev"]["perDay"], 200)

    def test_add_rows_creates_vocab_model_when_missing(self) -> None:
        """Missing model should be created with expected field order and templates."""
        calls: list[tuple[str, dict]] = []

        def fake_invoke(url: str, action: str, params: dict) -> object:
            calls.append((action, params))
            if action == "modelNames":
                return []
            if action == "deckNames":
                return []
            if action == "getDeckConfig":
                return {
                    "id": 1,
                    "name": "Default",
                    "new": {"perDay": 30},
                    "rev": {"perDay": 500},
                }
            if action == "cloneDeckConfigId":
                return 100
            if action == "saveDeckConfig":
                return True
            if action == "createModel":
                return True
            if action == "createDeck":
                return 1
            if action == "setDeckConfigId":
                return True
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

        self.assertIn("setDeckConfigId", [action for action, _params in calls])
        self.assertIn(
            '<div class="reading">{{Reading}}</div>',
            create_model_params["cardTemplates"][1]["Back"],
        )


if __name__ == "__main__":
    unittest.main()
