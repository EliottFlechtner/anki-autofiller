from __future__ import annotations

import json
import urllib.request

from models import CardRow, SentenceCardRow


def invoke(url: str, action: str, params: dict) -> object:
    payload = json.dumps({"action": action, "version": 6, "params": params}).encode(
        "utf-8"
    )
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=10) as response:
        body = response.read().decode("utf-8")

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
