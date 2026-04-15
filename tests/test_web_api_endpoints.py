from __future__ import annotations

import unittest
from unittest.mock import patch

from autofiller.models import CardRow

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
    def test_bootstrap_returns_defaults_and_presets(self) -> None:
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

    def test_generate_route_returns_410(self) -> None:
        app = web_app_module.app
        with app.test_client() as client:
            response = client.post("/generate")

        self.assertEqual(response.status_code, 410)
        payload = response.get_json()
        self.assertIn("Legacy /generate route", payload["error"])

    def test_start_and_status_with_synchronous_thread(self) -> None:
        app = web_app_module.app

        class _ImmediateThread:
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


if __name__ == "__main__":
    unittest.main()
