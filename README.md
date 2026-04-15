# Jisho2Anki

[![Compose Smoke](https://github.com/EliottFlechtner/anki-autofiller/actions/workflows/compose-smoke.yml/badge.svg)](https://github.com/EliottFlechtner/anki-autofiller/actions/workflows/compose-smoke.yml)
[![Docker Release](https://github.com/EliottFlechtner/anki-autofiller/actions/workflows/docker-release.yml/badge.svg)](https://github.com/EliottFlechtner/anki-autofiller/actions/workflows/docker-release.yml)
[![Latest Release](https://img.shields.io/github/v/release/EliottFlechtner/anki-autofiller?display_name=tag)](https://github.com/EliottFlechtner/anki-autofiller/releases)
[![GHCR Image](https://img.shields.io/badge/GHCR-ghcr.io%2Feliottflechtner%2Fjisho2anki-2ea44f)](https://ghcr.io/eliottflechtner/jisho2anki)

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
- use a React + Vite SPA frontend for the web UI

## Setup

```bash
python3 -m pip install -r requirements.txt
```

For the web frontend bundle, also install the Node dependencies once:

```bash
cd frontend
npm install
```

## Docker Deployment Pipeline

If you want the simplest launch path, use Docker Compose.

1. Copy compose-specific env defaults:

```bash
cp .env.docker.example .env.docker
```

2. Start the service:

```bash
make up
```

3. Open:

`http://127.0.0.1:5000` (or the `APP_PORT` you set in `.env.docker`)

Useful commands:

```bash
./scripts/docker-logs.sh
./scripts/docker-down.sh
```

Shortcuts with Make:

```bash
cp .env.docker.example .env.docker
make up
make logs
make down
```

Additional targets:

```bash
make ps
make config
make dev-up
make release-check
make smoke
make backup
```

What this pipeline gives you:

- one-command startup (`docker-up.sh`)
- container health checks via `/healthz`
- persistent output in local `output/`
- built-in host access to desktop AnkiConnect via `host.docker.internal`

Image pinning:

- set `ANKI_JISHO2ANKI_IMAGE_TAG` in `.env.docker` (for example `v0.1`) to lock deployment to a specific release image.

If Docker build fails at `pip install` with `Temporary failure in name resolution`, that is a Docker DNS/network issue. `docker-up.sh` now pulls a prebuilt image first, and if it must build locally it fails fast instead of hanging.

Optional override in `.env.docker` when using a mirror/proxy:

```bash
PIP_INDEX_URL=https://pypi.org/simple
# PIP_EXTRA_INDEX_URL=https://your-mirror/simple
# PIP_RETRIES=1
# PIP_TIMEOUT=15
```

`make up` behavior:

- tries to start from an existing local image first (`--no-build`)
- only builds when no local image is available
- fails fast on pip DNS issues instead of hanging for a long time

`make smoke` behavior:

- starts the stack
- validates `/healthz`
- validates `/api/bootstrap`

### Ops Runbook (Minimal)

1. Start service: `make up`
2. Verify quickly: `make smoke`
3. View status: `make ps`
4. Follow logs: `make logs`
5. Backup latest TSV: `make backup`
6. Stop service: `make down`

CI smoke workflow file:

- `.github/workflows/compose-smoke.yml`

Development container mode (bind-mount source):

```bash
docker compose -f docker-compose.dev.yml up --build
```

### Automated Image Publish

GitHub Actions now builds and publishes a container image to GHCR on:

- pushes to `main`
- tags like `v0.1`, `v0.2`, etc.

Workflow file:

- `.github/workflows/docker-release.yml`

## Config Files And Presets

This project supports env-style config files with `ANKI_JISHO2ANKI_*` keys.

1. Copy `.env.example` to `.env` and edit values.
2. Optional: create additional env files and pass them with `--env-file`.
3. Optional: use built-in presets from `presets/*.env` with `--preset`.

CLI config precedence is:

1. CLI flags
2. environment variables
3. `--env-file` values
4. `--preset` values
5. `.env.local`
6. `.env`
7. hardcoded defaults

Built-in presets live in `presets/`.

Current preset set:

- `balanced`
- `turbo-import`
- `high-quality`
- `sentence-cards`
- `tsv-only`
- `safe-api`

Example:

```bash
python3 jisho2anki.py --env-file configs/my-run.env --anki-connect
```

The web app uses the same settings loader. In the browser, clicking `Load preset defaults` or changing the preset/env file repopulates the visible fields with the merged settings. The values currently shown in the form are the values that get submitted. If you edit a field after loading a preset, that manual edit wins for that submission.

In other words, the preset is a template for the visible form, not a hidden mode. The fields stay editable, and the final submission always uses whatever is visible when you click `Generate Cards`.

## Quick Start (Web UI)

```bash
python3 web_app.py
```

Open: `http://127.0.0.1:5000`

If you want Vite-managed frontend editing with live browser updates, the easiest path is the launcher script:

```bash
./.venv/bin/python scripts/dev.py
```

Open: the Flask URL printed by the launcher output (for example `http://127.0.0.1:57581`).

This starts Vite on a free local port and launches Flask with the matching dev-server URL already wired up. If you want to run the pieces manually, use `cd frontend && npm run dev` in one terminal and point `ANKI_JISHO2ANKI_VITE_DEV_SERVER_URL` at the Vite port in another.

The launcher also picks a free Flask port automatically, so it avoids the common "port already in use" startup failure.

For the normal static build, run `cd frontend && npm run build` before starting Flask.

Static pipeline summary:

```bash
cd frontend && npm run build
cd ..
python3 web_app.py
```

When you run `python3 web_app.py`, open `http://127.0.0.1:5000`. When you run `scripts/dev.py`, use the Flask URL printed in the launcher output.

The web page can:

- save a TSV file
- optionally push notes directly to Anki through AnkiConnect
- use the existing Japanese note type by default
- keep pitch accent generation on by default
- show live generation progress (status, completed count, logs)
- load preset defaults into the visible form with a single click

## Quick Start (CLI)

Create `words.txt`:

```txt
食べる
勉強
試合
```

Generate TSV:

```bash
python3 jisho2anki.py --input words.txt --output anki_import.tsv --include-header
```

Using config defaults from `.env` or a preset:

```bash
python3 jisho2anki.py --preset balanced --anki-connect
```

Interactive candidate review (CLI only):

```bash
python3 jisho2anki.py --input words.txt --output anki_import.tsv --interactive-review --sentence-count 2
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
python3 jisho2anki.py \
  --input words.txt \
  --output anki_import.tsv \
  --anki-connect \
  --deck-name "Example" \
  --model-name "Japanese (Basic & Reversed)" \
  --field-word "Expression" \
  --field-meaning "Meaning" \
  --field-reading "Reading" \
  --tags "jp,vocab,autofill"
```

The docs and example config use the `Example` deck and the model `Japanese (Basic & Reversed)`.

For a complete end-to-end example that creates and fills a new deck named `Example`, see `EXAMPLE.md`.

## Pitch Accent Add-On

Your installed add-on exposes a `Pitch Accent` menu in Anki and an editor toolbar button.

- For bulk processing, use `Tools -> Pitch Accent -> bulk add` and point it at the deck/model after import.
- For one-off edits, open a note in the editor and use the pitch accent toolbar icon.
- The generator now reproduces that output by embedding the pitch accent SVG directly into the Reading field, so the add-on is optional after import.

## Project Structure

- `autofiller/`: core package with CLI, web app, and service modules
- `jisho2anki.py`: primary CLI entrypoint
- `anki_autofiller.py`: backward-compatible CLI alias
- `cli.py`: backward-compatible CLI wrapper
- `web_app.py`: backward-compatible web wrapper
- `templates/spa.html`: React SPA mount page
- `frontend/`: Vite + React source and build config
- `scripts/dev.py`: one-command local dev launcher (Vite + Flask)
- `Dockerfile`: container image definition
- `docker-compose.yml`: default deployment stack
- `docker-compose.dev.yml`: bind-mounted dev container stack
- `scripts/docker-up.sh`: one-command Docker startup
- `scripts/docker-down.sh`: stop/remove Docker stack
- `scripts/docker-logs.sh`: follow container logs
- `presets/`: reusable env-style config presets

## Notes

- Meanings/readings are fetched from Jisho's public API.
- Example sentences are parsed from Jisho search result HTML.
- If a word is not found, fields are left blank except `Word`.
- Duplicate words are automatically removed while preserving first-seen order.