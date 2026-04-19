"""Tests for Jisho HTML sentence extraction behavior."""

from __future__ import annotations

import unittest

from autofiller.jisho_client import JishoClient


class JishoSentenceExtractionTests(unittest.TestCase):
    """Validate sentence extraction and cleanup from Jisho HTML snippets."""

    def test_extract_sentences_strips_trailing_source_citation(self) -> None:
        """Trailing source labels like '— Jreibun' should be removed from English text."""
        client = JishoClient()
        html_payload = """
        <ul class="japanese_sentence clearfix">
          <li><span class="unlinked">おはようございます</span></li>
        </ul>
        <div class="english_sentence clearfix">
          <li><span class="english">Good morning. — Jreibun</span></li>
        </div>
        """

        sentences = client._extract_sentences(html_payload, limit=3)
        self.assertEqual(len(sentences), 1)
        self.assertEqual(sentences[0].japanese, "おはようございます")
        self.assertEqual(sentences[0].english, "Good morning.")


if __name__ == "__main__":
    unittest.main()
