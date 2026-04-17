"""Tests for furigana annotation helper."""

from __future__ import annotations

import unittest

from autofiller.furigana import add_furigana


class FuriganaTests(unittest.TestCase):
    """Validate ruby/anki furigana rendering behavior."""

    def test_add_furigana_ruby_with_okurigana(self) -> None:
        """Kanji + okurigana words should get ruby markup on kanji groups."""
        rendered = add_furigana("食べる", "たべる", fmt="ruby")

        self.assertIn("<ruby>", rendered)
        self.assertIn("<rt>た</rt>", rendered)
        self.assertTrue(rendered.endswith("べる"))

    def test_add_furigana_anki_format(self) -> None:
        """Anki format should use `base[reading]` style markup."""
        rendered = add_furigana("食べる", "たべる", fmt="anki")
        self.assertEqual(rendered, "食[た]べる")

    def test_add_furigana_no_kanji_returns_plain_text(self) -> None:
        """Kana-only expressions should be left unchanged."""
        rendered = add_furigana("たべる", "たべる", fmt="ruby")
        self.assertEqual(rendered, "たべる")


if __name__ == "__main__":
    unittest.main()
