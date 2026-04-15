# Anki Autofiller

Small tool to speed up Japanese vocab note creation for Anki.

Input is a word list (one word per line). Output is cards with fields:

1. `Word`
2. `Meaning`
3. `Reading`

For your Anki setup, the generator now targets your existing furigana-friendly note type:

1. `Japanese (Basic & Reversed)`
2. Fields: `Expression`, `Meaning`, `Reading`, `Lesson Number`

It can also:

- append Jisho example sentences into `Meaning`
- split Jisho examples into separate sentence cards
- auto-generate pitch accent SVG and embed it into `Reading`
- add notes directly to Anki via AnkiConnect
- run in either CLI mode or local web UI mode

## Setup

```bash
python3 -m pip install -r requirements.txt
```

## Quick Start (Web UI)

```bash
python3 web_app.py
```

Open `http://127.0.0.1:5000`, paste words line-by-line, and click `Generate Cards`.

The web page can:

- save a TSV file
- optionally push notes directly to Anki through AnkiConnect
- use the existing Japanese note type by default
- keep pitch accent generation on by default

## Quick Start (CLI)

Create `words.txt`:

```txt
食べる
勉強
試合
```

Generate TSV:

```bash
python3 anki_autofiller.py --input words.txt --output anki_import.tsv --include-header
```

Interactive candidate review (CLI only):

```bash
python3 anki_autofiller.py --input words.txt --output anki_import.tsv --interactive-review --sentence-count 2
```

Pitch accent is on by default in both CLI and web mode. Use `--no-pitch-accent` to disable it.

To keep answers short, use `--separate-sentence-cards` so sentence examples are created as separate notes.

## AnkiConnect Setup (What To Do)

AnkiConnect talks to the desktop Anki app locally, so you do not need to provide a mail/password in an `.env` file for this workflow.

1. Open Anki.
2. Go to `Tools -> Add-ons -> Get Add-ons...`.
3. Install AnkiConnect with code `2055492159`.
4. Restart Anki.
5. Keep Anki open while running this tool.
6. In Anki, confirm your note type has fields matching your mapping (`Expression`, `Meaning`, `Reading`, `Lesson Number`).

Optional connection check from terminal:

```bash
curl -s http://127.0.0.1:8765 -X POST -d '{"action":"version","version":6}'
```

If it returns a JSON result, AnkiConnect is reachable.

## Direct Add To Anki (CLI)

```bash
python3 anki_autofiller.py \
  --input words.txt \
  --output anki_import.tsv \
  --anki-connect \
  --deck-name "Keio::TestApp" \
  --model-name "Japanese (Basic & Reversed)" \
  --field-word "Expression" \
  --field-meaning "Meaning" \
  --field-reading "Reading" \
  --tags "jp,vocab,autofill"
```

The web UI defaults the deck to `Keio::TestApp` and the model to `Japanese (Basic & Reversed)`.

## Pitch Accent Add-On

Your installed add-on exposes a `Pitch Accent` menu in Anki and an editor toolbar button.

- For bulk processing, use `Tools -> Pitch Accent -> bulk add` and point it at the deck/model after import.
- For one-off edits, open a note in the editor and use the pitch accent toolbar icon.
- The generator now reproduces that output by embedding the pitch accent SVG directly into the Reading field, so the add-on is optional after import.

## Project Structure

- `anki_autofiller.py`: backward-compatible CLI entrypoint
- `cli.py`: CLI argument parsing and orchestration
- `web_app.py`: local Flask UI
- `pipeline.py`: card-building pipeline
- `jisho_client.py`: Jisho lookup + sentence scraping
- `anki_connect_client.py`: AnkiConnect calls
- `io_utils.py`: word parsing and TSV writing
- `models.py`: shared dataclasses

## Notes

- Meanings/readings are fetched from Jisho's public API.
- Example sentences are parsed from Jisho search result HTML.
- If a word is not found, fields are left blank except `Word`.
- Duplicate words are automatically removed while preserving first-seen order.