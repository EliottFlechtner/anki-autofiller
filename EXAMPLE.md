# EXAMPLE: Add New Words To Example Deck

This guide shows how to add a new list of words to a new Anki deck called `Example`.

## Prerequisites

- Anki desktop app is running.
- AnkiConnect add-on is installed and enabled.
- In this project, use the virtual environment Python:

```bash
./.venv/bin/python
```

## Option A: Web App (Recommended)

1. Start the app:

```bash
./.venv/bin/python web_app.py
```

Optional, if you want live frontend editing while you work on the page:

```bash
cd frontend
npm install
```

```bash
./.venv/bin/python scripts/dev.py
```

The launcher automatically picks free ports for both the Vite dev server and Flask.

If you want the lower-level manual flow instead, run `cd frontend && npm install && npm run dev` in one terminal and start Flask in another with `ANKI_AUTOFILLER_VITE_DEV_SERVER_URL=http://127.0.0.1:<vite-port> ./.venv/bin/python web_app.py`.

2. Open `http://127.0.0.1:5000`.

3. In `Basic` tab:
- Paste your word list (one word per line).
- Keep `Auto add pitch accent SVG` enabled.
- Optional: enable `Put sentences in separate cards` if you want short vocab answers.

4. In `Advanced` tab:
- Optional: set `Preset` or `Env file path` if you keep extra profiles in files.
- Click `Load preset defaults` after choosing a preset or env file so the visible fields match what will be submitted.
- Set `Deck name` to `Example`.
- Keep model as `Japanese (Basic & Reversed)` unless you want another note type.
- For faster generation, set `Max workers` to `6` to `10`.
- Keep `Enable AnkiConnect add` checked.

5. Click `Generate Cards`.

You will see a live progress area with:
- current status (`running`, `done`, or `error`)
- completed count (`x / total`)
- rolling logs

Note: the app auto-creates missing decks, so `Example` will be created automatically.

Preset behavior:

- The selected preset or env file populates the form when you click `Load preset defaults`.
- The values visible in the form are the values that get submitted.
- If you change a field after loading a preset, your manual edit overrides that field for the current run.
- Presets are templates, not hidden modes. They do not disable the other fields; they just fill them with defaults.

## Option B: CLI (Fast + Scriptable)

1. Put your list into `words.txt` (one word per line).

2. Run:

```bash
./.venv/bin/python anki_autofiller.py \
  --input words.txt \
  --output anki_import.tsv \
  --include-header \
  --anki-connect \
  --deck-name "Example" \
  --model-name "Japanese (Basic & Reversed)" \
  --field-word "Expression" \
  --field-meaning "Meaning" \
  --field-reading "Reading" \
  --sentence-count 1 \
  --max-workers 8 \
  --tags "example,autofill"
```

### Optional: add your own env file overrides

```bash
./.venv/bin/python anki_autofiller.py \
  --env-file configs/my-sample.env \
  --anki-connect
```

### If you want separate sentence cards

Add these flags:

```bash
  --separate-sentence-cards \
  --sentence-deck-name "Example::Examples" \
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
