#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(dirname "$0")/.."
cd "$ROOT_DIR"
mkdir -p output

if [[ ! -f .env.docker && -f .env.docker.example ]]; then
	cp .env.docker.example .env.docker
	echo "Created .env.docker from .env.docker.example"
fi

COMPOSE_ARGS=()
if [[ -f .env.docker ]]; then
	COMPOSE_ARGS+=(--env-file .env.docker)
fi

# Add Windows-specific overrides if on Windows
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" || "$OSTYPE" == "win32" ]]; then
	COMPOSE_ARGS+=(-f docker-compose.yml -f docker-compose.windows.yml)
fi

	exit 1
fi

docker compose "${COMPOSE_ARGS[@]}" up -d "$@"
echo "Jisho2Anki is starting at http://127.0.0.1:${APP_PORT:-5000}"
