.PHONY: install dev test lint migrate extension

install:
	python -m pip install -e '.[dev,publisher]'
	python -m playwright install chromium

dev:
	uvicorn app.main:app --app-dir apps/api --host 127.0.0.1 --port 8787 --reload

test:
	pytest -q

lint:
	ruff check apps/api

migrate:
	alembic upgrade head

extension:
	@echo "Load extension/chrome as an unpacked Chrome extension"
