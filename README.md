# books-scraping

> A small, re-runnable ingestion pipeline: it crawls [Books to Scrape](https://books.toscrape.com/)
> into a raw landing zone, validates the pages into Parquet and upserts them into DuckDB.

[![ci](https://github.com/emanuel-luis/books-scraping/actions/workflows/ci.yml/badge.svg)](https://github.com/emanuel-luis/books-scraping/actions/workflows/ci.yml)
![license](https://img.shields.io/github/license/emanuel-luis/books-scraping)
![python](https://img.shields.io/badge/python-3.12-blue)

Books to Scrape is a sandbox catalogue built for scraping practice (1,000 books on 50 listing
pages). The pipeline treats it like any other external source.

## What this demonstrates

- Layered ingestion: raw HTML landing with a manifest (URL, HTTP status, UTC fetch time,
  SHA-256), validated Parquet, and a DuckDB serving layer.
- Idempotent, re-runnable steps: raw runs are immutable, parsing is deterministic, and the load
  upserts by a natural key (the book's UPC). Loading the same run twice changes nothing,
  loading an older run never overwrites newer data, and a run parsed again (after a parser fix)
  reloads cleanly: snapshots it no longer has are dropped, and a book seen in an earlier run
  falls back to that run's price and stock.
- Data contracts and quality checks at every boundary: checksum verification of raw files,
  pydantic models, rejects written with their reason, and a row-count reconciliation after the
  load.
- Run metadata: each step records `run_id`, UTC start and finish, rows in, out and rejected in
  `pipeline_runs`.
- Polite, resilient HTTP: robots.txt, an explicit User-Agent, a rate limit, and retries with
  exponential backoff.
- Offline tests on saved HTML fixtures with an 85 % coverage gate, mypy strict, CI, and a
  Docker image.

## Architecture

![Architecture and data flow: the operator runs the CLI, fetch crawls books.toscrape.com into the raw layer (pages, manifest, run.json), parse validates the pages into Parquet and rejects, load upserts them into DuckDB in one transaction with a boundary check, and the optional fx step adds Frankfurter rates for the books_priced view; contracts and checks sit beside each step.](docs/diagrams/data-flow.svg)

Source: [data-flow.d2](docs/diagrams/data-flow.d2).

| Layer | Location | Written by | Contents |
| --- | --- | --- | --- |
| raw | `data/raw/<run_id>/` | `fetch` | response bytes as received under `pages/` (mirrors the URL path), `manifest.jsonl`, `run.json` |
| processed | `data/processed/<run_id>/` | `parse` | `books.parquet` (rows that passed the contract), `rejects.jsonl`, `run.json` |
| serving | `data/warehouse.duckdb` | `load`, `fx` | tables `books`, `book_snapshots`, `pipeline_runs`, `fx_rates`; view `books_priced` |

`run_id` is the UTC start time of the fetch (`20261025T134427Z`), so runs sort in time order.

## Tech stack

Python 3.12 · httpx · tenacity · selectolax · pydantic · DuckDB · Parquet · Typer · uv · ruff ·
mypy · pytest · hypothesis · Docker · GitHub Actions

## Quickstart

Needs [uv](https://docs.astral.sh/uv/) and make.

```bash
git clone https://github.com/emanuel-luis/books-scraping && cd books-scraping
make demo
```

`make demo` crawls 40 books from two listing pages, loads them, adds FX rates and prints the
table counts. Without make:

```bash
uv sync --locked
uv run books-scraping run --limit 40 --max-pages 2 --fx
uv run books-scraping stats
```

With Docker (data in a named volume):

```bash
docker build -t books-scraping .
docker run --rm -v books-scraping-data:/data books-scraping run --limit 20 --fx
docker run --rm -v books-scraping-data:/data books-scraping stats
```

## CLI

| Command | What it does |
| --- | --- |
| `books-scraping fetch [--limit N] [--max-pages N]` | crawl into a new raw run and print its `run_id` |
| `books-scraping parse [--run-id ID]` | raw → processed (default: the latest successful raw run) |
| `books-scraping load [--run-id ID]` | processed → DuckDB (default: the latest processed run) |
| `books-scraping fx` | load ECB rates for the currencies found in `books` |
| `books-scraping run [--limit N] [--max-pages N] [--fx]` | fetch → parse → load (→ fx) |
| `books-scraping stats` | row counts, the last pipeline runs, books per category |

A full crawl (no `--limit`) makes about 1,050 requests and takes around ten minutes at the
default rate of two requests per second. Steps exit with code 1 on failure, and logs go to
stderr with UTC timestamps, the `run_id` and the step.

What `run --fx` does, step by step on one `run_id`:

![Sequence of books-scraping run --fx: the CLI creates the raw run directory, reads robots.txt, fetches listing and product pages into the raw layer and writes run.json last; parse checks each page and writes Parquet, rejects and run.json; load upserts DuckDB in one transaction with a boundary check and records pipeline_runs; fx reads the currencies, calls Frankfurter and upserts fx_rates.](docs/diagrams/user-flows-run.svg)

Source: [user-flows-run.d2](docs/diagrams/user-flows-run.d2).

## Data contracts and quality checks

| Boundary | Check | On failure |
| --- | --- | --- |
| site → raw | robots.txt allows the URL, the host is the configured one, and the URL maps to a file inside the run directory | skipped and counted |
| site → raw | HTTP status; retries on transport errors, 429 and 5xx | recorded in the manifest, crawl continues |
| raw → processed | `run.json` exists (the fetch finished) | the step fails |
| raw → processed | file SHA-256 equals the manifest's | reject, stage `integrity` |
| raw → processed | page parses; `Book` contract (UPC is 16 hex chars, price ≥ 0 with 2 decimals, ISO currency, rating 1 to 5, stock ≥ 0) | reject, stage `parse` or `validate` |
| raw → processed | duplicate UPC inside a run | first kept, rest counted |
| processed → serving | snapshot rows for the run equal the Parquet rows | the load rolls back and fails |

Prices are stored as scraped: amount plus currency (GBP on this site). Conversion lives in the
optional `fx` step and the `books_priced` view, so the core pipeline needs no third-party API.

## Serving layer

| Table | Key | Contents |
| --- | --- | --- |
| `books` | `upc` | current state of each book, `first_seen_run_id`, `last_seen_run_id` |
| `book_snapshots` | `run_id`, `upc` | price, stock and rating per run (history) |
| `pipeline_runs` | `run_id`, `step` | status, UTC start and finish, rows in, out and rejected, details as JSON |
| `fx_rates` | `rate_date`, `base`, `quote` | ECB reference rates from Frankfurter |
| `books_priced` (view) | | `books` with `price_eur`, `price_usd`, `price_brl` at the latest rate |

Timestamps are `TIMESTAMP` columns holding UTC.

![Data model of the DuckDB serving layer: books keyed by UPC, book_snapshots keyed by run_id and UPC, pipeline_runs keyed by run_id and step, fx_rates keyed by rate date, base and quote, and the books_priced view that adds prices in EUR, USD and BRL; the dashed arrows are logical joins, since only primary keys are declared.](docs/diagrams/data-model.svg)

Source: [data-model.d2](docs/diagrams/data-model.d2).

## Configuration

Every setting is optional and none is a secret. Copy `.env.example` to `.env` to override.

| Variable | Default | Purpose |
| --- | --- | --- |
| `BOOKS_BASE_URL` | `https://books.toscrape.com/` | first listing page |
| `BOOKS_DATA_DIR` | `data` | root of the three layers (`/data` in the image) |
| `BOOKS_USER_AGENT` | `books-scraping/<version> (+repo URL)` | sent with every request |
| `BOOKS_MIN_INTERVAL_S` | `0.5` | minimum seconds between requests; a robots.txt `Crawl-delay` raises it |
| `BOOKS_TIMEOUT_S` | `20` | HTTP timeout |
| `BOOKS_MAX_RETRIES` | `4` | attempts per request |
| `BOOKS_FX_URL` | `https://api.frankfurter.dev/v1` | FX source (no key) |
| `BOOKS_FX_QUOTES` | `EUR,USD,BRL` | currencies to convert to |
| `BOOKS_LOG_LEVEL` | `INFO` | log level |

## Development

```bash
make install       # uv sync --locked
make lint          # ruff check, ruff format --check, mypy (what CI runs)
make test          # offline tests with the 85 % coverage gate
make test-network  # the one test that hits the live site
make help          # every target
```

The diagrams are [D2](https://d2lang.com/) sources in `docs/diagrams/`, rendered to the SVGs
next to them with one pinned D2 version (CI fails when a committed SVG is stale). These targets
need bash (Linux, macOS or WSL):

```bash
make d2-install                       # the pinned D2 (Linux x86_64), checksum verified
make diagrams                         # render every docs/diagrams/*.d2 to SVG
make diagrams-check                   # render, then fail if a committed SVG differs
make diagrams-watch NAME=data-flow    # live preview in the browser while editing
```

## Project structure

```
src/books_scraping/
  cli.py        Typer commands
  config.py     settings from BOOKS_* env vars
  fetch.py      HTTP client (robots.txt, rate limit, retries) and crawl -> raw layer
  parse.py      pure HTML parsers (listing and product pages)
  transform.py  raw -> processed: integrity check, contracts, rejects, Parquet
  load.py       processed -> DuckDB: schema, upserts, run metadata
  fx.py         optional FX step
  models.py     pydantic contracts
  runs.py       run ids, layer paths, step logger
tests/          offline tests; fixtures/ holds saved pages from the site
docs/           decisions log, refactor plan, diagrams/ (D2 sources and rendered SVGs)
```

## History

The first version (2022) drove Firefox through Selenium and wrote to SQLite from a single class
constructor. The 2026 rewrite replaced it with the layered pipeline above; the reasons are in
[docs/DECISIONS.md](docs/DECISIONS.md).

## License

[MIT](LICENSE)
