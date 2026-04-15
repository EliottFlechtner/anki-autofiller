.PHONY: help up down logs ps config dev-up release-check

help:
	@echo "Targets:"
	@echo "  make up            - Build and start Docker stack"
	@echo "  make down          - Stop Docker stack"
	@echo "  make logs          - Follow service logs"
	@echo "  make ps            - Show container status"
	@echo "  make config        - Render compose config"
	@echo "  make dev-up        - Start dev compose stack"
	@echo "  make release-check - Validate release prerequisites"

up:
	./scripts/docker-up.sh

down:
	./scripts/docker-down.sh

logs:
	./scripts/docker-logs.sh

ps:
	docker compose --env-file .env.docker ps

config:
	docker compose --env-file .env.docker config

dev-up:
	docker compose -f docker-compose.dev.yml up --build

release-check:
	@test -f .env.docker || cp .env.docker.example .env.docker
	docker compose --env-file .env.docker config >/dev/null
	@echo "Release check OK"
