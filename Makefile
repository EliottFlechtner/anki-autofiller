.PHONY: help up down logs ps config dev-up release-check smoke backup test test-docker

help:
	@echo "Targets:"
	@echo "  make up            - Build and start Docker stack"
	@echo "  make down          - Stop Docker stack"
	@echo "  make logs          - Follow service logs"
	@echo "  make ps            - Show container status"
	@echo "  make config        - Render compose config"
	@echo "  make dev-up        - Start dev compose stack"
	@echo "  make release-check - Validate release prerequisites"
	@echo "  make smoke         - Start stack and validate core endpoints"
	@echo "  make backup        - Create timestamped backup of output TSV"
	@echo "  make test          - Run local regression tests"
	@echo "  make test-docker   - Run tests inside running Docker container"

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

smoke: up
	@for i in $$(seq 1 30); do \
		if curl -fsS http://127.0.0.1:$${APP_PORT:-5000}/healthz >/dev/null; then \
			break; \
		fi; \
		sleep 1; \
		if [ $$i -eq 30 ]; then \
			echo "Health endpoint did not become ready in time"; \
			exit 1; \
		fi; \
	done
	@curl -fsS http://127.0.0.1:$${APP_PORT:-5000}/api/bootstrap >/dev/null
	@echo "Smoke check OK"

backup:
	./scripts/backup-output.sh

test:
	python3 -m unittest discover -s tests -p "test_*.py" -v

test-docker:
	docker exec jisho2anki python -m unittest discover -s tests -p "test_*.py" -v
