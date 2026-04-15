#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(dirname "$0")/.."
cd "$ROOT_DIR"

COMPOSE_ARGS=()
if [[ -f .env.docker ]]; then
	COMPOSE_ARGS+=(--env-file .env.docker)
fi

docker compose "${COMPOSE_ARGS[@]}" down "$@"
