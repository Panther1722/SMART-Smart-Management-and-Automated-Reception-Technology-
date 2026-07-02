.PHONY: up down build test lint validate-env hooks install-dev logs bootstrap ci-local monitoring scale

up:
	docker compose up --build -d

down:
	docker compose down

build:
	docker compose build

monitoring:
	docker compose -f docker-compose.yml -f docker-compose.monitoring.yml up -d

scale:
	docker compose up -d --scale backend=2

test:
	cd backend && pip install -r requirements.txt -r requirements-dev.txt && pytest

lint:
	cd backend && pip install ruff && ruff check app tests

validate-env:
	python scripts/validate_env.py

hooks:
	pre-commit install

bootstrap:
	cd backend && pip install -r requirements.txt -r requirements-dev.txt
	cd frontend && npm ci
	pre-commit install

install-dev: bootstrap

ci-local: lint validate-env test build

logs:
	docker compose logs -f backend

rotate-key:
	python scripts/rotate_admin_key.py
