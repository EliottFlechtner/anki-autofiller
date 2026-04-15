"""Thin AnkiConnect client for creating decks and adding notes."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from .models import CardRow, SentenceCardRow


def invoke(url: str, action: str, params: dict) -> object:
    """Invoke an AnkiConnect action and return its `result` payload."""
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
    """Add vocabulary card rows to Anki and return (success_count, failed_count)."""
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
    """Add sentence card rows to Anki and return (success_count, failed_count)."""
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
    """Create destination decks and submit note payloads through AnkiConnect."""
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
