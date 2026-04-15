"""File and TSV helpers for input normalization and output writing."""

from __future__ import annotations

import csv
from pathlib import Path

from .models import CardRow


def read_words_from_file(input_path: Path) -> list[str]:
    """Read words from a text file and normalize them.

    Args:
        input_path: Path to a newline-delimited source word list.

    Returns:
        Deduplicated words preserving first-seen order.

    Raises:
        FileNotFoundError: If `input_path` does not exist.
    """
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    raw_lines = input_path.read_text(encoding="utf-8").splitlines()
    return normalize_words(raw_lines)


def normalize_words(raw_lines: list[str]) -> list[str]:
    """Normalize a raw word list.

    Args:
        raw_lines: Input lines that may include blanks or duplicates.

    Returns:
        Trimmed, non-empty, deduplicated words in stable order.
    """
    cleaned = [line.strip() for line in raw_lines if line.strip()]

    seen: set[str] = set()
    words: list[str] = []
    for word in cleaned:
        if word not in seen:
            seen.add(word)
            words.append(word)
    return words


def write_tsv(rows: list[CardRow], output_path: Path, include_header: bool) -> None:
    """Write generated rows to a TSV file.

    Args:
        rows: Card rows to serialize.
        output_path: Destination path for the TSV file.
        include_header: Whether to write the `Word/Meaning/Reading` header row.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", quoting=csv.QUOTE_MINIMAL)

        if include_header:
            writer.writerow(["Word", "Meaning", "Reading"])

        for row in rows:
            writer.writerow([row.word, row.meaning, row.reading])
