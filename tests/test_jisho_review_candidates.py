"""Tests for review candidate extraction behavior in Jisho client."""

from __future__ import annotations

import json
import unittest

from autofiller.jisho_client import JishoClient


class JishoReviewCandidateTests(unittest.TestCase):
    """Validate exact-entry sense extraction and related-entry recommendation split."""

    def test_review_candidates_use_exact_entry_senses(self) -> None:
        """Exact entry senses should be options; compounds should be related words."""
        payload = {
            "data": [
                {
                    "japanese": [{"word": "団地", "reading": "だんち"}],
                    "senses": [
                        {
                            "english_definitions": [
                                "multi-unit apartments",
                                "apartment complex",
                            ]
                        },
                        {"english_definitions": ["Danchi"]},
                    ],
                },
                {
                    "japanese": [{"word": "団地住まい", "reading": "だんちずまい"}],
                    "senses": [
                        {"english_definitions": ["living in a housing complex"]}
                    ],
                },
                {
                    "japanese": [{"word": "団地族", "reading": "だんちぞく"}],
                    "senses": [{"english_definitions": ["housing project dwellers"]}],
                },
            ]
        }

        client = JishoClient()
        options, related = client._extract_review_candidates(
            json.dumps(payload), query="団地", limit=3
        )

        self.assertEqual(len(options), 2)
        self.assertEqual(options[0].reading, "だんち")
        self.assertIn("multi-unit apartments", options[0].meaning)
        self.assertIn("Danchi", options[1].meaning)

        self.assertEqual(len(related), 2)
        self.assertEqual(related[0]["word"], "団地住まい")
        self.assertEqual(related[1]["word"], "団地族")

    def test_review_candidates_include_multiple_exact_entries(self) -> None:
        """All exact-match entries should be options before compound related words."""
        payload = {
            "data": [
                {
                    "japanese": [{"word": "中", "reading": "ちゅう"}],
                    "senses": [
                        {"english_definitions": ["middle", "medium"]},
                        {"english_definitions": ["during", "while"]},
                    ],
                },
                {
                    "japanese": [{"word": "中", "reading": "なか"}],
                    "senses": [
                        {"english_definitions": ["inside", "interior"]},
                    ],
                },
                {
                    "japanese": [{"word": "中学校", "reading": "ちゅうがっこう"}],
                    "senses": [
                        {"english_definitions": ["junior high school"]},
                    ],
                },
            ]
        }

        client = JishoClient()
        options, related = client._extract_review_candidates(
            json.dumps(payload), query="中", limit=3
        )

        self.assertEqual(len(options), 3)
        self.assertEqual(options[0].reading, "ちゅう")
        self.assertEqual(options[1].reading, "ちゅう")
        self.assertEqual(options[2].reading, "なか")
        self.assertEqual(len(related), 1)
        self.assertEqual(related[0]["word"], "中学校")

    def test_review_candidates_fallback_when_no_exact_item(self) -> None:
        """When exact item missing, first item should still provide review options."""
        payload = {
            "data": [
                {
                    "japanese": [{"word": "団地住まい", "reading": "だんちずまい"}],
                    "senses": [
                        {"english_definitions": ["living in a housing complex"]}
                    ],
                }
            ]
        }

        client = JishoClient()
        options, related = client._extract_review_candidates(
            json.dumps(payload), query="団地", limit=3
        )

        self.assertEqual(len(options), 1)
        self.assertEqual(options[0].reading, "だんちずまい")
        self.assertIn("living in a housing complex", options[0].meaning)
        self.assertEqual(related, [])


if __name__ == "__main__":
    unittest.main()
