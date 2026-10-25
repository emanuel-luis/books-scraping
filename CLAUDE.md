# books-scraping

Layered ingestion pipeline for books.toscrape.com (a scraping sandbox): fetch → raw →
parse/validate → processed (Parquet) → load → serving (DuckDB), plus an optional FX step.
Portfolio repo of a data engineer: changes must keep the layers, idempotency and contracts
visible.

## Commands

- `uv sync --locked`: install (Python 3.12, dev group included).
- `make lint`: `uv run ruff check`, `uv run ruff format --check`, `uv run mypy` (the CI lint job).
- `make test`: offline pytest with `--cov-fail-under=85`. `make test-fast` skips coverage.
- `make test-network`: the `network`-marked test against the live site (deselected by default).
- `make demo`: `run --limit 40 --max-pages 2 --fx`, then `stats`.
- `make docker-build`, `make docker-run`.
- On Windows without make, run the underlying `uv run ...` commands.

## Repo map

- `src/books_scraping/cli.py`: Typer app (`fetch`, `parse`, `load`, `fx`, `run`, `stats`).
- `config.py`: `Settings`, env prefix `BOOKS_`. `runs.py`: run ids, `RunPaths`, `naive_utc`,
  step logger, `StepError`.
- `fetch.py`: `Fetcher` (robots.txt, rate limit, tenacity retries) and `crawl()` → raw layer.
- `parse.py`: pure HTML parsers (selectolax). `transform.py`: raw → processed.
- `load.py`: DuckDB DDL, upserts, `pipeline_runs`. `fx.py`: Frankfurter → `fx_rates`.
- `models.py`: pydantic contracts (`ManifestEntry`, `Book`, `Reject`, `StepSummary`, `FxRate`).
- `tests/fixtures/site/`: saved pages, served through `httpx.MockTransport`; see its README.
- `docs/DECISIONS.md`: decisions log. `docs/REFACTOR_PLAN.md`: the design.

## Invariants

- A raw run directory is immutable; `fetch` never writes into an existing `run_id`. `run.json`
  is written last and marks a run complete.
- Raw pages are saved as received and decoded as UTF-8 explicitly (the site sends no charset).
- Parse is deterministic: the same raw run gives the same processed rows.
- Load is idempotent and keyed by UPC; an older run never overwrites newer `books` rows.
  Snapshot count must equal the Parquet row count, inside one transaction.
- Prices stay as scraped (amount + currency); conversion only in `fx` / `books_priced`.
- Timestamps are aware UTC in Python and UTC `TIMESTAMP` columns in Parquet and DuckDB
  (convert with `naive_utc`).
- Tests never touch the network unless marked `network`; CI never scrapes.

## Conventions

- uv only; `pyproject.toml` + committed `uv.lock`. ruff line-length 100 with `BLE`
  (`# noqa: BLE001 - reason` on a broad except); mypy strict on `src`.
- Code, docs and commit messages in English; Conventional Commits.
- Work on a branch; the default branch is `main` (rename from `master` pending on GitHub).
- No secrets in the repo: settings come from `BOOKS_*` env vars, none of them secret.
- Record design decisions in `docs/DECISIONS.md`; update README and CHANGELOG with behavior
  changes.
