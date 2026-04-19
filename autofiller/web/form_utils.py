"""Form and query parsing helpers used by the Flask web layer."""

from __future__ import annotations

from typing import Mapping


def parse_inbox_item_ids(raw: str | None) -> list[int]:
    """Parse comma-separated positive inbox IDs into a stable unique list."""
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


def bool_from_form(value: str | None, default: bool = False) -> bool:
    """Parse checkbox/form values into a deterministic boolean."""
    if value is None:
        return default

    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def value_from_form(form_data: Mapping[str, str], key: str, default: str) -> str:
    """Read and trim a form value, falling back to default when blank."""
    raw = form_data.get(key)
    if raw is None:
        return default

    stripped = raw.strip()
    return stripped if stripped else default
