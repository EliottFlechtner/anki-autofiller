from __future__ import annotations

import os
from pathlib import Path
from typing import Any

DEFAULT_DECK_NAME = "Keio::TestApp"
DEFAULT_MODEL_NAME = "Japanese (Basic & Reversed)"
DEFAULT_EXPRESSION_FIELD = "Expression"

DEFAULT_SETTINGS: dict[str, Any] = {
    "input": "words.txt",
    "output_path": "anki_import.tsv",
    "include_header": True,
    "pause_seconds": 0.0,
    "max_workers": 6,
    "interactive_review": False,
    "candidate_limit": 3,
    "sentence_count": 2,
    "separate_sentence_cards": False,
    "include_sentences": True,
    "include_pitch_accent": True,
    "anki_connect": True,
    "anki_url": "http://127.0.0.1:8765",
    "deck_name": DEFAULT_DECK_NAME,
    "model_name": DEFAULT_MODEL_NAME,
    "field_word": DEFAULT_EXPRESSION_FIELD,
    "field_meaning": "Meaning",
    "field_reading": "Reading",
    "tags": "",
    "allow_duplicates": False,
    "sentence_deck_name": f"{DEFAULT_DECK_NAME}::Examples",
    "sentence_model_name": "Basic",
    "sentence_front_field": "Front",
    "sentence_back_field": "Back",
}

ENV_PREFIX = "ANKI_AUTOFILLER_"
ENV_TO_KEY = {
    "INPUT": "input",
    "OUTPUT_PATH": "output_path",
    "INCLUDE_HEADER": "include_header",
    "PAUSE_SECONDS": "pause_seconds",
    "MAX_WORKERS": "max_workers",
    "INTERACTIVE_REVIEW": "interactive_review",
    "CANDIDATE_LIMIT": "candidate_limit",
    "SENTENCE_COUNT": "sentence_count",
    "SEPARATE_SENTENCE_CARDS": "separate_sentence_cards",
    "INCLUDE_SENTENCES": "include_sentences",
    "INCLUDE_PITCH_ACCENT": "include_pitch_accent",
    "ANKI_CONNECT": "anki_connect",
    "ANKI_URL": "anki_url",
    "DECK_NAME": "deck_name",
    "MODEL_NAME": "model_name",
    "FIELD_WORD": "field_word",
    "FIELD_MEANING": "field_meaning",
    "FIELD_READING": "field_reading",
    "TAGS": "tags",
    "ALLOW_DUPLICATES": "allow_duplicates",
    "SENTENCE_DECK_NAME": "sentence_deck_name",
    "SENTENCE_MODEL_NAME": "sentence_model_name",
    "SENTENCE_FRONT_FIELD": "sentence_front_field",
    "SENTENCE_BACK_FIELD": "sentence_back_field",
}


def _parse_bool(raw: str) -> bool:
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _coerce_value(key: str, raw: str) -> Any:
    if key in {
        "include_header",
        "interactive_review",
        "separate_sentence_cards",
        "include_sentences",
        "include_pitch_accent",
        "anki_connect",
        "allow_duplicates",
    }:
        return _parse_bool(raw)
    if key in {"candidate_limit", "sentence_count", "max_workers"}:
        return int(raw)
    if key in {"pause_seconds"}:
        return float(raw)
    return raw


def _load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        values[key] = value
    return values


def _resolve_preset_file(preset_name: str | None) -> Path | None:
    if not preset_name:
        return None
    cleaned = preset_name.strip()
    if not cleaned:
        return None
    if any(ch in cleaned for ch in ("/", "\\", "..")):
        raise ValueError("Invalid preset name.")

    preset_path = Path("presets") / f"{cleaned}.env"
    return preset_path


def available_presets() -> list[str]:
    preset_dir = Path("presets")
    if not preset_dir.exists():
        return []

    names = [path.stem for path in preset_dir.glob("*.env") if path.is_file()]
    return sorted(names)


def load_settings(
    *,
    preset_name: str | None = None,
    env_file: str | None = None,
) -> dict[str, Any]:
    settings = dict(DEFAULT_SETTINGS)

    file_sources: list[Path] = [Path(".env"), Path(".env.local")]

    preset_file = _resolve_preset_file(preset_name)
    if preset_file is not None:
        file_sources.append(preset_file)

    if env_file:
        file_sources.append(Path(env_file))

    for source in file_sources:
        for env_key, raw_value in _load_env_file(source).items():
            if not env_key.startswith(ENV_PREFIX):
                continue
            short_key = env_key[len(ENV_PREFIX) :]
            mapped_key = ENV_TO_KEY.get(short_key)
            if not mapped_key:
                continue
            settings[mapped_key] = _coerce_value(mapped_key, raw_value)

    for short_key, mapped_key in ENV_TO_KEY.items():
        full_key = f"{ENV_PREFIX}{short_key}"
        raw_value = os.environ.get(full_key)
        if raw_value is None:
            continue
        settings[mapped_key] = _coerce_value(mapped_key, raw_value)

    return settings
