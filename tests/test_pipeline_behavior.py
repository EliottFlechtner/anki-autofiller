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
    def test_format_sentences_empty(self) -> None:
        self.assertEqual(format_sentences([]), "")

    def test_format_sentences_join(self) -> None:
        sentences = [
            ExampleSentence(japanese="食べる。", english="I eat."),
            ExampleSentence(japanese="勉強する。", english="I study."),
        ]
        formatted = format_sentences(sentences)
        self.assertIn("例文: 食べる。 - I eat.", formatted)
        self.assertIn("例文: 勉強する。 - I study.", formatted)
        self.assertIn("<br>", formatted)

    def test_default_interactive_selector_handles_retry_and_zero(self) -> None:
        candidates = [
            SearchCandidate(meaning="m1", reading="r1"),
            SearchCandidate(meaning="m2", reading="r2"),
        ]

        with patch("builtins.input", side_effect=["x", "0"]):
            selected = default_interactive_selector("word", candidates)

        self.assertEqual(selected.meaning, "")
        self.assertEqual(selected.reading, "")

    def test_build_word_result_respects_sentence_and_pitch_toggles(self) -> None:
        candidates = [SearchCandidate(meaning="eat", reading="たべる")]
        sentences = [ExampleSentence(japanese="パンを食べる。", english="I eat bread.")]

        with (
            patch(
                "autofiller.pipeline.JishoClient.search",
                return_value=(candidates, sentences),
            ),
            patch(
                "autofiller.pipeline.enrich_html_with_pitch",
                return_value="<!-- accent_start --><svg></svg><!-- accent_end -->",
            ),
        ):
            row, sentence_rows, reading, plain_meaning = _build_word_result(
                word="食べる",
                candidate_limit=3,
                sentence_count=2,
                include_sentences=False,
                separate_sentence_cards=False,
                include_pitch_accent=True,
                interactive_review=False,
                selector=lambda _word, cands: cands[0],
            )

        self.assertEqual(plain_meaning, "eat")
        self.assertEqual(row.meaning, "eat")
        self.assertIn("<svg>", row.reading)
        self.assertEqual(sentence_rows, [])
        self.assertIn("<svg>", reading)

    def test_build_word_result_creates_separate_sentence_cards(self) -> None:
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
                interactive_review=False,
                selector=lambda _word, cands: cands[0],
            )

        self.assertEqual(row.meaning, "match")
        self.assertEqual(len(sentence_rows), 1)
        self.assertIn("Word: 試合", sentence_rows[0].back)

    def test_build_rows_preserves_input_order(self) -> None:
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
                max_workers=3,
                interactive_review=False,
                progress_printer=None,
            )

        self.assertEqual([row.word for row in rows], ["a", "b", "c"])
        self.assertEqual(
            [row.meaning for row in rows], ["meaning-a", "meaning-b", "meaning-c"]
        )

    def test_build_rows_sequential_progress_and_sleep(self) -> None:
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
                max_workers=1,
                interactive_review=False,
                progress_printer=logs.append,
            )

        self.assertEqual([row.word for row in rows], ["x", "y"])
        self.assertEqual(len(logs), 2)
        sleep_mock.assert_called()

    def test_build_rows_interactive_uses_selector(self) -> None:
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
                max_workers=4,
                interactive_review=True,
                selector=lambda _word, cands: cands[1],
                progress_printer=None,
            )

        self.assertEqual(rows[0].meaning, "second")
        self.assertEqual(rows[0].reading, "s")
        self.assertEqual(sentence_rows, [])


if __name__ == "__main__":
    unittest.main()
