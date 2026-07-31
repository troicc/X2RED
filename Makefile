.PHONY: install dev test lint migrate extension

install:
	python -m pip install -e '.[dev,publisher]'
	python -m playwright install chromium

dev:
	x2red serve --host 127.0.0.1 --port 8787 --reload

test:
	pytest -q

lint:
	ruff check apps/api

migrate:
	x2red migrate

extension:
	@echo "Load extension/chrome as an unpacked Chrome extension"
