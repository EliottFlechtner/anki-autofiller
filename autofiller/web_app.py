"""Flask web API and SPA host for running Jisho2Anki from a browser."""

from __future__ import annotations

import os
import re
import threading
import uuid
import copy
import hmac
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Mapping

from flask import Flask, Response, jsonify, render_template, request

from .anki_connect_client import add_rows_to_anki, add_sentence_rows_to_anki, invoke
from .config import (
    available_presets,
    load_settings,
)
from .io_utils import normalize_words, write_tsv
from .jisho_client import JishoClient
from .models import CardRow, SearchCandidate, SentenceCardRow
from .pipeline import build_rows
from .pitch_accent import enrich_html_with_pitch
from .inbox_store import (
    add_inbox_items,
    delete_inbox_item,
    ensure_inbox_db,
    list_pending_inbox_items,
    mark_inbox_items_ankied,
    pending_inbox_count,
)

ROOT_DIR = Path(__file__).resolve().parents[1]
app = Flask(__name__, template_folder=str(ROOT_DIR / "templates"))
PROGRESS_RE = re.compile(r"^\[(\d+)/(\d+)\]")
ensure_inbox_db()


def _runtime_env(name: str, default: str) -> str:
    """Read runtime env from current or legacy prefix with fallback default.

    Args:
        name: Environment variable suffix without project prefix.
        default: Fallback value when no variable is set.

    Returns:
        Resolved runtime value.
    """
    return os.environ.get(
        f"ANKI_JISHO2ANKI_{name}",
        os.environ.get(f"ANKI_AUTOFILLER_{name}", default),
    )


DEFAULT_FLASK_HOST = _runtime_env("FLASK_HOST", "127.0.0.1")
DEFAULT_FLASK_PORT = int(_runtime_env("FLASK_PORT", os.environ.get("PORT", "5000")))
WEB_AUTH_USERNAME = _runtime_env("WEB_AUTH_USERNAME", "")
WEB_AUTH_PASSWORD = _runtime_env("WEB_AUTH_PASSWORD", "")
ALLOWED_IPS_RAW = _runtime_env("ALLOWED_IPS", "")

JOBS: dict[str, dict[str, Any]] = {}
JOB_LOCK = threading.Lock()


def _allowed_ips() -> set[str]:
    """Parse comma-separated allowed client IPs from runtime env."""
    return {token.strip() for token in ALLOWED_IPS_RAW.split(",") if token.strip()}


def _client_ip() -> str:
    """Resolve best-effort client IP, honoring proxy-forwarded headers."""
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    if forwarded_for.strip():
        # Use left-most client IP when behind a trusted reverse proxy.
        return forwarded_for.split(",", 1)[0].strip()
    return request.remote_addr or ""


def _web_auth_enabled() -> bool:
    """Return whether HTTP basic auth is enabled via runtime env values."""
    return bool(WEB_AUTH_USERNAME or WEB_AUTH_PASSWORD)


def _unauthorized_response() -> Response:
    """Return a standard HTTP basic-auth challenge response."""
    return Response(
        "Authentication required",
        401,
        {"WWW-Authenticate": 'Basic realm="Jisho2Anki", charset="UTF-8"'},
    )


def _is_authorized_request() -> bool:
    """Validate incoming request credentials against configured basic auth values."""
    auth = request.authorization
    if not auth:
        return False

    if not hmac.compare_digest(auth.username or "", WEB_AUTH_USERNAME):
        return False

    if not hmac.compare_digest(auth.password or "", WEB_AUTH_PASSWORD):
        return False

    return True


@app.before_request
def _protect_with_optional_basic_auth() -> Response | None:
    """Optionally require HTTP basic auth for all routes except health checks."""
    if request.path == "/healthz":
        return None

    allowed_ips = _allowed_ips()
    if allowed_ips:
        client_ip = _client_ip()
        if client_ip not in allowed_ips:
            return Response(
                "Access denied from this IP",
                403,
            )

    if not _web_auth_enabled():
        return None

    # Treat partial auth config as invalid and deny access until fixed.
    if not WEB_AUTH_USERNAME or not WEB_AUTH_PASSWORD:
        return Response(
            "Invalid auth configuration: set both WEB_AUTH_USERNAME and WEB_AUTH_PASSWORD",
            503,
        )

    if _is_authorized_request():
        return None

    return _unauthorized_response()


def _parse_inbox_item_ids(raw: str | None) -> list[int]:
    if raw is None:
        return []
    ids: list[int] = []
    for piece in str(raw).split(","):
        token = piece.strip()
        if not token:
            continue
        try:
            value = int(token)
        except ValueError:
            continue
        if value > 0:
            ids.append(value)
    return sorted(set(ids))


def _static_stylesheet_filename() -> str:
    """Return the built frontend stylesheet path relative to Flask static root.

    Returns:
        Relative static asset path or an empty string when no build exists.
    """
    assets_dir = ROOT_DIR / "autofiller" / "static" / "assets"
    if not assets_dir.exists():
        return ""

    matches = sorted(assets_dir.glob("main-*.css"))
    if not matches:
        return ""
    return f"assets/{matches[-1].name}"


def _bool_from_form(value: str | None, default: bool = False) -> bool:
    """Parse checkbox/form values into a deterministic boolean.

    Args:
        value: Raw checkbox/form string value.
        default: Fallback when value is missing or unrecognized.

    Returns:
        Parsed boolean value.
    """
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _job_update(job_id: str, **updates: Any) -> None:
    """Apply thread-safe updates to the in-memory job state map.

    Args:
        job_id: Target job ID.
        **updates: Key/value fields to update in the job state.
    """
    with JOB_LOCK:
        if job_id in JOBS:
            JOBS[job_id].update(updates)


def _serialize_rows_preview(rows: list[Any], limit: int = 60) -> list[dict[str, str]]:
    """Serialize generated rows into a lightweight preview payload.

    Args:
        rows: Full generated row list.
        limit: Maximum number of rows to include in preview.

    Returns:
        JSON-serializable preview row dictionaries.
    """
    return [
        {"word": row.word, "meaning": row.meaning, "reading": row.reading}
        for row in rows[:limit]
    ]


def _serialize_sentence_rows_preview(
    rows: list[Any], limit: int = 60
) -> list[dict[str, str]]:
    """Serialize generated sentence rows into a lightweight preview payload.

    Args:
        rows: Full generated sentence-row list.
        limit: Maximum number of rows to include in preview.

    Returns:
        JSON-serializable preview row dictionaries.
    """
    return [{"front": row.front, "back": row.back} for row in rows[:limit]]


def _deserialize_card_rows(payload_rows: list[dict[str, str]]) -> list[CardRow]:
    """Rebuild `CardRow` objects from serialized payload dictionaries."""
    return [
        CardRow(
            word=str(item.get("word", "")),
            meaning=str(item.get("meaning", "")),
            reading=str(item.get("reading", "")),
        )
        for item in payload_rows
    ]


def _deserialize_sentence_rows(
    payload_rows: list[dict[str, str]],
) -> list[SentenceCardRow]:
    """Rebuild `SentenceCardRow` objects from serialized payload dictionaries."""
    return [
        SentenceCardRow(
            front=str(item.get("front", "")),
            back=str(item.get("back", "")),
        )
        for item in payload_rows
    ]


def _to_hiragana(text: str) -> str:
    """Convert Katakana in `text` to Hiragana, preserving other characters."""
    chars: list[str] = []
    for char in text:
        code = ord(char)
        if 0x30A1 <= code <= 0x30F6:
            chars.append(chr(code - 0x60))
        else:
            chars.append(char)
    return "".join(chars)


def _build_review_items(
    *,
    words: list[str],
    candidate_limit: int,
    include_pitch_accent: bool,
    pitch_accent_theme: str,
    generated_rows: list[CardRow],
    max_workers: int = 1,
) -> list[dict[str, Any]]:
    """Build per-word candidate options used by web review-before-add workflow."""
    safe_workers = max(1, max_workers)

    def _build_single_item(index: int, word: str) -> dict[str, Any]:
        client = JishoClient()
        candidates, related_candidates = client.search_review(
            word,
            candidate_limit=max(candidate_limit, 1),
        )
        if not candidates:
            candidates = [SearchCandidate(meaning="", reading="")]

        options: list[dict[str, str]] = []
        for candidate in candidates:
            reading = _to_hiragana(candidate.reading)
            reading_preview = reading
            if include_pitch_accent:
                pitch_html = enrich_html_with_pitch(
                    word,
                    reading,
                    theme=pitch_accent_theme,
                )
                if pitch_html:
                    reading_preview = pitch_html

            options.append(
                {
                    "meaning": candidate.meaning,
                    "reading": reading,
                    "reading_preview": reading_preview,
                }
            )

        selected_index = 0
        if index < len(generated_rows):
            generated_meaning = generated_rows[index].meaning
            for opt_index, option in enumerate(options):
                if option["meaning"] == generated_meaning:
                    selected_index = opt_index
                    break

        return {
            "word": generated_rows[index].word if index < len(generated_rows) else word,
            "source_word": word,
            "options": options,
            "related_words": [
                {
                    "word": str(item.get("word", "")),
                    "meaning": str(item.get("meaning", "")),
                    "reading": _to_hiragana(str(item.get("reading", ""))),
                    "reading_preview": (
                        enrich_html_with_pitch(
                            str(item.get("word", "")),
                            _to_hiragana(str(item.get("reading", ""))),
                            theme=pitch_accent_theme,
                        )
                        if include_pitch_accent
                        else _to_hiragana(str(item.get("reading", "")))
                    )
                    or _to_hiragana(str(item.get("reading", ""))),
                }
                for item in related_candidates
                if str(item.get("word", "")).strip()
            ],
            "selected_index": selected_index,
        }

    if safe_workers == 1 or len(words) <= 1:
        return [_build_single_item(index, word) for index, word in enumerate(words)]

    ordered_items: list[dict[str, Any] | None] = [None] * len(words)
    with ThreadPoolExecutor(max_workers=min(safe_workers, len(words))) as executor:
        futures = {
            executor.submit(_build_single_item, index, word): index
            for index, word in enumerate(words)
        }
        for future in as_completed(futures):
            index = futures[future]
            ordered_items[index] = future.result()

    return [item for item in ordered_items if item is not None]


def _value_from_form(form_data: Mapping[str, str], key: str, default: str) -> str:
    """Read and trim a form value, falling back to `default` when blank.

    Args:
        form_data: Flat mapping of submitted form values.
        key: Form key to read.
        default: Fallback value for missing or blank input.

    Returns:
        Trimmed non-empty value or fallback default.
    """
    raw = form_data.get(key)
    if raw is None:
        return default
    stripped = raw.strip()
    return stripped if stripped else default


def _template_defaults(
    *, selected_preset: str = "", selected_env_file: str = ""
) -> dict[str, Any]:
    """Return default settings payload used by the frontend bootstrap.

    Args:
        selected_preset: Preset currently selected in the UI.
        selected_env_file: Env file currently selected in the UI.

    Returns:
        Settings dictionary enriched with selection metadata.
    """
    defaults = dict(load_settings())
    defaults["selected_preset"] = selected_preset
    defaults["selected_env_file"] = selected_env_file
    return defaults


@app.get("/api/bootstrap")
def api_bootstrap() -> Any:
    """Return initial defaults and available presets for the SPA.

    Returns:
        JSON response containing defaults and preset names.
    """
    defaults = _template_defaults()
    return jsonify({"defaults": defaults, "presets": available_presets()})


def _resolved_settings_for_request(form_data: Mapping[str, str]) -> dict[str, Any]:
    """Resolve settings for a request from selected preset/env-file inputs.

    Args:
        form_data: Incoming form field map.

    Returns:
        Effective settings dictionary for this request.
    """
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
    """Run the generation pipeline from submitted form values and settings.

    Args:
        form_data: Submitted form fields.
        progress_printer: Callback used to emit progress log lines.

    Returns:
        Result payload containing generated rows, paths, and user-facing summaries.

    Raises:
        ValueError: If no source words were provided.
    """
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
    pitch_accent_theme = _value_from_form(
        form_data,
        "pitch_accent_theme",
        str(settings["pitch_accent_theme"]),
    ).lower()
    if pitch_accent_theme not in {"dark", "light"}:
        pitch_accent_theme = "dark"

    include_furigana = _bool_from_form(
        form_data.get("include_furigana"),
        default=bool(settings["include_furigana"]),
    )
    furigana_format = _value_from_form(
        form_data,
        "furigana_format",
        str(settings["furigana_format"]),
    ).lower()
    if furigana_format not in {"ruby", "anki"}:
        furigana_format = "ruby"

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
        pitch_accent_theme=pitch_accent_theme,
        include_furigana=include_furigana,
        furigana_format=furigana_format,
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
    review_before_anki = _bool_from_form(
        form_data.get("review_before_anki"),
        default=bool(settings["review_before_anki"]),
    )

    inbox_item_ids = _parse_inbox_item_ids(form_data.get("inbox_item_ids"))

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

        if review_before_anki:
            review_items = _build_review_items(
                words=words,
                candidate_limit=candidate_limit,
                include_pitch_accent=include_pitch_accent,
                pitch_accent_theme=pitch_accent_theme,
                generated_rows=rows,
                max_workers=max(1, max_workers),
            )
            anki_summary = "Review mode enabled: preview generated. Confirm to add these notes to Anki."
            return {
                "rows": rows,
                "sentence_rows": sentence_rows,
                "output_path": str(output_path),
                "message": "",
                "anki_summary": anki_summary,
                "preset": preset_name,
                "env_file": env_file,
                "requires_confirmation": True,
                "review_items": review_items,
                "pending_add": {
                    "rows": _serialize_rows_preview(rows, limit=len(rows)),
                    "sentence_rows": _serialize_sentence_rows_preview(
                        sentence_rows, limit=len(sentence_rows)
                    ),
                    "review_items": copy.deepcopy(review_items),
                    "source_words": words,
                    "candidate_limit": candidate_limit,
                    "include_pitch_accent": include_pitch_accent,
                    "pitch_accent_theme": pitch_accent_theme,
                    "separate_sentence_cards": separate_sentence_cards,
                    "anki_url": anki_url,
                    "deck_name": deck_name,
                    "model_name": model_name,
                    "field_word": field_word,
                    "field_meaning": field_meaning,
                    "field_reading": field_reading,
                    "tags": tags,
                    "allow_duplicates": allow_duplicates,
                    "sentence_deck_name": sentence_deck_name,
                    "sentence_model_name": sentence_model_name,
                    "sentence_front_field": sentence_front_field,
                    "sentence_back_field": sentence_back_field,
                    "inbox_item_ids": inbox_item_ids,
                },
            }

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
        anki_summary = f"✓ Added {success} card{'' if success == 1 else 's'} to Anki"
        if failed:
            anki_summary += f" ({failed} failed)"

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
            anki_summary += f", ✓ added {sent_success} sentence card{'' if sent_success == 1 else 's'}"
            if sent_failed:
                anki_summary += f" ({sent_failed} failed)"

        if success > 0 and inbox_item_ids:
            mark_inbox_items_ankied(inbox_item_ids)

    return {
        "rows": rows,
        "sentence_rows": sentence_rows,
        "output_path": str(output_path),
        "message": f"Generated {len(rows)} rows.",
        "anki_summary": anki_summary,
        "preset": preset_name,
        "env_file": env_file,
        "requires_confirmation": False,
        "review_items": [],
    }


@app.post("/api/settings-preview")
def api_settings_preview() -> Any:
    """Preview merged settings for the currently selected preset/env file.

    Returns:
        JSON response with selected preset/env and merged settings payload.
    """
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


@app.get("/api/anki-options")
def api_anki_options() -> Any:
    """Return available Anki model and deck names for dropdown selection.

    Query params:
        anki_url: Optional AnkiConnect endpoint URL.

    Returns:
        JSON payload with `models` and `decks` arrays, or a descriptive error.
    """
    anki_url = request.args.get("anki_url", "").strip() or str(
        load_settings()["anki_url"]
    )

    try:
        models = invoke(anki_url, "modelNames", {})
        decks = invoke(anki_url, "deckNames", {})
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc), "models": [], "decks": []}), 502

    safe_models = (
        sorted(str(name) for name in models) if isinstance(models, list) else []
    )
    safe_decks = sorted(str(name) for name in decks) if isinstance(decks, list) else []
    return jsonify({"models": safe_models, "decks": safe_decks})


def _run_job(job_id: str, form_data: dict[str, str]) -> None:
    """Background worker for a single generation request.

    Args:
        job_id: Unique in-memory job identifier.
        form_data: Snapshot of submitted form data.
    """
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
            sentence_preview=_serialize_sentence_rows_preview(
                result.get("sentence_rows", [])
            ),
            review_items=result.get("review_items", []),
            preset=form_data.get("preset", ""),
            env_file=form_data.get("env_file", ""),
            requires_confirmation=bool(result.get("requires_confirmation", False)),
            pending_add=result.get("pending_add"),
        )
    except Exception as exc:  # noqa: BLE001
        _job_update(job_id, status="error", error=str(exc))


@app.get("/")
def index() -> str:
    """Serve the SPA shell with either Vite dev assets or built assets.

    Returns:
        Rendered HTML for the single-page app shell.
    """
    vite_dev_server_url = _runtime_env("VITE_DEV_SERVER_URL", "")
    return render_template(
        "spa.html",
        vite_dev_server_url=vite_dev_server_url,
        static_stylesheet_filename=(
            "" if vite_dev_server_url else _static_stylesheet_filename()
        ),
    )


@app.get("/healthz")
def healthz() -> Any:
    """Lightweight health endpoint for compose/ops checks.

    Returns:
        JSON response indicating service health.
    """
    return jsonify({"status": "ok"})


@app.get("/api/inbox/pending")
def api_inbox_pending() -> Any:
    """Return pending inbox rows for import/review in web UI."""
    limit_raw = request.args.get("limit", "200")
    try:
        limit = int(limit_raw)
    except ValueError:
        limit = 200

    items = list_pending_inbox_items(limit=limit)
    return jsonify({"items": items, "count": pending_inbox_count()})


@app.post("/api/inbox/add")
def api_inbox_add() -> Any:
    """Manually add one or more inbox rows (useful for capture/testing)."""
    body = request.get_json(silent=True) or {}
    raw_text = str(body.get("text", ""))
    source = str(body.get("source", "manual"))
    if not raw_text.strip():
        return jsonify({"error": "text is required"}), 400

    parts = [segment.strip() for segment in raw_text.splitlines() if segment.strip()]
    inserted = add_inbox_items(parts, source=source)
    return jsonify({"inserted": inserted, "count": len(inserted)})


@app.post("/api/inbox/mark-ankied")
def api_inbox_mark_ankied() -> Any:
    """Mark inbox rows as ankied after successful Anki submission."""
    body = request.get_json(silent=True) or {}
    ids_raw = body.get("ids", []) if isinstance(body, dict) else []
    if not isinstance(ids_raw, list):
        return jsonify({"error": "ids must be a list"}), 400

    try:
        ids = [int(item) for item in ids_raw]
    except (TypeError, ValueError):
        return jsonify({"error": "ids must be integers"}), 400

    changed = mark_inbox_items_ankied(ids)
    return jsonify({"changed": changed, "count": pending_inbox_count()})


@app.delete("/api/inbox/delete/<int:item_id>")
def api_inbox_delete(item_id: int) -> Any:
    """Delete an inbox item by ID."""
    if not (isinstance(item_id, int) and item_id > 0):
        return jsonify({"error": "invalid item_id"}), 400

    success = delete_inbox_item(item_id)
    if not success:
        return jsonify({"error": "could not delete item"}), 400

    return jsonify(
        {"success": True, "deleted": item_id, "count": pending_inbox_count()}
    )


@app.post("/api/start")
def api_start() -> Any:
    """Start an async generation job and return its job ID.

    Returns:
        JSON response containing started `job_id`.
    """
    job_id = uuid.uuid4().hex
    form_data = request.form.to_dict(flat=True)
    thread = threading.Thread(target=_run_job, args=(job_id, form_data), daemon=True)
    thread.start()
    return jsonify({"job_id": job_id})


@app.get("/api/status/<job_id>")
def api_status(job_id: str) -> Any:
    """Return current job status, progress, and final output summary.

    Args:
        job_id: Target job identifier.

    Returns:
        JSON status payload or 404 when the job is unknown.
    """
    with JOB_LOCK:
        job = JOBS.get(job_id)
    if not job:
        return jsonify({"error": "job not found"}), 404
    payload = dict(job)
    payload.pop("pending_add", None)
    return jsonify(payload)


@app.post("/api/confirm/<job_id>")
def api_confirm(job_id: str) -> Any:
    """Confirm and execute pending Anki add for a previously reviewed job.

    Args:
        job_id: Target job identifier.

    Returns:
        JSON response with the resulting Anki summary or an error payload.
    """
    with JOB_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return jsonify({"error": "job not found"}), 404

        if not job.get("requires_confirmation"):
            return jsonify({"error": "job does not require confirmation"}), 400

        pending_add = job.get("pending_add")
        if not isinstance(pending_add, dict):
            return jsonify({"error": "no pending add payload"}), 400

    request_body = request.get_json(silent=True) or {}
    requested_choices = (
        request_body.get("choices") if isinstance(request_body, dict) else None
    )
    only_add_valid_rows_raw = (
        request_body.get("only_add_valid_rows")
        if isinstance(request_body, dict)
        else False
    )
    if isinstance(only_add_valid_rows_raw, str):
        only_add_valid_rows = only_add_valid_rows_raw.strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
    else:
        only_add_valid_rows = bool(only_add_valid_rows_raw)

    try:
        rows = _deserialize_card_rows(pending_add.get("rows", []))
        sentence_rows = _deserialize_sentence_rows(pending_add.get("sentence_rows", []))
        review_items = pending_add.get("review_items", [])

        if isinstance(requested_choices, list) and isinstance(review_items, list):
            adjusted_rows: list[CardRow] = []
            for index, row in enumerate(rows):
                choice_value = (
                    requested_choices[index] if index < len(requested_choices) else 0
                )
                try:
                    selected_index = int(choice_value)
                except (TypeError, ValueError):
                    selected_index = 0

                item = review_items[index] if index < len(review_items) else {}
                options = item.get("options", []) if isinstance(item, dict) else []
                if not isinstance(options, list) or not options:
                    adjusted_rows.append(row)
                    continue

                if selected_index < 0 or selected_index >= len(options):
                    selected_index = 0
                selected_option = options[selected_index]
                adjusted_rows.append(
                    CardRow(
                        word=row.word,
                        meaning=str(selected_option.get("meaning", row.meaning)),
                        reading=str(
                            selected_option.get("reading_preview", row.reading)
                        ),
                    )
                )

                if index < len(sentence_rows):
                    current_sentence_row = sentence_rows[index]
                    updated_back = re.sub(
                        r"Reading:\s*[^<]*",
                        f"Reading: {str(selected_option.get('reading', ''))}",
                        current_sentence_row.back,
                    )
                    sentence_rows[index] = SentenceCardRow(
                        front=current_sentence_row.front,
                        back=updated_back,
                    )

            rows = adjusted_rows

        mapping_issues: list[str] = []
        if not str(pending_add.get("field_word", "")).strip():
            mapping_issues.append("Word field mapping is empty.")
        if not str(pending_add.get("field_meaning", "")).strip():
            mapping_issues.append("Meaning field mapping is empty.")
        if not str(pending_add.get("field_reading", "")).strip():
            mapping_issues.append("Reading field mapping is empty.")

        separate_sentence_cards = bool(pending_add.get("separate_sentence_cards"))
        if separate_sentence_cards:
            if not str(pending_add.get("sentence_front_field", "")).strip():
                mapping_issues.append("Sentence front field mapping is empty.")
            if not str(pending_add.get("sentence_back_field", "")).strip():
                mapping_issues.append("Sentence back field mapping is empty.")

        row_issues: list[dict[str, Any]] = []
        valid_indexes: list[int] = []
        skipped_reason_counts: dict[str, int] = {}
        for index, row in enumerate(rows):
            reasons: list[str] = []
            if not str(row.meaning).strip():
                reasons.append("missing meaning")
            if not str(row.reading).strip():
                reasons.append("missing reading")

            if reasons:
                row_issues.append(
                    {
                        "index": index,
                        "word": row.word,
                        "reasons": reasons,
                    }
                )
                for reason in reasons:
                    skipped_reason_counts[reason] = (
                        skipped_reason_counts.get(reason, 0) + 1
                    )
            else:
                valid_indexes.append(index)

        if mapping_issues or (row_issues and not only_add_valid_rows):
            return (
                jsonify(
                    {
                        "error": "validation failed before submit",
                        "validation": {
                            "mapping": mapping_issues,
                            "rows": row_issues,
                        },
                    }
                ),
                400,
            )

        skipped_rows_count = 0
        if row_issues and only_add_valid_rows:
            skipped_rows_count = len(row_issues)
            rows = [rows[i] for i in valid_indexes]
            if separate_sentence_cards:
                sentence_rows = [
                    sentence_rows[i] for i in valid_indexes if i < len(sentence_rows)
                ]

        if rows:
            success, failed = add_rows_to_anki(
                rows,
                url=str(pending_add.get("anki_url", "")),
                deck_name=str(pending_add.get("deck_name", "")),
                model_name=str(pending_add.get("model_name", "")),
                word_field=str(pending_add.get("field_word", "Word")),
                meaning_field=str(pending_add.get("field_meaning", "Translation")),
                reading_field=str(pending_add.get("field_reading", "Reading")),
                tags=list(pending_add.get("tags", [])),
                allow_duplicates=bool(pending_add.get("allow_duplicates", False)),
            )
        else:
            success, failed = 0, 0

        summary = (
            f"Added {success} note(s) to Anki."
            if success > 0
            else "No notes were added to Anki."
        )

        if skipped_rows_count > 0:
            reason_parts = ", ".join(
                f"{reason}={count}"
                for reason, count in sorted(skipped_reason_counts.items())
            )
            summary += f" Skipped {skipped_rows_count} invalid row(s)" + (
                f" ({reason_parts})." if reason_parts else "."
            )

        if pending_add.get("separate_sentence_cards") and sentence_rows:
            sent_success, sent_failed = add_sentence_rows_to_anki(
                sentence_rows,
                url=str(pending_add.get("anki_url", "")),
                deck_name=str(pending_add.get("sentence_deck_name", "")),
                model_name=str(pending_add.get("sentence_model_name", "")),
                front_field=str(pending_add.get("sentence_front_field", "Front")),
                back_field=str(pending_add.get("sentence_back_field", "Back")),
                tags=list(pending_add.get("tags", [])),
                allow_duplicates=bool(pending_add.get("allow_duplicates", False)),
            )
            summary += (
                f" | Sentence cards: success={sent_success}, failed={sent_failed}, "
                f"deck={pending_add.get('sentence_deck_name', '')}"
            )

        inbox_ids = pending_add.get("inbox_item_ids", [])
        if success > 0 and isinstance(inbox_ids, list):
            mark_inbox_items_ankied([int(item) for item in inbox_ids])

    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 500

    _job_update(
        job_id,
        requires_confirmation=False,
        pending_add=None,
        anki_summary=summary,
    )
    return jsonify(
        {
            "anki_summary": summary,
            "skipped_rows": skipped_rows_count,
            "skipped_reasons": skipped_reason_counts,
        }
    )


@app.get("/api/review-items/<job_id>")
def api_review_items(job_id: str) -> Any:
    """Rebuild review candidate options for a pending review job.

    Args:
        job_id: Target job identifier.

    Returns:
        JSON response containing rebuilt `review_items`.
    """
    with JOB_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return jsonify({"error": "job not found", "review_items": []}), 404

        if not job.get("requires_confirmation"):
            return (
                jsonify(
                    {
                        "error": "job does not require confirmation",
                        "review_items": [],
                    }
                ),
                400,
            )

        pending_add = job.get("pending_add")
        if not isinstance(pending_add, dict):
            return jsonify({"error": "no pending add payload", "review_items": []}), 400

    try:
        words_raw = pending_add.get("source_words", [])
        words = [str(word) for word in words_raw] if isinstance(words_raw, list) else []
        rows = _deserialize_card_rows(pending_add.get("rows", []))

        review_items = _build_review_items(
            words=words,
            candidate_limit=int(pending_add.get("candidate_limit", 1)),
            include_pitch_accent=bool(pending_add.get("include_pitch_accent", False)),
            pitch_accent_theme=str(pending_add.get("pitch_accent_theme", "dark")),
            generated_rows=rows,
        )
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc), "review_items": []}), 500

    _job_update(job_id, review_items=review_items)
    return jsonify({"review_items": review_items})


@app.post("/api/review-add-word/<job_id>")
def api_review_add_word(job_id: str) -> Any:
    """Add one more reviewed word to a pending batch."""
    with JOB_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return jsonify({"error": "job not found"}), 404

        if not job.get("requires_confirmation"):
            return jsonify({"error": "job does not require confirmation"}), 400

        pending_add = job.get("pending_add")
        if not isinstance(pending_add, dict):
            return jsonify({"error": "no pending add payload"}), 400

    body = request.get_json(silent=True) or {}
    word = str(body.get("word", "")).strip()
    if not word:
        return jsonify({"error": "word is required"}), 400

    try:
        source_words_raw = pending_add.get("source_words", [])
        source_words = (
            [str(item) for item in source_words_raw]
            if isinstance(source_words_raw, list)
            else []
        )
        if word in source_words:
            return jsonify({"error": f"{word} is already in batch"}), 409

        candidate_limit = int(pending_add.get("candidate_limit", 1))
        include_pitch_accent = bool(pending_add.get("include_pitch_accent", False))
        pitch_accent_theme = str(pending_add.get("pitch_accent_theme", "dark"))
        review_items = _build_review_items(
            words=[word],
            candidate_limit=max(candidate_limit, 1),
            include_pitch_accent=include_pitch_accent,
            pitch_accent_theme=pitch_accent_theme,
            generated_rows=[],
        )
        if review_items:
            review_item = review_items[0]
            selected_index = (
                int(review_item.get("selected_index", 0))
                if isinstance(review_item, dict)
                else 0
            )
        else:
            review_item = {
                "word": word,
                "source_word": word,
                "options": [
                    {
                        "meaning": "",
                        "reading": "",
                        "reading_preview": "",
                    }
                ],
                "related_words": [],
                "selected_index": 0,
            }
            selected_index = 0

        options = (
            review_item.get("options", []) if isinstance(review_item, dict) else []
        )
        selected_option = (
            options[selected_index] if isinstance(options, list) and options else {}
        )
        pending_rows = pending_add.get("rows", [])
        if not isinstance(pending_rows, list):
            pending_rows = []
        pending_rows.append(
            {
                "word": (
                    str(review_item.get("word", word))
                    if isinstance(review_item, dict)
                    else word
                ),
                "meaning": str(selected_option.get("meaning", "")),
                "reading": str(
                    selected_option.get(
                        "reading_preview", selected_option.get("reading", "")
                    )
                ),
            }
        )
        pending_add["rows"] = pending_rows

        pending_review_items = pending_add.get("review_items", [])
        if not isinstance(pending_review_items, list):
            pending_review_items = []
        updated_review_items = [*pending_review_items, review_item]
        pending_add["review_items"] = updated_review_items

        source_words.append(word)
        pending_add["source_words"] = source_words

        current_review_items = updated_review_items
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 500

    _job_update(job_id, pending_add=pending_add, review_items=current_review_items)
    return jsonify({"review_item": review_item, "selected_index": selected_index})


@app.get("/api/search-candidates")
def api_search_candidates() -> Any:
    """Search Jisho for a single word and return review candidate options.

    Query parameters:
        word: The word to search for.
        candidate_limit: Maximum number of candidates (default 1).
        include_pitch_accent: Whether to include pitch accent SVG (default false).
        pitch_accent_theme: Theme for pitch accent SVG (default 'dark').

    Returns:
        JSON response containing a single review item.
    """
    word = request.args.get("word", "").strip()
    if not word:
        return jsonify({"error": "word parameter required"}), 400

    try:
        candidate_limit = int(request.args.get("candidate_limit", "1"))
        include_pitch_accent = _bool_from_form(request.args.get("include_pitch_accent"))
        pitch_accent_theme = request.args.get("pitch_accent_theme", "dark")

        review_items = _build_review_items(
            words=[word],
            candidate_limit=max(candidate_limit, 1),
            include_pitch_accent=include_pitch_accent,
            pitch_accent_theme=pitch_accent_theme,
            generated_rows=[],
        )

        if review_items:
            return jsonify({"review_item": review_items[0]})
        else:
            return jsonify({"review_item": None}), 404

    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 500


@app.post("/generate")
def generate() -> str:
    """Legacy endpoint retained as explicit API migration notice.

    Returns:
        HTTP 410 JSON response explaining the replacement API routes.
    """
    return (
        jsonify(
            {
                "error": "Legacy /generate route is no longer used. Use /api/start and /api/status/<job_id>.",
            }
        ),
        410,
    )  # type: ignore


if __name__ == "__main__":
    ensure_inbox_db()
    app.run(host=DEFAULT_FLASK_HOST, port=DEFAULT_FLASK_PORT, debug=False)
