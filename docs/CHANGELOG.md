# Changelog

All notable changes to this project will be documented in this file.

## [1.1.0] - 2026-04-19

### Added
- **Sentence target-word highlighting** in generated examples (bold red emphasis) for both inline and separate sentence card modes.
- **Regression coverage for sentence cleaning and option parity**:
  - New sentence extraction test coverage for source citation stripping.
  - Expanded API and pipeline tests for added-word behavior and sentence rendering consistency.

### Changed
- **Added recommendation words now reuse active generation settings** from the review session (furigana, pitch accent, sentence mode/deck options).
- **Review flow consistency improvements** so inline sentence handling matches final confirmed card output.

### Fixed
- Stripped trailing source citation text from Jisho example English sentences before card generation.
- Corrected add/confirm mapping behavior so repeated added words no longer drift from selected meaning/reading context.

## [1.0.5] - 2026-04-19

### Added
- **Web access hardening controls** for the Flask UI/API:
  - Optional HTTP Basic Auth gate via runtime env.
  - Optional IP allowlist enforcement (except `/healthz`).
- **Supabase capture token support** across frontend and backend:
  - Capture page passphrase field and persisted token UX.
  - Header forwarding (`X-J2A-Capture-Token`) for Supabase inbox writes.
  - Docker/env wiring for `ANKI_JISHO2ANKI_SUPABASE_CAPTURE_TOKEN`.
- **Shared deck options preset flow** for Jisho2Anki decks with regression coverage.

### Changed
- **GitHub Pages behavior** now defaults to capture-only mode so the main settings page is not exposed on public Pages hosting.
- Frontend structure was split into focused components for clarity:
  - `CapturePanel`
  - `StatusColumn`
  - `SettingsColumn`
- Backend web layer was split into helper modules to reduce `web_app.py` size and improve maintainability:
  - `autofiller/web/form_utils.py`
  - `autofiller/web/review_utils.py`

### Fixed
- Fixed vocab model template naming/sync behavior during model creation updates.
- Fixed release-cycle regressions around capture/review paths while preserving existing API test patch points.

## [1.0.4] - 2026-04-18

### Added
- **Playwright end-to-end UI regression suite** for key web workflows:
  - Anki model/deck option loading.
  - Generate -> review -> confirm path with selection payload checks.
  - Inbox overlay import and delete flows.
- Frontend scripts for E2E execution (`npm run test:e2e`, `npm run test:e2e:headed`).

### Changed
- **Review item generation now uses `max_workers` parallelism** in web review-before-Anki mode.
  - Preserves original row order while parallelizing Jisho review candidate lookups.
  - Extends performance tuning behavior so review generation follows the same worker setting used during row build.

### Fixed
- Restored stable React hook execution order in the SPA to avoid blank-page runtime rendering failures.
- Added backend regression coverage to ensure review generation receives `max_workers` from request settings.

## [1.0.3] - 2026-04-17

### Added
- **Interactive review-before-Anki flow** in the web UI:
  - Per-word candidate selection with step-through review controls.
  - Related-word recommendations from Jisho with in-review “Add To Batch”.
  - Backend endpoint to append related words into active review jobs (`/api/review-add-word/<job_id>`).
- **Review candidate API support**:
  - Endpoint for single-word candidate fetch (`/api/search-candidates`).
  - Endpoint to rebuild review candidates for pending jobs (`/api/review-items/<job_id>`).
- **Expanded regression coverage**:
  - New API tests for add-word append behavior, duplicate rejection, and per-row choice mapping.
  - Additional tests for pitch accent SVG rendering and review candidate extraction behavior.

### Changed
- **Candidate ranking/extraction logic** now prioritizes exact-match Jisho entries for review options.
- Compound/related Jisho entries are separated into a **Related words** suggestion section.
- Anki submission summary messages were simplified to a cleaner, user-friendly format.
- Generated preview rendering now supports inline pitch SVG display in the web UI.

### Fixed
- Fixed review add-to-batch persistence so newly added words are included in final confirm-to-Anki submission.
- Fixed row-to-choice mapping bug where multiple added words could reuse the same meaning/reading during confirmation.
- Fixed review queue UX to append background-added words without forcing immediate navigation to the new item.
- Fixed generated preview list/count updates after adding related words to the batch.
- Removed noisy progress/log panel output from the status area.

## [1.0.2] - 2026-04-16

### Added
- **Project reorganization**: Cleaner structure with `docs/` and `config/` directories for better navigation
  - All documentation centralized in `docs/` (CHANGELOG, CONTRIBUTING, TROUBLESHOOTING, PROJECT_STRUCTURE, etc.)
  - All Docker/config files centralized in `config/` (Dockerfile, docker-compose variants, .env files)
- **Comprehensive documentation**:
  - `CONTRIBUTING.md`: Developer setup, coding standards, branching, testing guidelines
  - `TROUBLESHOOTING.md`: Common issues with solutions (Docker, AnkiConnect, Windows, networking)
  - `PROJECT_STRUCTURE.md`: Directory overview, module descriptions, key concepts
- **GitHub Actions CI/CD workflows**:
  - Windows smoke test workflow for integration testing
  - Windows unit test workflow for test suite validation
  - Enhanced diagnostics and error handling in smoke tests
- **Docker Compose enhancements**:
  - Linux host support via `docker-compose.linux-host.yml` override
  - Improved environment variable handling across platforms
- **Anki model improvements**:
  - Enhanced Anki model creation and CLI field descriptions
  - New unit tests for AnkiConnect note submission and model creation
- **Python variable consistency**: Updated Makefile and scripts to use `PYTHON` variable throughout

### Changed
- Makefile Python detection now uses OS-aware logic (Windows vs Unix)
  - Windows: Uses `python` directly (assumes PATH configuration)
  - Unix/Linux: Uses existing conditional detection (python3, python, etc.)
- Docker volume mount paths corrected after directory reorganization
- Build process updated to reference new `config/Dockerfile` location
- CI/CD workflows updated to reflect new directory structure

### Fixed
- Docker volume mounts: Changed from `./` to `../` to correctly mount repository root
- Docker build-dev path resolution after config/ reorganization
- Container startup issues where app files weren't found due to incorrect mounts
- Cross-platform Python detection on Windows (fixes make command failures)
- Smoke test diagnostics: Added container status checks and Docker setup verification

### Tested
- All make targets verified with new directory structure
- Docker container builds and runs successfully
- GitHub Actions workflows passing on Windows and Linux
- AnkiConnect integration tests included

## [1.0.1] - 2026-04-15

### Added
- **Windows Docker support**: Full Docker Desktop compatibility without WSL/bash requirement
- `docker-compose.windows.yml` override for Windows-specific settings (user, AnkiConnect URL, addon paths)
- `scripts/docker_wrapper.py`: Cross-platform Python wrapper for consistent Docker Compose control
- Updated `WINDOWS_DEV.md` with verified setup instructions
- `contrib/CONTRIBUTING.md`, `TROUBLESHOOTING.md`, `PROJECT_STRUCTURE.md` for developer onboarding

### Changed
- Refactored Makefile to use Python instead of shell scripts for true cross-platform compatibility
- `.env.docker` now uses Linux defaults; Windows overrides applied via compose file
- `scripts/docker-up.sh` now detects Windows and applies appropriate overrides
- Pitched accent addon path handling: Linux (`${HOME}/.local/share/Anki2/addons21/...`), Windows (`${APPDATA}/Anki2/addons21/...`)
- AnkiConnect URL: Linux uses `127.0.0.1:8765`, Windows/Mac use `host.docker.internal:8765`

### Fixed
- Permission denied errors on Windows when writing to `/app/output/anki_import.tsv` (now runs as root on Windows)
- Docker build-dev target now skips incompatible `DOCKER_BUILDKIT` and `--network=host` flags on Windows
- `make` commands now work natively on Windows without bash/MinGW

### Tested
- All make commands verified on Windows: `make up/down/logs/ps/config/release-check/backup/test`
- Docker health checks working on Windows
- GitHub Actions CI/CD smoke tests passing on Linux
- Cross-platform compatibility maintained

## [1.0.0] - 2026-04-15

### Added
- Initial stable v1.0.0 release marker in the Python package (`autofiller.__version__`).
- In-code documentation pass across core runtime modules.

### Changed
- Updated Jisho HTTP User-Agent to use package version dynamically.
- Updated README release/tag examples for v1.x and linked changelog usage.

### Notes
- This release is intended to be the first stable cross-platform (Linux + Windows) baseline.
