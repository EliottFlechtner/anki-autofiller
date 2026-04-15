#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(dirname "$0")/.."
cd "$ROOT_DIR"

mkdir -p output output/backups

SOURCE_FILE="output/anki_import.tsv"
if [[ ! -f "$SOURCE_FILE" ]]; then
  echo "No output TSV found at $SOURCE_FILE"
  exit 1
fi

STAMP="$(date +%Y%m%d-%H%M%S)"
DEST_FILE="output/backups/anki_import-${STAMP}.tsv"
cp "$SOURCE_FILE" "$DEST_FILE"
echo "Backup created: $DEST_FILE"
