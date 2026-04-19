"""Integration-style tests for Flask API endpoints and async job wiring."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from autofiller.models import CardRow, SearchCandidate, SentenceCardRow

try:
    from autofiller import web_app as web_app_module

    _WEB_APP_IMPORT_ERROR = None
except ModuleNotFoundError as exc:
    web_app_module = None  # type: ignore[assignment]
    _WEB_APP_IMPORT_ERROR = exc


@unittest.skipIf(
    _WEB_APP_IMPORT_ERROR is not None,
    "Flask dependency missing for web_app tests. Install requirements or run make test-docker.",
)
class WebApiEndpointTests(unittest.TestCase):
    """Verify API contracts for health, bootstrap, settings, and job lifecycle."""

    def test_healthz(self) -> None:
        """Health endpoint should return a minimal ok payload."""
        app = web_app_module.app
        with app.test_client() as client:
            response = client.get("/healthz")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"status": "ok"})

    def test_bootstrap_returns_defaults_and_presets(self) -> None:
        """Bootstrap endpoint should expose defaults and preset names for the SPA."""
        app = web_app_module.app

        with (
            app.test_client() as client,
            patch(
                "autofiller.web_app.load_settings",
                return_value={"output_path": "x.tsv"},
            ),
            patch(
                "autofiller.web_app.available_presets",
                return_value=["balanced", "safe-api"],
            ),
        ):
            response = client.get("/api/bootstrap")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["defaults"]["output_path"], "x.tsv")
        self.assertEqual(payload["presets"], ["balanced", "safe-api"])

    def test_settings_preview_uses_request_preset_and_env(self) -> None:
        """Settings preview should forward request preset/env values into loader."""
        app = web_app_module.app

        with (
            app.test_client() as client,
            patch(
                "autofiller.web_app.load_settings",
                return_value={"include_sentences": False, "include_pitch_accent": True},
            ) as load_settings_mock,
            patch("autofiller.web_app.available_presets", return_value=["balanced"]),
        ):
            response = client.post(
                "/api/settings-preview",
                data={"preset": "balanced", "env_file": "configs/dev.env"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["preset"], "balanced")
        self.assertEqual(payload["env_file"], "configs/dev.env")
        self.assertIn("settings", payload)
        load_settings_mock.assert_called_with(
            preset_name="balanced",
            env_file="configs/dev.env",
        )

    def test_anki_options_returns_models_and_decks(self) -> None:
        """Anki options endpoint should expose model/deck names for dropdowns."""
        app = web_app_module.app

        with (
            app.test_client() as client,
            patch(
                "autofiller.web_app.invoke",
                side_effect=[
                    ["Jisho2Anki::Vocab", "Basic"],
                    ["Default", "Keio::TestApp"],
                ],
            ),
        ):
            response = client.get(
                "/api/anki-options", query_string={"anki_url": "http://127.0.0.1:8765"}
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertIn("Jisho2Anki::Vocab", payload["models"])
        self.assertIn("Keio::TestApp", payload["decks"])

    def test_anki_options_handles_ankiconnect_error(self) -> None:
        """Anki options endpoint should report connection failures gracefully."""
        app = web_app_module.app

        with (
            app.test_client() as client,
            patch(
                "autofiller.web_app.invoke",
                side_effect=RuntimeError("connection failed"),
            ),
        ):
            response = client.get("/api/anki-options")

        self.assertEqual(response.status_code, 502)
        payload = response.get_json()
        self.assertEqual(payload["models"], [])
        self.assertEqual(payload["decks"], [])
        self.assertIn("connection failed", payload["error"])

    def test_generate_route_returns_410(self) -> None:
        """Legacy route should stay explicitly disabled with HTTP 410."""
        app = web_app_module.app
        with app.test_client() as client:
            response = client.post("/generate")

        self.assertEqual(response.status_code, 410)
        payload = response.get_json()
        self.assertIn("Legacy /generate route", payload["error"])

    def test_start_and_status_with_synchronous_thread(self) -> None:
        """Job start/status should complete in-process when thread is patched immediate."""
        app = web_app_module.app

        class _ImmediateThread:
            """Thread test double that runs target synchronously in `start()`."""

            def __init__(self, target, args, daemon):
                self._target = target
                self._args = args
                self.daemon = daemon

            def start(self):
                self._target(*self._args)

        fake_result = {
            "rows": [CardRow(word="食べる", meaning="eat", reading="たべる")],
            "output_path": "output/test.tsv",
            "message": "Generated 1 rows.",
            "anki_summary": "",
            "preset": "",
            "env_file": "",
        }

        with (
            app.test_client() as client,
            patch("autofiller.web_app.threading.Thread", _ImmediateThread),
            patch("autofiller.web_app._build_from_form", return_value=fake_result),
        ):
            start_resp = client.post("/api/start", data={"words": "食べる"})
            self.assertEqual(start_resp.status_code, 200)
            job_id = start_resp.get_json()["job_id"]

            status_resp = client.get(f"/api/status/{job_id}")
            self.assertEqual(status_resp.status_code, 200)
            payload = status_resp.get_json()
            self.assertEqual(payload["status"], "done")
            self.assertEqual(payload["message"], "Generated 1 rows.")
            self.assertEqual(payload["output_path"], "output/test.tsv")
            self.assertTrue(payload["preview"])

    def test_start_and_status_error_path(self) -> None:
        """Failed build jobs should transition into the `error` status payload."""
        app = web_app_module.app

        class _ImmediateThread:
            """Thread test double that runs target synchronously in `start()`."""

            def __init__(self, target, args, daemon):
                self._target = target
                self._args = args
                self.daemon = daemon

            def start(self):
                self._target(*self._args)

        with (
            app.test_client() as client,
            patch("autofiller.web_app.threading.Thread", _ImmediateThread),
            patch(
                "autofiller.web_app._build_from_form",
                side_effect=ValueError("boom"),
            ),
        ):
            start_resp = client.post("/api/start", data={"words": "食べる"})
            self.assertEqual(start_resp.status_code, 200)
            job_id = start_resp.get_json()["job_id"]

            status_resp = client.get(f"/api/status/{job_id}")
            self.assertEqual(status_resp.status_code, 200)
            payload = status_resp.get_json()
            self.assertEqual(payload["status"], "error")
            self.assertEqual(payload["error"], "boom")

    def test_status_not_found(self) -> None:
        """Unknown job IDs should return 404 with a stable error shape."""
        app = web_app_module.app
        with app.test_client() as client:
            response = client.get("/api/status/does-not-exist")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json()["error"], "job not found")

    def test_status_hides_pending_add_payload(self) -> None:
        """Status responses should not expose internal pending add payload internals."""
        app = web_app_module.app
        job_id = "job-with-pending"

        with web_app_module.JOB_LOCK:
            web_app_module.JOBS[job_id] = {
                "status": "done",
                "pending_add": {
                    "rows": [{"word": "x", "meaning": "m", "reading": "r"}]
                },
                "requires_confirmation": True,
            }

        try:
            with app.test_client() as client:
                response = client.get(f"/api/status/{job_id}")
            self.assertEqual(response.status_code, 200)
            payload = response.get_json()
            self.assertNotIn("pending_add", payload)
        finally:
            with web_app_module.JOB_LOCK:
                web_app_module.JOBS.pop(job_id, None)

    def test_confirm_add_executes_pending_submission(self) -> None:
        """Confirm endpoint should submit pending reviewed rows and clear confirmation state."""
        app = web_app_module.app
        job_id = "job-confirm"

        pending_add = {
            "rows": [{"word": "食べる", "meaning": "eat", "reading": "たべる"}],
            "sentence_rows": [{"front": "文", "back": "sentence"}],
            "separate_sentence_cards": True,
            "anki_url": "http://127.0.0.1:8765",
            "deck_name": "Example",
            "model_name": "Jisho2Anki::Vocab",
            "field_word": "Word",
            "field_meaning": "Translation",
            "field_reading": "Reading",
            "tags": ["jp"],
            "allow_duplicates": False,
            "sentence_deck_name": "Example::Sentences",
            "sentence_model_name": "Basic",
            "sentence_front_field": "Front",
            "sentence_back_field": "Back",
        }

        with web_app_module.JOB_LOCK:
            web_app_module.JOBS[job_id] = {
                "status": "done",
                "requires_confirmation": True,
                "pending_add": pending_add,
                "anki_summary": "",
            }

        try:
            with (
                app.test_client() as client,
                patch("autofiller.web_app.add_rows_to_anki", return_value=(1, 0)),
                patch(
                    "autofiller.web_app.add_sentence_rows_to_anki",
                    return_value=(1, 0),
                ),
            ):
                response = client.post(f"/api/confirm/{job_id}")

            self.assertEqual(response.status_code, 200)
            payload = response.get_json()
            self.assertIn("Added 1 note(s) to Anki.", payload["anki_summary"])

            with web_app_module.JOB_LOCK:
                job = web_app_module.JOBS[job_id]
            self.assertFalse(job["requires_confirmation"])
            self.assertIsNone(job["pending_add"])
        finally:
            with web_app_module.JOB_LOCK:
                web_app_module.JOBS.pop(job_id, None)

    def test_confirm_add_blocks_invalid_rows_without_skip_mode(self) -> None:
        """Confirm endpoint should reject invalid rows when skip mode is disabled."""
        app = web_app_module.app
        job_id = "job-confirm-invalid-block"

        pending_add = {
            "rows": [
                {"word": "A", "meaning": "good", "reading": "read-A"},
                {"word": "B", "meaning": "", "reading": ""},
            ],
            "sentence_rows": [],
            "review_items": [],
            "separate_sentence_cards": False,
            "anki_url": "http://127.0.0.1:8765",
            "deck_name": "Example",
            "model_name": "Jisho2Anki::Vocab",
            "field_word": "Word",
            "field_meaning": "Translation",
            "field_reading": "Reading",
            "tags": ["jp"],
            "allow_duplicates": False,
        }

        with web_app_module.JOB_LOCK:
            web_app_module.JOBS[job_id] = {
                "status": "done",
                "requires_confirmation": True,
                "pending_add": pending_add,
                "anki_summary": "",
            }

        try:
            with (
                app.test_client() as client,
                patch("autofiller.web_app.add_rows_to_anki") as add_rows_mock,
            ):
                response = client.post(
                    f"/api/confirm/{job_id}",
                    json={"only_add_valid_rows": False},
                )

            self.assertEqual(response.status_code, 400)
            payload = response.get_json()
            self.assertIn("validation failed", payload["error"])
            self.assertTrue(payload["validation"]["rows"])
            add_rows_mock.assert_not_called()

            with web_app_module.JOB_LOCK:
                job = web_app_module.JOBS[job_id]
            self.assertTrue(job["requires_confirmation"])
        finally:
            with web_app_module.JOB_LOCK:
                web_app_module.JOBS.pop(job_id, None)

    def test_confirm_add_only_valid_rows_skips_invalid_with_summary(self) -> None:
        """Confirm endpoint should submit only valid rows and report skipped invalid rows."""
        app = web_app_module.app
        job_id = "job-confirm-skip-invalid"

        pending_add = {
            "rows": [
                {"word": "A", "meaning": "good", "reading": "read-A"},
                {"word": "B", "meaning": "", "reading": ""},
            ],
            "sentence_rows": [],
            "review_items": [],
            "separate_sentence_cards": False,
            "anki_url": "http://127.0.0.1:8765",
            "deck_name": "Example",
            "model_name": "Jisho2Anki::Vocab",
            "field_word": "Word",
            "field_meaning": "Translation",
            "field_reading": "Reading",
            "tags": ["jp"],
            "allow_duplicates": False,
        }

        with web_app_module.JOB_LOCK:
            web_app_module.JOBS[job_id] = {
                "status": "done",
                "requires_confirmation": True,
                "pending_add": pending_add,
                "anki_summary": "",
            }

        captured_rows: list[CardRow] = []

        def _capture_rows(rows, **_kwargs):
            captured_rows.extend(rows)
            return (len(rows), 0)

        try:
            with (
                app.test_client() as client,
                patch("autofiller.web_app.add_rows_to_anki", side_effect=_capture_rows),
            ):
                response = client.post(
                    f"/api/confirm/{job_id}",
                    json={"only_add_valid_rows": True},
                )

            self.assertEqual(response.status_code, 200)
            payload = response.get_json()
            self.assertEqual(len(captured_rows), 1)
            self.assertEqual(captured_rows[0].word, "A")
            self.assertIn("Skipped 1 invalid row(s)", payload["anki_summary"])
            self.assertEqual(payload["skipped_rows"], 1)
            self.assertIn("missing meaning", payload["skipped_reasons"])
            self.assertIn("missing reading", payload["skipped_reasons"])

            with web_app_module.JOB_LOCK:
                job = web_app_module.JOBS[job_id]
            self.assertFalse(job["requires_confirmation"])
            self.assertIsNone(job["pending_add"])
        finally:
            with web_app_module.JOB_LOCK:
                web_app_module.JOBS.pop(job_id, None)

    def test_review_add_word_appends_once_and_updates_pending_payload(self) -> None:
        """Add-word endpoint should append exactly one review item/row and persist it."""
        app = web_app_module.app
        job_id = "job-add-word"

        pending_add = {
            "rows": [{"word": "A", "meaning": "mean-A", "reading": "read-A"}],
            "sentence_rows": [],
            "review_items": [
                {
                    "word": "A",
                    "source_word": "A",
                    "options": [
                        {
                            "meaning": "mean-A",
                            "reading": "read-A",
                            "reading_preview": "read-A",
                        }
                    ],
                    "related_words": [],
                    "selected_index": 0,
                }
            ],
            "source_words": ["A"],
            "candidate_limit": 3,
            "include_pitch_accent": True,
            "pitch_accent_theme": "dark",
            "separate_sentence_cards": False,
            "anki_url": "http://127.0.0.1:8765",
            "deck_name": "Example",
            "model_name": "Jisho2Anki::Vocab",
            "field_word": "Word",
            "field_meaning": "Translation",
            "field_reading": "Reading",
            "tags": ["jp"],
            "allow_duplicates": False,
        }

        with web_app_module.JOB_LOCK:
            web_app_module.JOBS[job_id] = {
                "status": "done",
                "requires_confirmation": True,
                "pending_add": pending_add,
                "review_items": [
                    {
                        "word": "A",
                        "source_word": "A",
                        "options": [
                            {
                                "meaning": "mean-A",
                                "reading": "read-A",
                                "reading_preview": "read-A",
                            }
                        ],
                        "related_words": [],
                        "selected_index": 0,
                    }
                ],
            }

        new_review_item = {
            "word": "B",
            "source_word": "B",
            "options": [
                {
                    "meaning": "mean-B",
                    "reading": "read-B",
                    "reading_preview": "<svg>pitch-B</svg>",
                }
            ],
            "related_words": [],
            "selected_index": 0,
        }

        try:
            with (
                app.test_client() as client,
                patch(
                    "autofiller.web_app._build_review_items",
                    return_value=[new_review_item],
                ),
            ):
                response = client.post(
                    f"/api/review-add-word/{job_id}",
                    json={"word": "B"},
                )

            self.assertEqual(response.status_code, 200)
            payload = response.get_json()
            self.assertEqual(payload["review_item"]["word"], "B")

            with web_app_module.JOB_LOCK:
                job = web_app_module.JOBS[job_id]
                updated_pending = job["pending_add"]

            self.assertEqual(len(updated_pending["rows"]), 2)
            self.assertEqual(updated_pending["rows"][1]["word"], "B")
            self.assertEqual(updated_pending["rows"][1]["meaning"], "mean-B")
            self.assertEqual(
                updated_pending["rows"][1]["reading"], "<svg>pitch-B</svg>"
            )
            self.assertEqual(updated_pending["source_words"], ["A", "B"])
            self.assertEqual(len(updated_pending["review_items"]), 2)
            self.assertEqual(len(job["review_items"]), 2)
        finally:
            with web_app_module.JOB_LOCK:
                web_app_module.JOBS.pop(job_id, None)

    def test_review_add_word_rejects_duplicate_source_word(self) -> None:
        """Add-word endpoint should reject words already present in source_words."""
        app = web_app_module.app
        job_id = "job-add-duplicate"

        with web_app_module.JOB_LOCK:
            web_app_module.JOBS[job_id] = {
                "status": "done",
                "requires_confirmation": True,
                "pending_add": {
                    "rows": [],
                    "sentence_rows": [],
                    "review_items": [],
                    "source_words": ["A", "B"],
                    "candidate_limit": 3,
                    "include_pitch_accent": False,
                    "pitch_accent_theme": "dark",
                },
                "review_items": [],
            }

        try:
            with app.test_client() as client:
                response = client.post(
                    f"/api/review-add-word/{job_id}",
                    json={"word": "B"},
                )

            self.assertEqual(response.status_code, 409)
            self.assertIn("already in batch", response.get_json()["error"])
        finally:
            with web_app_module.JOB_LOCK:
                web_app_module.JOBS.pop(job_id, None)

    def test_review_add_word_falls_back_when_no_candidates(self) -> None:
        """Add-word endpoint should still add a blank review item when Jisho has no matches."""
        app = web_app_module.app
        job_id = "job-add-fallback"

        with web_app_module.JOB_LOCK:
            web_app_module.JOBS[job_id] = {
                "status": "done",
                "requires_confirmation": True,
                "pending_add": {
                    "rows": [],
                    "sentence_rows": [],
                    "review_items": [],
                    "source_words": [],
                    "candidate_limit": 3,
                    "include_pitch_accent": False,
                    "pitch_accent_theme": "dark",
                },
                "review_items": [],
            }

        try:
            with (
                app.test_client() as client,
                patch("autofiller.web_app._build_review_items", return_value=[]),
            ):
                response = client.post(
                    f"/api/review-add-word/{job_id}",
                    json={"word": "未登録語"},
                )

            self.assertEqual(response.status_code, 200)
            payload = response.get_json()
            self.assertEqual(payload["selected_index"], 0)
            self.assertEqual(payload["review_item"]["options"][0]["meaning"], "")
            self.assertEqual(payload["review_item"]["options"][0]["reading"], "")

            with web_app_module.JOB_LOCK:
                job = web_app_module.JOBS[job_id]
                updated_pending = job["pending_add"]

            self.assertEqual(updated_pending["rows"][0]["word"], "未登録語")
            self.assertEqual(updated_pending["rows"][0]["meaning"], "")
            self.assertEqual(updated_pending["rows"][0]["reading"], "")
            self.assertEqual(updated_pending["source_words"], ["未登録語"])
        finally:
            with web_app_module.JOB_LOCK:
                web_app_module.JOBS.pop(job_id, None)

    def test_review_add_word_reuses_generation_settings_inline_sentence(self) -> None:
        """Add-word should reuse include-sentences/furigana/pitch settings from original batch."""
        app = web_app_module.app
        job_id = "job-add-settings-inline"

        with web_app_module.JOB_LOCK:
            web_app_module.JOBS[job_id] = {
                "status": "done",
                "requires_confirmation": True,
                "pending_add": {
                    "rows": [],
                    "sentence_rows": [],
                    "review_items": [],
                    "source_words": ["既存語"],
                    "candidate_limit": 5,
                    "sentence_count": 2,
                    "max_workers": 4,
                    "include_sentences": True,
                    "include_pitch_accent": True,
                    "pitch_accent_theme": "light",
                    "include_furigana": True,
                    "furigana_format": "anki",
                    "separate_sentence_cards": False,
                },
                "review_items": [],
            }

        try:
            with (
                app.test_client() as client,
                patch(
                    "autofiller.web_app.build_rows",
                    return_value=(
                        [
                            CardRow(
                                word="語[ご]",
                                meaning="base meaning<br><br>例文: S - E",
                                reading="<svg>ご</svg>",
                            )
                        ],
                        [],
                    ),
                ) as build_rows_mock,
                patch(
                    "autofiller.web_app._build_review_items",
                    return_value=[
                        {
                            "word": "語",
                            "source_word": "語",
                            "options": [
                                {
                                    "meaning": "selected meaning",
                                    "reading": "ご",
                                    "reading_preview": "<svg>ご</svg>",
                                }
                            ],
                            "related_words": [],
                            "selected_index": 0,
                        }
                    ],
                ),
            ):
                response = client.post(
                    f"/api/review-add-word/{job_id}",
                    json={"word": "語"},
                )

            self.assertEqual(response.status_code, 200)
            build_rows_mock.assert_called_once_with(
                words=["語"],
                pause_seconds=0,
                candidate_limit=5,
                sentence_count=2,
                include_sentences=True,
                separate_sentence_cards=False,
                include_pitch_accent=True,
                pitch_accent_theme="light",
                include_furigana=True,
                furigana_format="anki",
                max_workers=4,
                interactive_review=False,
                progress_printer=None,
            )

            with web_app_module.JOB_LOCK:
                updated_pending = web_app_module.JOBS[job_id]["pending_add"]

            self.assertEqual(updated_pending["rows"][0]["word"], "語[ご]")
            self.assertIn("selected meaning", updated_pending["rows"][0]["meaning"])
            self.assertIn("<br><br>例文:", updated_pending["rows"][0]["meaning"])
            self.assertEqual(updated_pending["rows"][0]["reading"], "<svg>ご</svg>")
            self.assertIn("語", updated_pending["source_words"])
        finally:
            with web_app_module.JOB_LOCK:
                web_app_module.JOBS.pop(job_id, None)

    def test_review_add_word_uses_default_sentence_count_when_missing(self) -> None:
        """Add-word should fall back to the configured example-sentence count, not 1."""
        app = web_app_module.app
        job_id = "job-add-default-sentence-count"

        with web_app_module.JOB_LOCK:
            web_app_module.JOBS[job_id] = {
                "status": "done",
                "requires_confirmation": True,
                "pending_add": {
                    "rows": [],
                    "sentence_rows": [],
                    "review_items": [],
                    "source_words": [],
                    "candidate_limit": 3,
                    "include_sentences": True,
                    "include_pitch_accent": False,
                    "pitch_accent_theme": "dark",
                    "include_furigana": False,
                    "furigana_format": "ruby",
                    "separate_sentence_cards": False,
                    "max_workers": 3,
                },
                "review_items": [],
            }

        try:
            with (
                app.test_client() as client,
                patch(
                    "autofiller.web_app.load_settings",
                    return_value={
                        "sentence_count": 2,
                        "max_workers": 3,
                    },
                ),
                patch(
                    "autofiller.web_app.build_rows",
                    return_value=([CardRow(word="語", meaning="m", reading="r")], []),
                ) as build_rows_mock,
                patch(
                    "autofiller.web_app._build_review_items",
                    return_value=[
                        {
                            "word": "語",
                            "source_word": "語",
                            "options": [
                                {
                                    "meaning": "m",
                                    "reading": "r",
                                    "reading_preview": "r",
                                }
                            ],
                            "related_words": [],
                            "selected_index": 0,
                        }
                    ],
                ),
            ):
                response = client.post(
                    f"/api/review-add-word/{job_id}",
                    json={"word": "語"},
                )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(build_rows_mock.call_args.kwargs["sentence_count"], 2)
            self.assertEqual(build_rows_mock.call_args.kwargs["max_workers"], 3)
        finally:
            with web_app_module.JOB_LOCK:
                web_app_module.JOBS.pop(job_id, None)

    def test_review_add_word_appends_separate_sentence_rows(self) -> None:
        """Add-word should append generated separate sentence rows for the new word."""
        app = web_app_module.app
        job_id = "job-add-settings-separate"

        with web_app_module.JOB_LOCK:
            web_app_module.JOBS[job_id] = {
                "status": "done",
                "requires_confirmation": True,
                "pending_add": {
                    "rows": [],
                    "sentence_rows": [],
                    "review_items": [],
                    "source_words": [],
                    "candidate_limit": 3,
                    "sentence_count": 2,
                    "include_sentences": True,
                    "include_pitch_accent": False,
                    "pitch_accent_theme": "dark",
                    "include_furigana": False,
                    "furigana_format": "ruby",
                    "separate_sentence_cards": True,
                },
                "review_items": [],
            }

        try:
            with (
                app.test_client() as client,
                patch(
                    "autofiller.web_app.build_rows",
                    return_value=(
                        [CardRow(word="語", meaning="selected meaning", reading="ご")],
                        [
                            SentenceCardRow(
                                front="文1",
                                back="E1<br><br>Word: 語<br>Reading: ご",
                            ),
                            SentenceCardRow(
                                front="文2",
                                back="E2<br><br>Word: 語<br>Reading: ご",
                            ),
                        ],
                    ),
                ),
                patch(
                    "autofiller.web_app._build_review_items",
                    return_value=[
                        {
                            "word": "語",
                            "source_word": "語",
                            "options": [
                                {
                                    "meaning": "selected meaning",
                                    "reading": "ご",
                                    "reading_preview": "ご",
                                }
                            ],
                            "related_words": [],
                            "selected_index": 0,
                        }
                    ],
                ),
            ):
                response = client.post(
                    f"/api/review-add-word/{job_id}",
                    json={"word": "語"},
                )

            self.assertEqual(response.status_code, 200)
            with web_app_module.JOB_LOCK:
                updated_pending = web_app_module.JOBS[job_id]["pending_add"]

            self.assertEqual(len(updated_pending["sentence_rows"]), 2)
            self.assertEqual(updated_pending["sentence_rows"][0]["front"], "文1")
            self.assertIn("Word: 語", updated_pending["sentence_rows"][0]["back"])
            self.assertEqual(updated_pending["rows"][0]["word"], "語")
        finally:
            with web_app_module.JOB_LOCK:
                web_app_module.JOBS.pop(job_id, None)

    def test_review_add_word_option_parity_matrix(self) -> None:
        """Added review words should always reuse the original generation option set."""
        app = web_app_module.app

        scenarios = [
            {
                "name": "inline-furigana-pitch-dark",
                "include_sentences": True,
                "separate_sentence_cards": False,
                "include_pitch_accent": True,
                "pitch_accent_theme": "dark",
                "include_furigana": True,
                "furigana_format": "anki",
            },
            {
                "name": "separate-no-furigana-pitch-light",
                "include_sentences": True,
                "separate_sentence_cards": True,
                "include_pitch_accent": True,
                "pitch_accent_theme": "light",
                "include_furigana": False,
                "furigana_format": "ruby",
            },
            {
                "name": "plain-no-sentences-no-pitch",
                "include_sentences": False,
                "separate_sentence_cards": False,
                "include_pitch_accent": False,
                "pitch_accent_theme": "dark",
                "include_furigana": False,
                "furigana_format": "ruby",
            },
        ]

        for idx, scenario in enumerate(scenarios):
            job_id = f"job-add-matrix-{idx}"
            with self.subTest(scenario=scenario["name"]):
                with web_app_module.JOB_LOCK:
                    web_app_module.JOBS[job_id] = {
                        "status": "done",
                        "requires_confirmation": True,
                        "pending_add": {
                            "rows": [],
                            "sentence_rows": [],
                            "review_items": [],
                            "source_words": ["初期語"],
                            "candidate_limit": 4,
                            "sentence_count": 2,
                            "include_sentences": scenario["include_sentences"],
                            "include_pitch_accent": scenario["include_pitch_accent"],
                            "pitch_accent_theme": scenario["pitch_accent_theme"],
                            "include_furigana": scenario["include_furigana"],
                            "furigana_format": scenario["furigana_format"],
                            "separate_sentence_cards": scenario[
                                "separate_sentence_cards"
                            ],
                        },
                        "review_items": [],
                    }

                build_rows_calls = []

                def _fake_build_rows(*, words, **kwargs):
                    build_rows_calls.append({"words": list(words), **kwargs})
                    word = str(words[0])
                    # Include inline sentence suffix to verify carry-over handling.
                    generated_row = CardRow(
                        word=f"{word}[よみ]" if scenario["include_furigana"] else word,
                        meaning=(
                            f"base-{word}<br><br>例文: {word} の例文"
                            if scenario["include_sentences"]
                            and not scenario["separate_sentence_cards"]
                            else f"base-{word}"
                        ),
                        reading=(
                            f"<svg data-theme=\"{scenario['pitch_accent_theme']}\" />"
                            if scenario["include_pitch_accent"]
                            else f"reading-{word}"
                        ),
                    )
                    sentence_rows = (
                        [
                            SentenceCardRow(
                                front=f"文-{word}",
                                back=f"EN-{word}<br><br>Word: {word}<br>Reading: reading-{word}",
                            )
                        ]
                        if scenario["separate_sentence_cards"]
                        else []
                    )
                    return [generated_row], sentence_rows

                def _fake_review_items(*, words, **_kwargs):
                    word = str(words[0])
                    return [
                        {
                            "word": word,
                            "source_word": word,
                            "options": [
                                {
                                    "meaning": f"selected-{word}",
                                    "reading": f"sel-reading-{word}",
                                    "reading_preview": (
                                        f'<svg data-word="{word}" />'
                                        if scenario["include_pitch_accent"]
                                        else f"sel-reading-{word}"
                                    ),
                                }
                            ],
                            "related_words": [],
                            "selected_index": 0,
                        }
                    ]

                try:
                    with (
                        app.test_client() as client,
                        patch(
                            "autofiller.web_app.build_rows",
                            side_effect=_fake_build_rows,
                        ),
                        patch(
                            "autofiller.web_app._build_review_items",
                            side_effect=_fake_review_items,
                        ),
                    ):
                        resp_a = client.post(
                            f"/api/review-add-word/{job_id}",
                            json={"word": "追加語A"},
                        )
                        resp_b = client.post(
                            f"/api/review-add-word/{job_id}",
                            json={"word": "追加語B"},
                        )

                    self.assertEqual(resp_a.status_code, 200)
                    self.assertEqual(resp_b.status_code, 200)
                    self.assertEqual(len(build_rows_calls), 2)

                    for call in build_rows_calls:
                        self.assertEqual(call["pause_seconds"], 0)
                        self.assertEqual(call["candidate_limit"], 4)
                        self.assertEqual(call["sentence_count"], 2)
                        self.assertEqual(
                            call["include_sentences"], scenario["include_sentences"]
                        )
                        self.assertEqual(
                            call["separate_sentence_cards"],
                            scenario["separate_sentence_cards"],
                        )
                        self.assertEqual(
                            call["include_pitch_accent"],
                            scenario["include_pitch_accent"],
                        )
                        self.assertEqual(
                            call["pitch_accent_theme"], scenario["pitch_accent_theme"]
                        )
                        self.assertEqual(
                            call["include_furigana"], scenario["include_furigana"]
                        )
                        self.assertEqual(
                            call["furigana_format"], scenario["furigana_format"]
                        )
                        self.assertEqual(call["interactive_review"], False)

                    with web_app_module.JOB_LOCK:
                        pending = web_app_module.JOBS[job_id]["pending_add"]

                    # Two added rows should be appended regardless of scenario.
                    self.assertEqual(len(pending["rows"]), 2)
                    self.assertIn("追加語A", pending["source_words"])
                    self.assertIn("追加語B", pending["source_words"])

                    if scenario["separate_sentence_cards"]:
                        self.assertEqual(len(pending["sentence_rows"]), 2)
                        self.assertIn(
                            "Word: 追加語A", pending["sentence_rows"][0]["back"]
                        )
                        self.assertIn(
                            "Word: 追加語B", pending["sentence_rows"][1]["back"]
                        )
                    else:
                        self.assertEqual(pending["sentence_rows"], [])

                    if (
                        scenario["include_sentences"]
                        and not scenario["separate_sentence_cards"]
                    ):
                        self.assertIn("<br><br>例文:", pending["rows"][0]["meaning"])
                        self.assertIn("<br><br>例文:", pending["rows"][1]["meaning"])
                    else:
                        self.assertNotIn("<br><br>例文:", pending["rows"][0]["meaning"])
                        self.assertNotIn("<br><br>例文:", pending["rows"][1]["meaning"])
                finally:
                    with web_app_module.JOB_LOCK:
                        web_app_module.JOBS.pop(job_id, None)

    def test_build_review_items_handles_blank_readings_with_pitch(self) -> None:
        """Review item builder should keep blank readings blank and still build pitch previews for non-blank readings."""
        generated_rows = [CardRow(word="語", meaning="chosen", reading="")]

        def _pitch_html(word: str, reading: str, *, theme: str) -> str:
            if not reading:
                return ""
            return f'<svg data-word="{word}" data-reading="{reading}" data-theme="{theme}" />'

        with (
            patch(
                "autofiller.web_app.JishoClient.search_review",
                return_value=(
                    [
                        SearchCandidate(meaning="chosen", reading=""),
                        SearchCandidate(meaning="other", reading="カタカナ"),
                    ],
                    [
                        {
                            "word": "関連",
                            "meaning": "related",
                            "reading": "",
                        },
                        {
                            "word": "有音",
                            "meaning": "has reading",
                            "reading": "カタカナ",
                        },
                    ],
                ),
            ),
            patch("autofiller.web_app.enrich_html_with_pitch", side_effect=_pitch_html),
        ):
            review_items = web_app_module._build_review_items(
                words=["語"],
                candidate_limit=2,
                include_pitch_accent=True,
                pitch_accent_theme="dark",
                generated_rows=generated_rows,
            )

        self.assertEqual(len(review_items), 1)
        item = review_items[0]
        self.assertEqual(item["selected_index"], 0)
        self.assertEqual(item["options"][0]["reading"], "")
        self.assertEqual(item["options"][0]["reading_preview"], "")
        self.assertEqual(item["options"][1]["reading"], "かたかな")
        self.assertIn('data-theme="dark"', item["options"][1]["reading_preview"])
        self.assertEqual(item["related_words"][0]["reading"], "")
        self.assertEqual(item["related_words"][0]["reading_preview"], "")
        self.assertEqual(item["related_words"][1]["reading"], "かたかな")
        self.assertIn(
            'data-reading="かたかな"', item["related_words"][1]["reading_preview"]
        )

    def test_build_from_form_forwards_max_workers_to_review_generation(self) -> None:
        """Review generation should reuse the same max_workers performance setting."""
        form_data = {
            "words": "食べる\n勉強",
            "anki_connect": "true",
            "review_before_anki": "true",
            "max_workers": "4",
            "candidate_limit": "2",
            "include_pitch_accent": "false",
        }
        default_settings = {
            "pause_seconds": 0,
            "candidate_limit": 3,
            "sentence_count": 1,
            "max_workers": 2,
            "include_sentences": False,
            "include_pitch_accent": False,
            "pitch_accent_theme": "dark",
            "include_furigana": False,
            "furigana_format": "ruby",
            "separate_sentence_cards": False,
            "output_path": "output/test.tsv",
            "include_header": False,
            "review_before_anki": True,
            "anki_connect": True,
            "anki_url": "http://127.0.0.1:8765",
            "deck_name": "Default",
            "model_name": "Jisho2Anki::Vocab",
            "field_word": "Word",
            "field_meaning": "Translation",
            "field_reading": "Reading",
            "allow_duplicates": False,
            "tags": "",
            "sentence_deck_name": "Default",
            "sentence_model_name": "Basic",
            "sentence_front_field": "Front",
            "sentence_back_field": "Back",
        }

        generated_rows = [
            CardRow(word="食べる", meaning="to eat", reading="たべる"),
            CardRow(word="勉強", meaning="study", reading="べんきょう"),
        ]

        with (
            patch(
                "autofiller.web_app._resolved_settings_for_request",
                return_value=default_settings,
            ),
            patch("autofiller.web_app.build_rows", return_value=(generated_rows, [])),
            patch("autofiller.web_app.write_tsv"),
            patch(
                "autofiller.web_app._build_review_items", return_value=[]
            ) as review_mock,
        ):
            result = web_app_module._build_from_form(form_data, lambda _line: None)

        self.assertTrue(result["requires_confirmation"])
        review_mock.assert_called_once()
        self.assertEqual(review_mock.call_args.kwargs["max_workers"], 4)
        self.assertEqual(review_mock.call_args.kwargs["candidate_limit"], 2)

    def test_confirm_add_uses_distinct_choice_per_row(self) -> None:
        """Confirm endpoint must map each row to its own selected option, not reuse another row choice."""
        app = web_app_module.app
        job_id = "job-confirm-choice-mapping"

        pending_add = {
            "rows": [
                {"word": "B", "meaning": "orig-B", "reading": "orig-B"},
                {"word": "C", "meaning": "orig-C", "reading": "orig-C"},
            ],
            "sentence_rows": [],
            "review_items": [
                {
                    "word": "B",
                    "source_word": "B",
                    "options": [
                        {
                            "meaning": "B-option-0",
                            "reading": "B-r-0",
                            "reading_preview": "<svg>B-r-0</svg>",
                        },
                        {
                            "meaning": "B-option-1",
                            "reading": "B-r-1",
                            "reading_preview": "<svg>B-r-1</svg>",
                        },
                    ],
                    "related_words": [],
                    "selected_index": 0,
                },
                {
                    "word": "C",
                    "source_word": "C",
                    "options": [
                        {
                            "meaning": "C-option-0",
                            "reading": "C-r-0",
                            "reading_preview": "<svg>C-r-0</svg>",
                        },
                        {
                            "meaning": "C-option-1",
                            "reading": "C-r-1",
                            "reading_preview": "<svg>C-r-1</svg>",
                        },
                    ],
                    "related_words": [],
                    "selected_index": 0,
                },
            ],
            "separate_sentence_cards": False,
            "anki_url": "http://127.0.0.1:8765",
            "deck_name": "Example",
            "model_name": "Jisho2Anki::Vocab",
            "field_word": "Word",
            "field_meaning": "Translation",
            "field_reading": "Reading",
            "tags": ["jp"],
            "allow_duplicates": False,
        }

        with web_app_module.JOB_LOCK:
            web_app_module.JOBS[job_id] = {
                "status": "done",
                "requires_confirmation": True,
                "pending_add": pending_add,
                "anki_summary": "",
            }

        captured_rows: list[CardRow] = []

        def _capture_rows(rows, **_kwargs):
            captured_rows.extend(rows)
            return (len(rows), 0)

        try:
            with (
                app.test_client() as client,
                patch("autofiller.web_app.add_rows_to_anki", side_effect=_capture_rows),
            ):
                response = client.post(
                    f"/api/confirm/{job_id}",
                    json={"choices": [1, 0]},
                )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(captured_rows), 2)

            self.assertEqual(captured_rows[0].word, "B")
            self.assertEqual(captured_rows[0].meaning, "B-option-1")
            self.assertEqual(captured_rows[0].reading, "<svg>B-r-1</svg>")

            self.assertEqual(captured_rows[1].word, "C")
            self.assertEqual(captured_rows[1].meaning, "C-option-0")
            self.assertEqual(captured_rows[1].reading, "<svg>C-r-0</svg>")
        finally:
            with web_app_module.JOB_LOCK:
                web_app_module.JOBS.pop(job_id, None)

    def test_confirm_add_updates_sentence_rows_per_choice(self) -> None:
        """Confirm endpoint should update sentence-card readings according to each row choice."""
        app = web_app_module.app
        job_id = "job-confirm-sentence-choices"

        pending_add = {
            "rows": [
                {"word": "B", "meaning": "orig-B", "reading": "orig-B"},
                {"word": "C", "meaning": "orig-C", "reading": "orig-C"},
            ],
            "sentence_rows": [
                {"front": "B文", "back": "Front reading: old-B\nReading: old-B"},
                {"front": "C文", "back": "Front reading: old-C\nReading: old-C"},
            ],
            "review_items": [
                {
                    "word": "B",
                    "source_word": "B",
                    "options": [
                        {
                            "meaning": "B-option-0",
                            "reading": "B-r-0",
                            "reading_preview": "<svg>B-r-0</svg>",
                        },
                        {
                            "meaning": "B-option-1",
                            "reading": "B-r-1",
                            "reading_preview": "<svg>B-r-1</svg>",
                        },
                    ],
                    "related_words": [],
                    "selected_index": 0,
                },
                {
                    "word": "C",
                    "source_word": "C",
                    "options": [
                        {
                            "meaning": "C-option-0",
                            "reading": "C-r-0",
                            "reading_preview": "<svg>C-r-0</svg>",
                        },
                        {
                            "meaning": "C-option-1",
                            "reading": "C-r-1",
                            "reading_preview": "<svg>C-r-1</svg>",
                        },
                    ],
                    "related_words": [],
                    "selected_index": 0,
                },
            ],
            "separate_sentence_cards": True,
            "sentence_deck_name": "Example::Sentences",
            "sentence_model_name": "Basic",
            "sentence_front_field": "Front",
            "sentence_back_field": "Back",
            "anki_url": "http://127.0.0.1:8765",
            "deck_name": "Example",
            "model_name": "Jisho2Anki::Vocab",
            "field_word": "Word",
            "field_meaning": "Translation",
            "field_reading": "Reading",
            "tags": ["jp"],
            "allow_duplicates": False,
        }

        with web_app_module.JOB_LOCK:
            web_app_module.JOBS[job_id] = {
                "status": "done",
                "requires_confirmation": True,
                "pending_add": pending_add,
                "anki_summary": "",
            }

        captured_sentence_rows = []

        def _capture_sentence_rows(rows, **_kwargs):
            captured_sentence_rows.extend(rows)
            return (len(rows), 0)

        try:
            with (
                app.test_client() as client,
                patch("autofiller.web_app.add_rows_to_anki", return_value=(2, 0)),
                patch(
                    "autofiller.web_app.add_sentence_rows_to_anki",
                    side_effect=_capture_sentence_rows,
                ),
            ):
                response = client.post(
                    f"/api/confirm/{job_id}",
                    json={"choices": [1, 0]},
                )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(captured_sentence_rows), 2)
            self.assertIn("Reading: B-r-1", captured_sentence_rows[0].back)
            self.assertIn("Reading: C-r-0", captured_sentence_rows[1].back)
        finally:
            with web_app_module.JOB_LOCK:
                web_app_module.JOBS.pop(job_id, None)

    def test_confirm_add_preserves_inline_sentences_when_not_separate(self) -> None:
        """Confirm endpoint should keep inline sentence text when replacing reviewed meaning."""
        app = web_app_module.app
        job_id = "job-confirm-inline-sentence"

        pending_add = {
            "rows": [
                {
                    "word": "おはよう",
                    "meaning": "good morning<br><br>例文: 子どもたちは学校に着くと、校門で出迎えた校長先生に「おはようございます」と元気よく挨拶した。 - When the children arrived.",
                    "reading": "おはよう",
                }
            ],
            "sentence_rows": [],
            "review_items": [
                {
                    "word": "おはよう",
                    "source_word": "おはよう",
                    "options": [
                        {
                            "meaning": "good morning",
                            "reading": "おはよう",
                            "reading_preview": "おはよう",
                        },
                        {
                            "meaning": "morning greeting",
                            "reading": "おはよう",
                            "reading_preview": "おはよう",
                        },
                    ],
                    "related_words": [],
                    "selected_index": 0,
                }
            ],
            "separate_sentence_cards": False,
            "anki_url": "http://127.0.0.1:8765",
            "deck_name": "Example",
            "model_name": "Jisho2Anki::Vocab",
            "field_word": "Word",
            "field_meaning": "Translation",
            "field_reading": "Reading",
            "tags": ["jp"],
            "allow_duplicates": False,
        }

        with web_app_module.JOB_LOCK:
            web_app_module.JOBS[job_id] = {
                "status": "done",
                "requires_confirmation": True,
                "pending_add": pending_add,
                "anki_summary": "",
            }

        captured_rows: list[CardRow] = []

        def _capture_rows(rows, **_kwargs):
            captured_rows.extend(rows)
            return (len(rows), 0)

        try:
            with (
                app.test_client() as client,
                patch("autofiller.web_app.add_rows_to_anki", side_effect=_capture_rows),
            ):
                response = client.post(
                    f"/api/confirm/{job_id}",
                    json={"choices": [1]},
                )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(captured_rows), 1)
            self.assertIn("morning greeting", captured_rows[0].meaning)
            self.assertIn("<br><br>例文:", captured_rows[0].meaning)
            self.assertIn("When the children arrived.", captured_rows[0].meaning)
        finally:
            with web_app_module.JOB_LOCK:
                web_app_module.JOBS.pop(job_id, None)

    def test_inbox_pending_and_mark_ankied(self) -> None:
        """Inbox pending endpoint should expose items and mark endpoint should update status."""
        app = web_app_module.app
        fake_items = [
            {
                "id": 11,
                "text": "団地",
                "source": "capture:web",
                "received_at_ms": 1,
                "created_at_ms": 1,
                "status": "pending",
            }
        ]

        with (
            app.test_client() as client,
            patch(
                "autofiller.web_app.list_pending_inbox_items", return_value=fake_items
            ),
            patch("autofiller.web_app.pending_inbox_count", return_value=1),
        ):
            pending_resp = client.get("/api/inbox/pending")

        self.assertEqual(pending_resp.status_code, 200)
        self.assertEqual(pending_resp.get_json()["count"], 1)
        self.assertEqual(pending_resp.get_json()["items"][0]["text"], "団地")

        with (
            app.test_client() as client,
            patch("autofiller.web_app.mark_inbox_items_ankied", return_value=2),
            patch("autofiller.web_app.pending_inbox_count", return_value=3),
        ):
            mark_resp = client.post("/api/inbox/mark-ankied", json={"ids": [11, 12]})

        self.assertEqual(mark_resp.status_code, 200)
        self.assertEqual(mark_resp.get_json()["changed"], 2)
        self.assertEqual(mark_resp.get_json()["count"], 3)

    def test_inbox_add_endpoint_inserts_text_lines(self) -> None:
        """Inbox add endpoint should split multiline text and store each row."""
        app = web_app_module.app

        with (
            app.test_client() as client,
            patch(
                "autofiller.web_app.add_inbox_items",
                side_effect=lambda items, **_kwargs: [
                    {"id": idx + 1, "text": text} for idx, text in enumerate(items)
                ],
            ),
        ):
            resp = client.post(
                "/api/inbox/add",
                json={"text": "団地\n通快", "source": "capture:web"},
            )

        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json()
        self.assertEqual(payload["count"], 2)
        self.assertEqual(len(payload["inserted"]), 2)

    def test_confirm_marks_inbox_items_ankied(self) -> None:
        """Confirm endpoint should mark imported inbox item ids as ankied on success."""
        app = web_app_module.app
        job_id = "job-confirm-inbox-mark"

        pending_add = {
            "rows": [{"word": "食べる", "meaning": "eat", "reading": "たべる"}],
            "sentence_rows": [],
            "review_items": [],
            "separate_sentence_cards": False,
            "anki_url": "http://127.0.0.1:8765",
            "deck_name": "Example",
            "model_name": "Jisho2Anki::Vocab",
            "field_word": "Word",
            "field_meaning": "Translation",
            "field_reading": "Reading",
            "tags": ["jp"],
            "allow_duplicates": False,
            "inbox_item_ids": [101, 102],
        }

        with web_app_module.JOB_LOCK:
            web_app_module.JOBS[job_id] = {
                "status": "done",
                "requires_confirmation": True,
                "pending_add": pending_add,
                "anki_summary": "",
            }

        try:
            with (
                app.test_client() as client,
                patch("autofiller.web_app.add_rows_to_anki", return_value=(1, 0)),
                patch("autofiller.web_app.mark_inbox_items_ankied") as mark_mock,
            ):
                resp = client.post(f"/api/confirm/{job_id}")

            self.assertEqual(resp.status_code, 200)
            mark_mock.assert_called_once_with([101, 102])
        finally:
            with web_app_module.JOB_LOCK:
                web_app_module.JOBS.pop(job_id, None)


if __name__ == "__main__":
    unittest.main()
