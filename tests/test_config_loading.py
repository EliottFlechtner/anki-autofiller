from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from autofiller import config


class ConfigLoadingTests(unittest.TestCase):
    def test_resolve_preset_file_rejects_path_traversal(self) -> None:
        with self.assertRaises(ValueError):
            config._resolve_preset_file("../bad")
        with self.assertRaises(ValueError):
            config._resolve_preset_file("dir/name")

    def test_available_presets_sorted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "presets").mkdir()
            (root / "presets" / "z-last.env").write_text("", encoding="utf-8")
            (root / "presets" / "a-first.env").write_text("", encoding="utf-8")
            (root / "presets" / "ignore.txt").write_text("", encoding="utf-8")

            old_cwd = Path.cwd()
            os.chdir(root)
            try:
                self.assertEqual(config.available_presets(), ["a-first", "z-last"])
            finally:
                os.chdir(old_cwd)

    def test_load_settings_precedence_and_type_coercion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "presets").mkdir()

            (root / ".env").write_text(
                "\n".join(
                    [
                        "ANKI_JISHO2ANKI_INCLUDE_SENTENCES=true",
                        "ANKI_JISHO2ANKI_CANDIDATE_LIMIT=2",
                        "ANKI_JISHO2ANKI_PAUSE_SECONDS=0.1",
                    ]
                ),
                encoding="utf-8",
            )
            (root / ".env.local").write_text(
                "\n".join(
                    [
                        "ANKI_JISHO2ANKI_INCLUDE_SENTENCES=false",
                        "ANKI_JISHO2ANKI_CANDIDATE_LIMIT=4",
                    ]
                ),
                encoding="utf-8",
            )
            (root / "presets" / "balanced.env").write_text(
                "\n".join(
                    [
                        "ANKI_JISHO2ANKI_INCLUDE_PITCH_ACCENT=false",
                        "ANKI_JISHO2ANKI_MAX_WORKERS=5",
                    ]
                ),
                encoding="utf-8",
            )
            (root / "custom.env").write_text(
                "\n".join(
                    [
                        "ANKI_JISHO2ANKI_MAX_WORKERS=7",
                        "ANKI_JISHO2ANKI_ALLOW_DUPLICATES=true",
                    ]
                ),
                encoding="utf-8",
            )

            env_override = {
                "ANKI_JISHO2ANKI_INCLUDE_SENTENCES": "true",
                "ANKI_JISHO2ANKI_MAX_WORKERS": "9",
            }

            old_cwd = Path.cwd()
            os.chdir(root)
            try:
                with patch.dict(os.environ, env_override, clear=False):
                    settings = config.load_settings(
                        preset_name="balanced",
                        env_file="custom.env",
                    )
            finally:
                os.chdir(old_cwd)

            # os.environ should win over file sources.
            self.assertTrue(settings["include_sentences"])
            self.assertEqual(settings["max_workers"], 9)
            # env_file should win over preset.
            self.assertTrue(settings["allow_duplicates"])
            # preset should apply when not overridden later.
            self.assertFalse(settings["include_pitch_accent"])
            # coerced numeric types
            self.assertIsInstance(settings["candidate_limit"], int)
            self.assertIsInstance(settings["pause_seconds"], float)


if __name__ == "__main__":
    unittest.main()
