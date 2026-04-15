.PHONY: help up down logs ps config dev-up build-dev build-dev-up release-check smoke backup test test-docker

help:
	@echo "Targets:"
	@echo "  make up            - Build and start Docker stack"
	@echo "  make down          - Stop Docker stack"
	@echo "  make logs          - Follow service logs"
	@echo "  make ps            - Show container status"
	@echo "  make config        - Render compose config"
	@echo "  make dev-up        - Start dev compose stack (uses pre-built image)"
	@echo "  make build-dev     - Build local dev image with BUILDKIT (fixes DNS issues)"
	@echo "  make build-dev-up  - Build dev image and start with compose"
	@echo "  make release-check - Validate release prerequisites"
	@echo "  make smoke         - Start stack and validate core endpoints"
	@echo "  make backup        - Create timestamped backup of output TSV"
	@echo "  make test          - Run local regression tests"
	@echo "  make test-docker   - Run tests inside running Docker container"

_ensure_env:
	@python -c "import os, shutil; os.path.exists('.env.docker') or (os.path.exists('.env.docker.example') and shutil.copy('.env.docker.example', '.env.docker')) or None"

up: _ensure_env
	@python scripts/docker_wrapper.py up

down:
	docker compose --env-file .env.docker down

logs:
	docker compose --env-file .env.docker logs -f

ps:
	docker compose --env-file .env.docker ps

config:
	docker compose --env-file .env.docker config

dev-up:
	docker compose -f docker-compose.dev.yml up

build-dev:
	@python scripts/docker_wrapper.py build-dev

build-dev-up: build-dev
	docker compose -f docker-compose.dev.yml up

release-check:
	@python -c "import os, shutil; os.path.exists('.env.docker') or (os.path.exists('.env.docker.example') and shutil.copy('.env.docker.example', '.env.docker')) or None"
	@python -c "import subprocess; subprocess.run(['docker', 'compose', '--env-file', '.env.docker', 'config'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)"
	@echo "Release check OK"

smoke: up
	@python scripts/docker_wrapper.py healthz

backup:
	@python -c "import shutil, os; (os.path.exists('output/anki_import.tsv') and (shutil.copy('output/anki_import.tsv', 'output/anki_import.tsv.bak'), print('Backed up to output/anki_import.tsv.bak'))) or (not os.path.exists('output/anki_import.tsv') and print('No TSV file to backup'))"

test:
	python -m unittest discover -s tests -p "test_*.py" -v

test-docker:
	docker exec jisho2anki python -m unittest discover -s tests -p "test_*.py" -v
