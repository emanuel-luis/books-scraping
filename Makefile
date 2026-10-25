.PHONY: help install lint format test test-fast test-network demo docker-build docker-run clean

help:           ## list the targets
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-14s %s\n", $$1, $$2}'

install:        ## sync the environment from uv.lock
	uv sync --locked

lint:           ## what CI's lint job runs
	uv run ruff check
	uv run ruff format --check
	uv run mypy

format:         ## apply ruff fixes and formatting
	uv run ruff check --fix
	uv run ruff format

test:           ## offline tests with the 85 % coverage gate
	uv run pytest --cov=books_scraping --cov-fail-under=85

test-fast:      ## offline tests without coverage
	uv run pytest -q

test-network:   ## the tests that hit the live site
	uv run pytest -m network

demo:           ## small live run, then the table counts
	uv run books-scraping run --limit 40 --max-pages 2 --fx
	uv run books-scraping stats

docker-build:   ## build the image
	docker build -t books-scraping .

docker-run:     ## run the image, data in the books-scraping-data volume
	docker run --rm -v books-scraping-data:/data books-scraping

clean:          ## remove caches and build output
	rm -rf .venv .mypy_cache .pytest_cache .ruff_cache .hypothesis .coverage htmlcov dist
