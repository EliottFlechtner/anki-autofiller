# EXAMPLE: Add New Words To Slang 2026

This guide shows exactly how to add a new list of words to a new Anki deck called `Slang 2026`.

## Prerequisites

- Anki desktop app is running.
- AnkiConnect add-on is installed and enabled.
- In this project, use the virtual environment Python:

```bash
/home/shark/Documents/anki-autofiller/.venv/bin/python
```

## Option A: Web App (Recommended)

1. Start the app:

```bash
/home/shark/Documents/anki-autofiller/.venv/bin/python web_app.py
```

2. Open `http://127.0.0.1:5000`.

3. In `Basic` tab:
- Paste your word list (one word per line).
- Keep `Auto add pitch accent SVG` enabled.
- Optional: enable `Put sentences in separate cards` if you want short vocab answers.

4. In `Advanced` tab:
- Set `Preset` to `slang2026` (recommended).
- Optional: set `Env file path` if you keep extra profiles in files.
- Set `Deck name` to `Slang 2026`.
- Keep model as `Japanese (Basic & Reversed)` unless you want another note type.
- For faster generation, set `Max workers` to `6` to `10`.
- Keep `Enable AnkiConnect add` checked.

5. Click `Generate Cards`.

You will see a live progress area with:
- current status (`running`, `done`, or `error`)
- completed count (`x / total`)
- rolling logs

Note: the app auto-creates missing decks, so `Slang 2026` will be created automatically.

## Option B: CLI (Fast + Scriptable)

1. Put your list into `words.txt` (one word per line).

2. Run:

```bash
/home/shark/Documents/anki-autofiller/.venv/bin/python anki_autofiller.py \
  --preset slang2026 \
  --input words.txt \
  --output anki_import.tsv \
  --include-header \
  --anki-connect \
  --deck-name "Slang 2026" \
  --model-name "Japanese (Basic & Reversed)" \
  --field-word "Expression" \
  --field-meaning "Meaning" \
  --field-reading "Reading" \
  --sentence-count 1 \
  --max-workers 8 \
  --tags "slang2026,autofill"
```

### Optional: add your own env file overrides

```bash
/home/shark/Documents/anki-autofiller/.venv/bin/python anki_autofiller.py \
  --preset slang2026 \
  --env-file configs/my-slang.env \
  --anki-connect
```

### If you want separate sentence cards

Add these flags:

```bash
  --separate-sentence-cards \
  --sentence-deck-name "Slang 2026::Examples" \
  --sentence-model-name "Basic" \
  --sentence-front-field "Front" \
  --sentence-back-field "Back"
```

## Tips For Speed

- Use `--max-workers 8` (or around `6-10`) with `--pause-seconds 0`.
- Keep interactive review off for bulk imports.
- Reduce `--sentence-count` if you only need 1 example per word.

## Troubleshooting

- If duplicates are blocked, add `--allow-duplicates`.
- If deck does not exist, no action needed: deck is auto-created.
- If AnkiConnect fails, check Anki is open and run:

```bash
curl -s http://127.0.0.1:8765 -X POST -H 'Content-Type: application/json' -d '{"action":"version","version":6}'
```
