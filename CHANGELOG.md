# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

The 2022 Selenium scraper is replaced by a layered ingestion pipeline (version 0.1.0 in
`pyproject.toml`).

### Added

- `books_scraping` package with a Typer CLI: `fetch`, `parse`, `load`, `fx`, `run`, `stats`.
- Raw layer: response bytes as received, a `manifest.jsonl` (URL, status, UTC time, SHA-256) and
  a `run.json` per run. robots.txt check, explicit User-Agent, rate limit, retries with backoff.
- Processed layer: pydantic contracts, checksum verification, `rejects.jsonl`, Parquet output.
- Serving layer in DuckDB: `books` (upsert by UPC), `book_snapshots`, `pipeline_runs`,
  `fx_rates` and the `books_priced` view.
- Optional FX step using Frankfurter (ECB reference rates, no API key).
- Offline tests on saved HTML fixtures with an 85 % coverage gate, ruff, mypy strict.
- Multi-stage Docker image running as a non-root user.
- GitHub Actions: lint, tests, Docker build, pip-audit, zizmor; Dependabot.
- MIT license, decisions log and refactor plan in `docs/`.
- D2 diagrams in `docs/diagrams/` (data flow, the `run` sequence, the DuckDB data model),
  rendered to SVG with a pinned D2 0.9.0; `make diagrams`, `make diagrams-check`,
  `make diagrams-watch` and a CI `diagrams` job that fails on a stale SVG. The README shows
  them in place of the Mermaid flowchart.

### Changed

- Prices are stored as scraped (amount and currency). The old code converted GBP prices with an
  EUR rate.
- The misspelled `scrapping` module is gone; the code lives in `books_scraping`.

### Removed

- Selenium, GeckoDriver and its hardcoded Windows path, SQLAlchemy models and the
  import-time database session, `requirements.txt`, `main.py`.
- The tracked `library.db` and the duplicate `readme.md`, which collided with `README.md` on
  case-insensitive file systems.

### Security

- Removed a hardcoded currencylayer API key. It is still in the git history, so it is treated
  as compromised and must be rotated; the history is not rewritten (see `docs/DECISIONS.md`).
