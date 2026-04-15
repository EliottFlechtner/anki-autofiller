from __future__ import annotations

from pathlib import Path

from flask import Flask, render_template, request

from anki_connect_client import add_rows_to_anki, add_sentence_rows_to_anki
from io_utils import normalize_words, write_tsv
from pipeline import build_rows

app = Flask(__name__)
DEFAULT_DECK_NAME = "Keio::TestApp"
DEFAULT_MODEL_NAME = "Japanese (Basic & Reversed)"
DEFAULT_EXPRESSION_FIELD = "Expression"
DEFAULT_SENTENCE_DECK_NAME = f"{DEFAULT_DECK_NAME}::Examples"


def _bool_from_form(value: str | None) -> bool:
    return value == "on"


@app.get("/")
def index() -> str:
    return render_template("index.html")


@app.post("/generate")
def generate() -> str:
    words_block = request.form.get("words", "")
    words = normalize_words(words_block.splitlines())

    if not words:
        return render_template("index.html", error="Please enter at least one word.")

    pause_seconds = float(request.form.get("pause_seconds", "0.0") or "0.0")
    candidate_limit = int(request.form.get("candidate_limit", "3") or "3")
    sentence_count = int(request.form.get("sentence_count", "2") or "2")
    include_sentences = _bool_from_form(request.form.get("include_sentences"))
    include_pitch_accent = _bool_from_form(request.form.get("include_pitch_accent"))
    separate_sentence_cards = _bool_from_form(
        request.form.get("separate_sentence_cards")
    )

    rows, sentence_rows = build_rows(
        words=words,
        pause_seconds=pause_seconds,
        candidate_limit=candidate_limit,
        sentence_count=sentence_count,
        include_sentences=include_sentences,
        separate_sentence_cards=separate_sentence_cards,
        include_pitch_accent=include_pitch_accent,
        interactive_review=False,
        progress_printer=None,
    )

    output_path_raw = (
        request.form.get("output_path", "anki_import.tsv").strip() or "anki_import.tsv"
    )
    output_path = Path(output_path_raw)
    include_header = _bool_from_form(request.form.get("include_header"))
    write_tsv(rows=rows, output_path=output_path, include_header=include_header)

    anki_summary = ""
    if _bool_from_form(request.form.get("anki_connect")):
        anki_url = request.form.get("anki_url", "http://127.0.0.1:8765").strip()
        deck_name = (
            request.form.get("deck_name", DEFAULT_DECK_NAME).strip()
            or DEFAULT_DECK_NAME
        )
        model_name = (
            request.form.get("model_name", DEFAULT_MODEL_NAME).strip()
            or DEFAULT_MODEL_NAME
        )
        field_word = (
            request.form.get("field_word", DEFAULT_EXPRESSION_FIELD).strip()
            or DEFAULT_EXPRESSION_FIELD
        )
        field_meaning = (
            request.form.get("field_meaning", "Meaning").strip() or "Meaning"
        )
        field_reading = (
            request.form.get("field_reading", "Reading").strip() or "Reading"
        )
        allow_duplicates = _bool_from_form(request.form.get("allow_duplicates"))
        tags_raw = request.form.get("tags", "")
        tags = [tag.strip() for tag in tags_raw.split(",") if tag.strip()]
        sentence_deck_name = (
            request.form.get("sentence_deck_name", DEFAULT_SENTENCE_DECK_NAME).strip()
            or DEFAULT_SENTENCE_DECK_NAME
        )
        sentence_model_name = (
            request.form.get("sentence_model_name", "Basic").strip() or "Basic"
        )
        sentence_front_field = (
            request.form.get("sentence_front_field", "Front").strip() or "Front"
        )
        sentence_back_field = (
            request.form.get("sentence_back_field", "Back").strip() or "Back"
        )

        if not deck_name or not model_name:
            return render_template(
                "index.html",
                error="For AnkiConnect mode, deck name and model name are required.",
                preview=rows,
                output_path=str(output_path),
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

    return render_template(
        "index.html",
        preview=rows,
        output_path=str(output_path),
        message=f"Generated {len(rows)} rows.",
        anki_summary=anki_summary,
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
