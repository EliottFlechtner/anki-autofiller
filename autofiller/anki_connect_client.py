"""Thin AnkiConnect client for creating decks and adding notes."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from .models import CardRow, SentenceCardRow


VOCAB_DECK_CONFIG_NAME = "Jisho2Anki::Shared Deck Options"
VOCAB_DECK_CONFIG_NEW_PER_DAY = 20
VOCAB_DECK_CONFIG_REVIEW_PER_DAY = 200
_VOCAB_DECK_CONFIG_ID: int | None = None


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

    existing = invoke(url, "modelNames", {})
    if isinstance(existing, list) and model_name in existing:
        templates_result = invoke(url, "modelTemplates", {"modelName": model_name})
        existing_templates = (
            templates_result if isinstance(templates_result, dict) else {}
        )

        first_template_name = "Word -> Reading+Translation"
        if first_template_name not in existing_templates and existing_templates:
            first_template_name = list(existing_templates.keys())[0]

        second_template_name = "Translation -> Word+Reading"
        if second_template_name not in existing_templates:
            legacy_second_name = "Word+Reading -> Translation"
            if legacy_second_name in existing_templates:
                second_template_name = legacy_second_name
            elif len(existing_templates) >= 2:
                second_template_name = list(existing_templates.keys())[1]

        desired_templates = {
            first_template_name: {
                "Front": card_templates[0]["Front"],
                "Back": card_templates[0]["Back"],
            },
            second_template_name: {
                "Front": card_templates[1]["Front"],
                "Back": card_templates[1]["Back"],
            },
        }

        invoke(
            url,
            "updateModelTemplates",
            {"model": {"name": model_name, "templates": desired_templates}},
        )
        invoke(
            url,
            "updateModelStyling",
            {"model": {"name": model_name, "css": css}},
        )
        return

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


def ensure_vocab_deck_config(url: str) -> int:
    """Create or reuse the shared deck options group for Jisho2Anki decks."""
    global _VOCAB_DECK_CONFIG_ID
    if _VOCAB_DECK_CONFIG_ID is not None:
        return _VOCAB_DECK_CONFIG_ID

    config = None
    deck_names = invoke(url, "deckNames", {})
    if isinstance(deck_names, list):
        for deck_name in deck_names:
            deck_config = invoke(url, "getDeckConfig", {"deck": deck_name})
            if (
                isinstance(deck_config, dict)
                and deck_config.get("name") == VOCAB_DECK_CONFIG_NAME
            ):
                config = deck_config
                break

    if config is None:
        default_config = invoke(url, "getDeckConfig", {"deck": "Default"})
        if not isinstance(default_config, dict):
            raise RuntimeError("Could not load the default Anki deck options.")

        clone_result = invoke(
            url,
            "cloneDeckConfigId",
            {"name": VOCAB_DECK_CONFIG_NAME, "cloneFrom": default_config["id"]},
        )
        if not isinstance(clone_result, int):
            raise RuntimeError("Could not create the shared Jisho2Anki deck options.")

        config = default_config
        config["id"] = clone_result
        config["name"] = VOCAB_DECK_CONFIG_NAME

    config["name"] = VOCAB_DECK_CONFIG_NAME
    config["new"]["perDay"] = VOCAB_DECK_CONFIG_NEW_PER_DAY
    config["rev"]["perDay"] = VOCAB_DECK_CONFIG_REVIEW_PER_DAY

    saved = invoke(url, "saveDeckConfig", {"config": config})
    if not saved:
        raise RuntimeError("Could not save the shared Jisho2Anki deck options.")

    _VOCAB_DECK_CONFIG_ID = int(config["id"])
    return _VOCAB_DECK_CONFIG_ID


def assign_vocab_deck_config(url: str, deck_names: list[str]) -> None:
    """Assign the shared vocab deck options group to the given decks."""
    if not deck_names:
        return

    config_id = ensure_vocab_deck_config(url)
    result = invoke(
        url,
        "setDeckConfigId",
        {"decks": deck_names, "configId": config_id},
    )
    if not result:
        raise RuntimeError("Could not assign the shared Jisho2Anki deck options.")


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

    assign_vocab_deck_config(url, deck_names)

    result = invoke(url, "addNotes", {"notes": notes})
    if not isinstance(result, list):
        raise RuntimeError("Unexpected AnkiConnect response for addNotes.")

    success = sum(1 for note_id in result if note_id is not None)
    failed = len(result) - success
    return success, failed
