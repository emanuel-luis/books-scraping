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
- `make d2-install` (pinned D2 0.9.0, sha256 checked), `make diagrams` (render every
  `docs/diagrams/*.d2` to SVG), `make diagrams-check` (the CI `diagrams` job: render, fail on any
  diff), `make diagrams-watch NAME=<name>` (live preview). They need bash: on Windows run them
  in WSL, where D2 lives in `~/.local/share/d2/v0.9.0`.
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
- `docs/diagrams/`: D2 sources (`data-flow`, `user-flows-run`, `data-model`), the shared
  `_style.d2` and the committed SVGs the README shows.

## Invariants

- A raw run directory is immutable; `fetch` never writes into an existing `run_id`. `run.json`
  is written last and marks a run complete.
- Raw pages are saved as received and decoded as UTF-8 explicitly (the site sends no charset).
- Parse is deterministic: the same raw run gives the same processed rows.
- Load is idempotent and keyed by UPC; an older run never overwrites newer `books` rows.
  Reloading a reparsed run deletes its snapshots that the new Parquet lacks (only those keys:
  never delete and re-insert one key in a transaction). Snapshot count must equal the Parquet
  row count, inside one transaction.
- Every crawled URL must map inside the run dir (`url_to_relpath` refuses `..`, `\`, `:`);
  unsafe URLs are skipped before any request.
- `latest_run` picks only runs whose `run.json` says `ok`.
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
- Diagrams: edit the `.d2` source (with an editor, not `sed`: it mangles `\n` and `·`), run
  `make diagrams`, commit source and SVG together. A change to the steps, layers or DuckDB
  schema updates the matching diagram. No Mermaid.
