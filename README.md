# Jisho2Anki

[![Compose Smoke](https://github.com/EliottFlechtner/Jisho2Anki/actions/workflows/compose-smoke.yml/badge.svg)](https://github.com/EliottFlechtner/Jisho2Anki/actions/workflows/compose-smoke.yml)
[![Docker Release](https://github.com/EliottFlechtner/Jisho2Anki/actions/workflows/docker-release.yml/badge.svg)](https://github.com/EliottFlechtner/Jisho2Anki/actions/workflows/docker-release.yml)
[![Unit Tests](https://github.com/EliottFlechtner/Jisho2Anki/actions/workflows/tests.yml/badge.svg)](https://github.com/EliottFlechtner/Jisho2Anki/actions/workflows/tests.yml)
[![Latest Release](https://img.shields.io/github/v/release/EliottFlechtner/Jisho2Anki?display_name=tag)](https://github.com/EliottFlechtner/Jisho2Anki/releases)
[![GHCR Image](https://img.shields.io/badge/GHCR-ghcr.io%2Feliottflechtner%2Fjisho2anki-2ea44f)](https://ghcr.io/eliottflechtner/jisho2anki)

Jisho2Anki turns plain Japanese word lists into Anki-ready cards with much less manual work. It combines dictionary lookup, optional review, and export/import paths in one project so you can stay focused on learning rather than formatting notes.

## What it does

- Builds vocab cards from one-word-per-line input.
- Exports to TSV for standard Anki import workflows.
- Optionally sends notes directly to desktop Anki with AnkiConnect.
- Supports review-before-add so you can choose the best candidate per word.
- Can enrich cards with:
  - furigana
  - Jisho example sentences
  - pitch accent SVG rendering
- Offers both CLI and Web UI, powered by the same core pipeline.

## Default note model

When direct Anki mode is enabled, Jisho2Anki uses this model by default (and can auto-create it if missing):

- Jisho2Anki::Vocab (Kanji-Reading-Translation)

Default fields:

1. Word
2. Reading
3. Translation

## Quick setup

### Prerequisites

- Python 3.12+
- Node.js 20 LTS (for frontend build/dev)
- Desktop Anki + AnkiConnect (for direct add mode)

### Install dependencies

```bash
python3 -m pip install -r requirements.txt
```

If you plan to use the web frontend locally:

```bash
cd frontend
npm install
cd ..
```

## Run options

### Web UI (recommended)

```bash
python3 web_app.py
```

Open: `http://127.0.0.1:5000`

The web app is best if you want visual review, easier option toggles, and inline preview before confirmation.

### CLI

Create an input file:

```text
食べる
勉強
試合
```

Generate TSV:

```bash
python3 jisho2anki.py --input words.txt --output anki_import.tsv --include-header
```

Direct add to Anki:

```bash
python3 jisho2anki.py \
  --input words.txt \
  --output anki_import.tsv \
  --anki-connect \
  --deck-name "Example" \
  --model-name "Jisho2Anki::Vocab (Kanji-Reading-Translation)"
```

### Docker

```bash
cp .env.docker.example .env.docker
make up
```

Open: `http://127.0.0.1:5000`

Useful commands:

```bash
make logs
make smoke
make down
```

## AnkiConnect setup (for direct add)

1. Open desktop Anki.
2. Go to Tools -> Add-ons -> Get Add-ons.
3. Install AnkiConnect with code `2055492159`.
4. Restart Anki.
5. Keep Anki running while using Jisho2Anki.

Optional connection test:

```bash
curl -s http://127.0.0.1:8765 -X POST -d '{"action":"version","version":6}'
```

## Web workflow at a glance

1. Paste words into the main input area.
2. Pick options (sentences/furigana/pitch/review).
3. Click Generate Cards.
4. In review mode, choose candidates per row.
5. Confirm and add to Anki or export via TSV.

## Review and quality controls

- Review queue supports per-row meaning/reading choice.
- Related words can be added into the current review batch.
- Validation runs before final confirmation and can skip invalid rows when enabled.
- Row order is preserved from input through submission.

## Performance tuning

Jisho2Anki exposes performance settings in CLI and Web UI, including `max_workers`, `candidate_limit`, and pause controls.

Practical guidance:

- Increase `max_workers` for larger batches.
- Lower `candidate_limit` when speed matters more than choice variety.
- Keep pause at `0` for fastest runs.

Recent versions also apply worker parallelism to review generation, not only initial row building.

## Inbox support

The project includes an inbox flow for collecting words and importing pending items into the main generation/review pipeline.

For public capture pages (for example GitHub Pages), use a shared passphrase and enforce it in Supabase RLS via header `x-j2a-capture-token`.

Environment variables:

- `VITE_SUPABASE_URL`
- `VITE_SUPABASE_ANON_KEY`
- `ANKI_JISHO2ANKI_SUPABASE_CAPTURE_TOKEN` (for local app calls to Supabase; legacy alias: `ANKI_AUTOFILLER_SUPABASE_CAPTURE_TOKEN`)

This README intentionally stays focused on core project usage. For environment-specific inbox hosting/configuration details, see the documentation links below.

## Project structure

- autofiller/: Core Python package (config, pipeline, web API, integrations)
- frontend/: React + Vite SPA
- templates/: SPA shell template
- tests/: Unit and API regression tests
- config/: Docker/deployment configuration
- docs/: Guides, troubleshooting, standards, and changelog

## Documentation

- [Getting Started](docs/README.md)
- [Example Workflow](docs/EXAMPLE.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [Project Structure](docs/PROJECT_STRUCTURE.md)
- [Contributing](docs/CONTRIBUTING.md)
- [Windows Development](docs/WINDOWS_DEV.md)
- [Release Standards](docs/RELEASE_STANDARDS.md)
- [Changelog](docs/CHANGELOG.md)

## Notes

- Meanings/readings are fetched from Jisho lookups.
- If no match is found, non-word fields may remain blank.
- Duplicate input words are removed while preserving first-seen order.
