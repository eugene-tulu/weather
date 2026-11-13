.PHONY: help backend-test backend-lint frontend-test frontend-lint frontend-build check compose-up compose-down

help:
	@echo "backend-test    Run backend pytest in conda env ndvi"
	@echo "backend-lint    Run ruff and black checks"
	@echo "frontend-test   Run Vitest"
	@echo "frontend-lint   Run ESLint and tsc"
	@echo "frontend-build  Run Next.js production build"
	@echo "check           Run backend + frontend checks"
	@echo "compose-up      Build and start the Docker stack"
	@echo "compose-down    Stop the Docker stack"

backend-test:
	cd backend && conda run -n ndvi python -m pytest

backend-lint:
	cd backend && conda run -n ndvi ruff check . && conda run -n ndvi black --check .

frontend-test:
	cd frontend && npm test

frontend-lint:
	cd frontend && npm run lint && npm run typecheck

frontend-build:
	cd frontend && npm run build

check: backend-test backend-lint frontend-test frontend-lint

compose-up:
	docker compose up --build

compose-down:
	docker compose down