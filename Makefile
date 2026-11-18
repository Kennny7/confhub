.PHONY: install test lint format run worker ui

install:
	uv sync --all-extras

test:
	uv run pytest -q

lint:
	uv run ruff check .

format:
	uv run ruff format .

run:
	uv run confhub serve

worker:
	uv run confhub worker

ui:
	uv run confhub ui

init:
	uv run confhub init
