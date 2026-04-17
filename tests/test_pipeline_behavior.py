"""Behavioral tests for row generation, formatting, and interactive selection."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from autofiller.models import CardRow, ExampleSentence, SearchCandidate
from autofiller.pipeline import (
    _build_word_result,
    build_rows,
    default_interactive_selector,
    format_sentences,
)


class PipelineBehaviorTests(unittest.TestCase):
    """Cover pipeline behavior for sentence/pitch options and ordering guarantees."""

    def test_format_sentences_empty(self) -> None:
        """No sentences should yield an empty formatting payload."""
        self.assertEqual(format_sentences([]), "")

    def test_format_sentences_join(self) -> None:
        """Sentence formatting should include all entries separated by `<br>`."""
        sentences = [
            ExampleSentence(japanese="食べる。", english="I eat."),
            ExampleSentence(japanese="勉強する。", english="I study."),
        ]
        formatted = format_sentences(sentences)
        self.assertIn("例文: 食べる。 - I eat.", formatted)
        self.assertIn("例文: 勉強する。 - I study.", formatted)
        self.assertIn("<br>", formatted)

    def test_default_interactive_selector_handles_retry_and_zero(self) -> None:
        """Selector should retry invalid input and allow explicit blank selection via `0`."""
        candidates = [
            SearchCandidate(meaning="m1", reading="r1"),
            SearchCandidate(meaning="m2", reading="r2"),
        ]

        with patch("builtins.input", side_effect=["x", "0"]):
            selected = default_interactive_selector("word", candidates)

        self.assertEqual(selected.meaning, "")
        self.assertEqual(selected.reading, "")

    def test_build_word_result_respects_sentence_and_pitch_toggles(self) -> None:
        """Word result should honor sentence inclusion and pitch-accent toggles."""
        candidates = [SearchCandidate(meaning="eat", reading="たべる")]
        sentences = [ExampleSentence(japanese="パンを食べる。", english="I eat bread.")]
        pitch_html = "<!-- accent_start --><svg></svg><!-- accent_end -->"

        with (
            patch(
                "autofiller.pipeline.JishoClient.search",
                return_value=(candidates, sentences),
            ),
            patch(
                "autofiller.pipeline.enrich_html_with_pitch",
                return_value=pitch_html,
            ),
        ):
            row, sentence_rows, reading, plain_meaning = _build_word_result(
                word="食べる",
                candidate_limit=3,
                sentence_count=2,
                include_sentences=False,
                separate_sentence_cards=False,
                include_pitch_accent=True,
                pitch_accent_theme="dark",
                include_furigana=False,
                furigana_format="ruby",
                interactive_review=False,
                selector=lambda _word, cands: cands[0],
            )

        self.assertEqual(plain_meaning, "eat")
        self.assertEqual(row.meaning, "eat")
        self.assertEqual(row.reading, pitch_html)
        self.assertEqual(reading, pitch_html)
        self.assertEqual(sentence_rows, [])

    def test_build_word_result_normalizes_katakana_reading_to_hiragana(self) -> None:
        """Readings should be normalized to hiragana-only text when pitch mode is off."""
        candidates = [SearchCandidate(meaning="coffee", reading="コーヒー")]

        with patch(
            "autofiller.pipeline.JishoClient.search",
            return_value=(candidates, []),
        ):
            row, _sentence_rows, reading, _plain_meaning = _build_word_result(
                word="珈琲",
                candidate_limit=3,
                sentence_count=0,
                include_sentences=False,
                separate_sentence_cards=False,
                include_pitch_accent=False,
                pitch_accent_theme="dark",
                include_furigana=False,
                furigana_format="ruby",
                interactive_review=False,
                selector=lambda _word, cands: cands[0],
            )

        self.assertEqual(row.reading, "こーひー")
        self.assertEqual(reading, "こーひー")

    def test_build_word_result_creates_separate_sentence_cards(self) -> None:
        """Separate sentence card mode should emit companion `SentenceCardRow` entries."""
        candidates = [SearchCandidate(meaning="match", reading="しあい")]
        sentences = [ExampleSentence(japanese="試合だ。", english="It is a match.")]

        with patch(
            "autofiller.pipeline.JishoClient.search",
            return_value=(candidates, sentences),
        ):
            row, sentence_rows, _reading, _plain_meaning = _build_word_result(
                word="試合",
                candidate_limit=3,
                sentence_count=2,
                include_sentences=True,
                separate_sentence_cards=True,
                include_pitch_accent=False,
                pitch_accent_theme="dark",
                include_furigana=False,
                furigana_format="ruby",
                interactive_review=False,
                selector=lambda _word, cands: cands[0],
            )

        self.assertEqual(row.meaning, "match")
        self.assertEqual(len(sentence_rows), 1)
        self.assertIn("Word: 試合", sentence_rows[0].back)

    def test_build_rows_preserves_input_order(self) -> None:
        """Parallel builds should still preserve original input order in final rows."""

        def fake_build_word_result(*, word, **_kwargs):
            return (
                CardRow(
                    word=word, meaning=f"meaning-{word}", reading=f"reading-{word}"
                ),
                [],
                f"reading-{word}",
                f"meaning-{word}",
            )

        with patch(
            "autofiller.pipeline._build_word_result", side_effect=fake_build_word_result
        ):
            rows, _sentence_rows = build_rows(
                words=["a", "b", "c"],
                pause_seconds=0,
                candidate_limit=2,
                sentence_count=0,
                include_sentences=False,
                separate_sentence_cards=False,
                include_pitch_accent=False,
                pitch_accent_theme="dark",
                include_furigana=False,
                furigana_format="ruby",
                max_workers=3,
                interactive_review=False,
                progress_printer=None,
            )

        self.assertEqual([row.word for row in rows], ["a", "b", "c"])
        self.assertEqual(
            [row.meaning for row in rows], ["meaning-a", "meaning-b", "meaning-c"]
        )

    def test_build_rows_sequential_progress_and_sleep(self) -> None:
        """Sequential mode should emit progress and respect pause-based sleeping."""

        def fake_build_word_result(*, word, **_kwargs):
            return (
                CardRow(word=word, meaning=f"m-{word}", reading=f"r-{word}"),
                [],
                f"r-{word}",
                f"m-{word}",
            )

        logs: list[str] = []
        with (
            patch(
                "autofiller.pipeline._build_word_result",
                side_effect=fake_build_word_result,
            ),
            patch("autofiller.pipeline.time.sleep") as sleep_mock,
        ):
            rows, _ = build_rows(
                words=["x", "y"],
                pause_seconds=0.2,
                candidate_limit=2,
                sentence_count=0,
                include_sentences=False,
                separate_sentence_cards=False,
                include_pitch_accent=False,
                pitch_accent_theme="dark",
                include_furigana=False,
                furigana_format="ruby",
                max_workers=1,
                interactive_review=False,
                progress_printer=logs.append,
            )

        self.assertEqual([row.word for row in rows], ["x", "y"])
        self.assertEqual(len(logs), 2)
        sleep_mock.assert_called()

    def test_build_rows_interactive_uses_selector(self) -> None:
        """Interactive mode should defer candidate choice to the injected selector."""
        candidates = [
            SearchCandidate(meaning="first", reading="f"),
            SearchCandidate(meaning="second", reading="s"),
        ]
        sentences = [ExampleSentence(japanese="文", english="sentence")]

        with patch(
            "autofiller.pipeline.JishoClient.search",
            return_value=(candidates, sentences),
        ):
            rows, sentence_rows = build_rows(
                words=["語"],
                pause_seconds=0,
                candidate_limit=2,
                sentence_count=1,
                include_sentences=False,
                separate_sentence_cards=False,
                include_pitch_accent=False,
                pitch_accent_theme="dark",
                include_furigana=False,
                furigana_format="ruby",
                max_workers=4,
                interactive_review=True,
                selector=lambda _word, cands: cands[1],
                progress_printer=None,
            )

        self.assertEqual(rows[0].meaning, "second")
        self.assertEqual(rows[0].reading, "s")
        self.assertEqual(sentence_rows, [])

    def test_build_word_result_applies_furigana_markup(self) -> None:
        """Furigana mode should annotate the word field when reading is available."""
        candidates = [SearchCandidate(meaning="eat", reading="たべる")]

        with patch(
            "autofiller.pipeline.JishoClient.search",
            return_value=(candidates, []),
        ):
            row, _sentence_rows, _reading, _plain_meaning = _build_word_result(
                word="食べる",
                candidate_limit=3,
                sentence_count=0,
                include_sentences=False,
                separate_sentence_cards=False,
                include_pitch_accent=False,
                pitch_accent_theme="dark",
                include_furigana=True,
                furigana_format="ruby",
                interactive_review=False,
                selector=lambda _word, cands: cands[0],
            )

        self.assertIn("<ruby>", row.word)
        self.assertIn("<rt>た</rt>", row.word)

    def test_build_word_result_passes_pitch_theme(self) -> None:
        """Pitch rendering should forward the selected SVG theme option."""
        candidates = [SearchCandidate(meaning="rain", reading="あめ")]

        with (
            patch(
                "autofiller.pipeline.JishoClient.search",
                return_value=(candidates, []),
            ),
            patch(
                "autofiller.pipeline.enrich_html_with_pitch",
                return_value=None,
            ) as pitch_mock,
        ):
            _build_word_result(
                word="雨",
                candidate_limit=3,
                sentence_count=0,
                include_sentences=False,
                separate_sentence_cards=False,
                include_pitch_accent=True,
                pitch_accent_theme="light",
                include_furigana=False,
                furigana_format="ruby",
                interactive_review=False,
                selector=lambda _word, cands: cands[0],
            )

        pitch_mock.assert_called_once_with("雨", "あめ", theme="light")


if __name__ == "__main__":
    unittest.main()
