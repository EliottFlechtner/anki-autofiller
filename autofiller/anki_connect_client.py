"""Thin AnkiConnect client for creating decks and adding notes."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from .models import CardRow, SentenceCardRow


def _field_ref(field_name: str) -> str:
    """Return an Anki template field reference like `{{Field}}`."""
    return "{{" + field_name + "}}"


def ensure_vocab_model(
    *,
    url: str,
    model_name: str,
    word_field: str,
    meaning_field: str,
    reading_field: str,
) -> None:
    """Create a Kanji/Reading/Translation note type when it does not exist.

    The generated model has two card templates so learners can practice both:
    - word -> reading + translation
    - translation -> word + reading
    """
    existing = invoke(url, "modelNames", {})
    if isinstance(existing, list) and model_name in existing:
        return

    word_ref = _field_ref(word_field)
    reading_ref = _field_ref(reading_field)
    meaning_ref = _field_ref(meaning_field)

    css = """
.card {
  font-family: "Noto Sans JP", "Hiragino Sans", "Yu Gothic", sans-serif;
  text-align: center;
  color: #1f2937;
  background: #ffffff;
  line-height: 1.5;
}
.word {
  font-size: 2.1em;
  font-weight: 700;
  margin: 0.3em 0;
}
.reading {
  font-size: 1.35em;
  margin-top: 0.35em;
}
.meaning {
  font-size: 1.15em;
  margin-top: 0.6em;
}
.sep {
  border: none;
  border-top: 1px solid #d1d5db;
  margin: 0.8em 0;
}
""".strip()

    card_templates = [
        {
            "Name": "Word -> Reading+Translation",
            "Front": ('<div class="word">' + word_ref + "</div>"),
            "Back": (
                "{{FrontSide}}"
                '<hr class="sep">'
                '<div class="reading">' + reading_ref + "</div>"
                '<div class="meaning">' + meaning_ref + "</div>"
            ),
        },
        {
            "Name": "Translation -> Word+Reading",
            "Front": ('<div class="meaning">' + meaning_ref + "</div>"),
            "Back": (
                "{{FrontSide}}"
                '<hr class="sep">'
                '<div class="word">' + word_ref + "</div>"
                '<div class="reading">' + reading_ref + "</div>"
            ),
        },
    ]

    invoke(
        url,
        "createModel",
        {
            "modelName": model_name,
            "inOrderFields": [word_field, reading_field, meaning_field],
            "css": css,
            "isCloze": False,
            "cardTemplates": card_templates,
        },
    )


def invoke(url: str, action: str, params: dict) -> object:
    """Invoke an AnkiConnect action and return its `result` payload.

    Args:
        url: AnkiConnect HTTP endpoint URL.
        action: AnkiConnect action name.
        params: Action payload parameters.

    Returns:
        The `result` value from the AnkiConnect response.

    Raises:
        RuntimeError: If AnkiConnect is unreachable or returns an error field.
    """
    payload = json.dumps({"action": action, "version": 6, "params": params}).encode(
        "utf-8"
    )
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            body = response.read().decode("utf-8")
    except urllib.error.URLError as exc:
        reason = str(exc.reason) if getattr(exc, "reason", None) else str(exc)
        docker_hint = ""
        if "host.docker.internal" in url and "Errno 111" in reason:
            docker_hint = (
                " If you are running in Docker on Linux, this usually means AnkiConnect "
                "is listening only on 127.0.0.1. Either run the app outside Docker, or "
                "configure AnkiConnect to bind to 0.0.0.0 so containers can reach it."
            )
        raise RuntimeError(
            f"Could not reach AnkiConnect at {url}: {reason}.{docker_hint}"
        ) from exc

    data = json.loads(body)
    if data.get("error"):
        raise RuntimeError(f"AnkiConnect error: {data['error']}")
    return data.get("result")


def add_rows_to_anki(
    rows: list[CardRow],
    *,
    url: str,
    deck_name: str,
    model_name: str,
    word_field: str,
    meaning_field: str,
    reading_field: str,
    tags: list[str],
    allow_duplicates: bool,
) -> tuple[int, int]:
    """Add vocabulary card rows to Anki.

    Args:
        rows: Card rows to submit.
        url: AnkiConnect endpoint.
        deck_name: Target deck name.
        model_name: Target note type/model.
        word_field: Model field name for source word/expression.
        meaning_field: Model field name for meaning.
        reading_field: Model field name for reading.
        tags: Tags to attach to created notes.
        allow_duplicates: Whether duplicate notes are allowed.

    Returns:
        Tuple of `(success_count, failed_count)`.
    """
    ensure_vocab_model(
        url=url,
        model_name=model_name,
        word_field=word_field,
        meaning_field=meaning_field,
        reading_field=reading_field,
    )

    notes: list[dict] = []
    for row in rows:
        notes.append(
            {
                "deckName": deck_name,
                "modelName": model_name,
                "fields": {
                    word_field: row.word,
                    meaning_field: row.meaning,
                    reading_field: row.reading,
                },
                "tags": tags,
                "options": {"allowDuplicate": allow_duplicates},
            }
        )

    return add_notes(
        notes=notes,
        url=url,
    )


def add_sentence_rows_to_anki(
    rows: list[SentenceCardRow],
    *,
    url: str,
    deck_name: str,
    model_name: str,
    front_field: str,
    back_field: str,
    tags: list[str],
    allow_duplicates: bool,
) -> tuple[int, int]:
    """Add sentence card rows to Anki.

    Args:
        rows: Sentence card rows to submit.
        url: AnkiConnect endpoint.
        deck_name: Target sentence deck.
        model_name: Target sentence note type/model.
        front_field: Model field name for sentence front text.
        back_field: Model field name for sentence back text.
        tags: Tags to attach to created notes.
        allow_duplicates: Whether duplicate notes are allowed.

    Returns:
        Tuple of `(success_count, failed_count)`.
    """
    notes: list[dict] = []
    for row in rows:
        notes.append(
            {
                "deckName": deck_name,
                "modelName": model_name,
                "fields": {
                    front_field: row.front,
                    back_field: row.back,
                },
                "tags": tags,
                "options": {"allowDuplicate": allow_duplicates},
            }
        )

    return add_notes(
        notes=notes,
        url=url,
    )


def add_notes(*, notes: list[dict], url: str) -> tuple[int, int]:
    """Create destination decks and submit note payloads through AnkiConnect.

    Args:
        notes: Raw Anki note payload objects.
        url: AnkiConnect endpoint URL.

    Returns:
        Tuple of `(success_count, failed_count)`.

    Raises:
        RuntimeError: If `addNotes` returns a non-list result.
    """
    if not notes:
        return 0, 0

    # Ensure all target decks exist before note creation.
    deck_names = sorted(
        {note.get("deckName", "") for note in notes if note.get("deckName")}
    )
    for deck_name in deck_names:
        invoke(url, "createDeck", {"deck": deck_name})

    result = invoke(url, "addNotes", {"notes": notes})
    if not isinstance(result, list):
        raise RuntimeError("Unexpected AnkiConnect response for addNotes.")

    success = sum(1 for note_id in result if note_id is not None)
    failed = len(result) - success
    return success, failed
