from __future__ import annotations

import os
import re
import threading
import uuid
from pathlib import Path
from typing import Any, Mapping

from flask import Flask, jsonify, render_template, request

from .anki_connect_client import add_rows_to_anki, add_sentence_rows_to_anki
from .config import (
    available_presets,
    load_settings,
)
from .io_utils import normalize_words, write_tsv
from .pipeline import build_rows

ROOT_DIR = Path(__file__).resolve().parents[1]
app = Flask(__name__, template_folder=str(ROOT_DIR / "templates"))
PROGRESS_RE = re.compile(r"^\[(\d+)/(\d+)\]")

JOBS: dict[str, dict[str, Any]] = {}
JOB_LOCK = threading.Lock()


def _bool_from_form(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value == "on"


def _job_update(job_id: str, **updates: Any) -> None:
    with JOB_LOCK:
        if job_id in JOBS:
            JOBS[job_id].update(updates)


def _serialize_rows_preview(rows: list[Any], limit: int = 60) -> list[dict[str, str]]:
    return [
        {"word": row.word, "meaning": row.meaning, "reading": row.reading}
        for row in rows[:limit]
    ]


def _value_from_form(form_data: Mapping[str, str], key: str, default: str) -> str:
    raw = form_data.get(key)
    if raw is None:
        return default
    stripped = raw.strip()
    return stripped if stripped else default


def _template_defaults(
    *, selected_preset: str = "", selected_env_file: str = ""
) -> dict[str, Any]:
    defaults = dict(load_settings())
    defaults["selected_preset"] = selected_preset
    defaults["selected_env_file"] = selected_env_file
    return defaults


def _resolved_settings_for_request(form_data: Mapping[str, str]) -> dict[str, Any]:
    preset_name = _value_from_form(form_data, "preset", "")
    env_file = _value_from_form(form_data, "env_file", "")
    return load_settings(
        preset_name=preset_name or None,
        env_file=env_file or None,
    )


def _build_from_form(
    form_data: Mapping[str, str],
    progress_printer,
) -> dict[str, Any]:
    preset_name = _value_from_form(form_data, "preset", "")
    env_file = _value_from_form(form_data, "env_file", "")
    settings = _resolved_settings_for_request(form_data)

    words_block = form_data.get("words", "")
    words = normalize_words(words_block.splitlines())

    if not words:
        raise ValueError("Please enter at least one word.")

    pause_seconds = float(
        _value_from_form(form_data, "pause_seconds", str(settings["pause_seconds"]))
    )
    candidate_limit = int(
        _value_from_form(form_data, "candidate_limit", str(settings["candidate_limit"]))
    )
    sentence_count = int(
        _value_from_form(form_data, "sentence_count", str(settings["sentence_count"]))
    )
    max_workers = int(
        _value_from_form(form_data, "max_workers", str(settings["max_workers"]))
    )
    include_sentences = _bool_from_form(
        form_data.get("include_sentences"),
        default=bool(settings["include_sentences"]),
    )
    include_pitch_accent = _bool_from_form(
        form_data.get("include_pitch_accent"),
        default=bool(settings["include_pitch_accent"]),
    )
    separate_sentence_cards = _bool_from_form(
        form_data.get("separate_sentence_cards"),
        default=bool(settings["separate_sentence_cards"]),
    )

    rows, sentence_rows = build_rows(
        words=words,
        pause_seconds=pause_seconds,
        candidate_limit=candidate_limit,
        sentence_count=sentence_count,
        include_sentences=include_sentences,
        separate_sentence_cards=separate_sentence_cards,
        include_pitch_accent=include_pitch_accent,
        max_workers=max(1, max_workers),
        interactive_review=False,
        progress_printer=progress_printer,
    )

    output_path_raw = _value_from_form(
        form_data,
        "output_path",
        str(settings["output_path"]),
    )
    output_path = Path(output_path_raw)
    include_header = _bool_from_form(
        form_data.get("include_header"),
        default=bool(settings["include_header"]),
    )
    write_tsv(rows=rows, output_path=output_path, include_header=include_header)

    anki_summary = ""
    if _bool_from_form(
        form_data.get("anki_connect"), default=bool(settings["anki_connect"])
    ):
        anki_url = _value_from_form(form_data, "anki_url", str(settings["anki_url"]))
        deck_name = _value_from_form(form_data, "deck_name", str(settings["deck_name"]))
        model_name = _value_from_form(
            form_data, "model_name", str(settings["model_name"])
        )
        field_word = _value_from_form(
            form_data, "field_word", str(settings["field_word"])
        )
        field_meaning = _value_from_form(
            form_data,
            "field_meaning",
            str(settings["field_meaning"]),
        )
        field_reading = _value_from_form(
            form_data,
            "field_reading",
            str(settings["field_reading"]),
        )
        allow_duplicates = _bool_from_form(
            form_data.get("allow_duplicates"),
            default=bool(settings["allow_duplicates"]),
        )
        tags_raw = _value_from_form(form_data, "tags", str(settings["tags"]))
        tags = [tag.strip() for tag in tags_raw.split(",") if tag.strip()]
        sentence_deck_name = _value_from_form(
            form_data,
            "sentence_deck_name",
            str(settings["sentence_deck_name"]),
        )
        sentence_model_name = _value_from_form(
            form_data,
            "sentence_model_name",
            str(settings["sentence_model_name"]),
        )
        sentence_front_field = _value_from_form(
            form_data,
            "sentence_front_field",
            str(settings["sentence_front_field"]),
        )
        sentence_back_field = _value_from_form(
            form_data,
            "sentence_back_field",
            str(settings["sentence_back_field"]),
        )

        success, failed = add_rows_to_anki(
            rows,
            url=anki_url,
            deck_name=deck_name,
            model_name=model_name,
            word_field=field_word,
            meaning_field=field_meaning,
            reading_field=field_reading,
            tags=tags,
            allow_duplicates=allow_duplicates,
        )
        anki_summary = (
            f"Added to Anki: success={success}, failed={failed}, endpoint={anki_url}"
        )

        if separate_sentence_cards:
            sent_success, sent_failed = add_sentence_rows_to_anki(
                sentence_rows,
                url=anki_url,
                deck_name=sentence_deck_name,
                model_name=sentence_model_name,
                front_field=sentence_front_field,
                back_field=sentence_back_field,
                tags=tags,
                allow_duplicates=allow_duplicates,
            )
            anki_summary += (
                f" | Sentence cards: success={sent_success}, failed={sent_failed}, "
                f"deck={sentence_deck_name}"
            )

    return {
        "rows": rows,
        "output_path": str(output_path),
        "message": f"Generated {len(rows)} rows.",
        "anki_summary": anki_summary,
        "preset": preset_name,
        "env_file": env_file,
    }


@app.post("/api/settings-preview")
def api_settings_preview() -> Any:
    form_data = request.form.to_dict(flat=True)
    preset_name = _value_from_form(form_data, "preset", "")
    env_file = _value_from_form(form_data, "env_file", "")
    settings = _resolved_settings_for_request(form_data)
    return jsonify(
        {
            "preset": preset_name,
            "env_file": env_file,
            "settings": settings,
            "presets": available_presets(),
        }
    )


def _run_job(job_id: str, form_data: dict[str, str]) -> None:
    with JOB_LOCK:
        JOBS[job_id] = {
            "status": "running",
            "completed": 0,
            "total": len(normalize_words(form_data.get("words", "").splitlines())),
            "log": [],
            "message": "",
            "anki_summary": "",
            "preview": [],
            "output_path": "",
            "error": "",
        }

    def progress_cb(line: str) -> None:
        completed = None
        total = None
        m = PROGRESS_RE.match(line)
        if m:
            completed = int(m.group(1))
            total = int(m.group(2))

        with JOB_LOCK:
            job = JOBS.get(job_id)
            if not job:
                return
            if completed is not None:
                job["completed"] = completed
            if total is not None:
                job["total"] = total
            logs = job.get("log", [])
            logs.append(line)
            job["log"] = logs[-40:]

    try:
        result = _build_from_form(form_data, progress_cb)
        _job_update(
            job_id,
            status="done",
            completed=result["rows"] and len(result["rows"]) or 0,
            message=result["message"],
            anki_summary=result["anki_summary"],
            output_path=result["output_path"],
            preview=_serialize_rows_preview(result["rows"]),
            preset=form_data.get("preset", ""),
            env_file=form_data.get("env_file", ""),
        )
    except Exception as exc:  # noqa: BLE001
        _job_update(job_id, status="error", error=str(exc))


@app.get("/")
def index() -> str:
    return render_template(
        "index.html",
        defaults=_template_defaults(),
        presets=available_presets(),
        vite_dev_server_url=os.environ.get("ANKI_AUTOFILLER_VITE_DEV_SERVER_URL", ""),
    )


@app.post("/api/start")
def api_start() -> Any:
    job_id = uuid.uuid4().hex
    form_data = request.form.to_dict(flat=True)
    thread = threading.Thread(target=_run_job, args=(job_id, form_data), daemon=True)
    thread.start()
    return jsonify({"job_id": job_id})


@app.get("/api/status/<job_id>")
def api_status(job_id: str) -> Any:
    with JOB_LOCK:
        job = JOBS.get(job_id)
    if not job:
        return jsonify({"error": "job not found"}), 404
    return jsonify(job)


@app.post("/generate")
def generate() -> str:
    try:
        result = _build_from_form(request.form.to_dict(flat=True), print)
    except Exception as exc:  # noqa: BLE001
        return render_template(
            "index.html",
            error=str(exc),
            defaults=_template_defaults(
                selected_preset=request.form.get("preset", ""),
                selected_env_file=request.form.get("env_file", ""),
            ),
            presets=available_presets(),
            vite_dev_server_url=os.environ.get(
                "ANKI_AUTOFILLER_VITE_DEV_SERVER_URL", ""
            ),
        )

    return render_template(
        "index.html",
        preview=result["rows"],
        output_path=result["output_path"],
        message=result["message"],
        anki_summary=result["anki_summary"],
        defaults=_template_defaults(
            selected_preset=result.get("preset", ""),
            selected_env_file=result.get("env_file", ""),
        ),
        presets=available_presets(),
        vite_dev_server_url=os.environ.get("ANKI_AUTOFILLER_VITE_DEV_SERVER_URL", ""),
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
