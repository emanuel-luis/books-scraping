# Refactor plan: Selenium scraper → ingestion pipeline

Goal: replace the 2022 Selenium scraper with a small, testable ingestion pipeline for
[books.toscrape.com](https://books.toscrape.com/) (a sandbox built for scraping practice):

```
fetch → raw landing → parse + validate → processed → load → serving (→ optional fx)
```

Done when the CLI runs the whole flow against the live site, the tests run offline on saved
HTML fixtures, CI is green, the Docker image builds and the README describes the new flow.
Decisions behind this plan: [DECISIONS.md](DECISIONS.md).

## Layers and layout

| Layer | Location | Written by | Contents |
| --- | --- | --- | --- |
| raw | `data/raw/<run_id>/` | `fetch` | `pages/<url path>` (response bytes as received), `manifest.jsonl`, `run.json` |
| processed | `data/processed/<run_id>/` | `parse` | `books.parquet` (validated rows), `rejects.jsonl`, `run.json` |
| serving | `data/warehouse.duckdb` | `load`, `fx` | `books`, `book_snapshots`, `pipeline_runs`, `fx_rates`, view `books_priced` |

- `run_id` = UTC start time, `YYYYMMDDTHHMMSSZ`. Sorts lexicographically in time order.
- Raw pages mirror the URL path: `https://books.toscrape.com/catalogue/page-2.html` →
  `pages/catalogue/page-2.html`; a path ending in `/` or empty → `index.html`.
- `data/` is configurable (`BOOKS_DATA_DIR`) and gitignored.

## Package (`src/books_scraping/`, src layout, `py.typed`, no work at import time)

| Module | Responsibility |
| --- | --- |
| `__init__.py` | `__version__` from `importlib.metadata` |
| `__main__.py` | `python -m books_scraping` → CLI |
| `config.py` | `Settings` (pydantic-settings, env prefix `BOOKS_`, reads `.env`) |
| `runs.py` | `new_run_id()`, `utc_now()`, `RunPaths` (raw/processed dirs, warehouse path), latest-run lookup |
| `models.py` | pydantic v2 contracts (frozen, `extra="forbid"`): `ManifestEntry`, `Book`, `Reject`, `StepSummary`, `FxRate` |
| `parse.py` | pure functions: `parse_listing(html, page_url) -> Listing(product_urls, next_url)`, `parse_product(html, url) -> dict`, `parse_price("£51.77") -> (Decimal, "GBP")`, `parse_rating("Three") -> 3`, `parse_stock("In stock (22 available)") -> 22` |
| `fetch.py` | `Fetcher` (httpx client, robots.txt, rate limit, retries) and `crawl()` writing the raw layer |
| `transform.py` | parse step: raw run → processed run (integrity check, validation, rejects, Parquet) |
| `load.py` | DuckDB DDL and upserts from processed Parquet; `pipeline_runs` rows |
| `fx.py` | Frankfurter client → `FxRate` rows → `fx_rates` upsert |
| `cli.py` | Typer app |

## Contracts (`models.py`)

- `ManifestEntry`: `url`, `kind` (`robots` / `listing` / `product`), `status` (int),
  `path` (relative to the run dir, `None` when no body was saved), `sha256` (64 hex or `None`),
  `bytes` (int), `fetched_at` (aware UTC datetime).
- `Book`: `upc` (`^[0-9a-f]{16}$`, the natural key), `url`, `title` (non-empty), `category`
  (non-empty), `price` (`Decimal`, >= 0, 2 places), `currency` (`^[A-Z]{3}$`, mapped from the
  symbol: `£`→GBP, `€`→EUR, `$`→USD; any other symbol is a reject), `stock` (int >= 0),
  `rating` (1..5), `num_reviews` (int >= 0), `description` (`str | None`), `fetched_at`
  (aware UTC), `run_id`.
- `Reject`: `url`, `path`, `stage` (`integrity` / `parse` / `validate`), `error`.
- `StepSummary` (`run.json` of each layer): `run_id`, `step`, `status`, `started_at`,
  `finished_at`, `rows_in`, `rows_out`, `rows_rejected`, plus step-specific counters
  (`listing_pages`, `product_pages`, `failed`, `skipped_robots`, `duplicates`).
- `FxRate`: `rate_date` (date), `base`, `quote`, `rate` (`Decimal` > 0, parsed from the JSON
  text, never via float), `source` (`"frankfurter (ECB)"`), `fetched_at`.

## Steps

### fetch (network)

- httpx client, explicit User-Agent
  `books-scraping/<version> (+https://github.com/emanuel-luis/books-scraping)`, timeout from
  settings. The transport and the sleep/clock functions are injectable (tests use
  `httpx.MockTransport` and a fake sleep; no real waiting in tests).
- robots.txt first (`urllib.robotparser`): 2xx → parse; 401/403 → disallow all; other 4xx →
  allow all (the live site answers 404); 5xx after retries → abort. Every URL is checked with
  `can_fetch` before the request; a disallowed URL is skipped and counted. A `Crawl-delay`
  raises the minimum interval.
- Rate limit: at least `BOOKS_MIN_INTERVAL_S` (default 0.5 s) between requests.
- tenacity retries on `httpx.TransportError` and on 429/500/502/503/504: exponential backoff,
  `BOOKS_MAX_RETRIES` attempts (default 4). A page that still fails is recorded in the manifest
  with its status and no body; the crawl continues.
- Crawl: start at `BOOKS_BASE_URL` (catalogue page 1), follow the `next` link, collect product
  URLs (absolute, via `urljoin`) until `--limit` products or `--max-pages` listing pages; then
  fetch each product page. Response bytes are saved exactly as received (`response.content`).
- The manifest is appended and flushed per page, so a crash leaves a valid partial manifest.
  `run.json` is written last; the parse step refuses a raw run without it.
- A raw run directory is immutable: fetch never writes into an existing `run_id`.

### parse (offline, deterministic)

- Reads `manifest.jsonl`; for each `product` entry with status 200: re-hash the file and compare
  with the manifest `sha256` (mismatch → reject, stage `integrity`), decode as UTF-8 explicitly
  (the site sends `Content-Type: text/html` with no charset; never let a library guess, or `£`
  becomes `Â£`), `parse_product`, validate into `Book`.
- Duplicate UPCs inside one run: keep the first, count the rest.
- Writes `books.parquet` (through DuckDB `COPY ... (FORMAT parquet)`; explicit column types,
  `DECIMAL(10,2)` for price), `rejects.jsonl` and `run.json` into a temp dir, then renames it
  over `processed/<run_id>/`. Same raw input → same processed output.

### load (offline, idempotent)

DDL (`CREATE TABLE IF NOT EXISTS`):

- `books`: `upc` PK, `url`, `title`, `category`, `price DECIMAL(10,2)`, `currency`, `stock`,
  `rating`, `num_reviews`, `description`, `first_seen_run_id`, `last_seen_run_id`,
  `updated_at`. Upsert keyed by `upc`; loading an older run never overwrites newer state
  (update only when the incoming `run_id` >= `last_seen_run_id`; use `ON CONFLICT DO UPDATE
  ... WHERE` or `MERGE INTO`, whichever DuckDB supports cleanly).
- `book_snapshots`: PK (`run_id`, `upc`), `price`, `currency`, `stock`, `rating`, `fetched_at`.
  Price/stock history per run.
- `pipeline_runs`: PK (`run_id`, `step`), `status`, `started_at`, `finished_at`, `rows_in`,
  `rows_out`, `rows_rejected`, `detail` (JSON text). Load records the fetch and parse
  summaries from the `run.json` files plus its own row.
- `fx_rates`: PK (`rate_date`, `base`, `quote`), `rate DECIMAL(18,6)`, `source`, `fetched_at`.
- View `books_priced`: every book with `price_eur`, `price_usd`, `price_brl` (rounded to 2)
  from the latest `rate_date` for its currency; NULL when no rate is loaded.
- Timestamps are UTC. If DuckDB's `TIMESTAMPTZ` needs an extra dependency to round-trip, store
  `TIMESTAMP` holding UTC and say so in the column comment; a test asserts the round trip.
- Boundary check after the load: `book_snapshots` rows for the run == rows in `books.parquet`;
  a mismatch fails the step.
- Loading the same run twice leaves every table unchanged (except `pipeline_runs.finished_at`).

### fx (network, optional)

- `GET {BOOKS_FX_URL}/latest?base=<currency>&symbols=<BOOKS_FX_QUOTES>` for each distinct
  currency in `books` (GBP). Default URL `https://api.frankfurter.dev/v1`, quotes `EUR,USD,BRL`.
- Upsert into `fx_rates`; same retry policy as fetch.

## CLI (Typer, entry point `books-scraping`)

| Command | Does |
| --- | --- |
| `fetch [--limit N] [--max-pages N]` | crawl into a new raw run; prints the `run_id` |
| `parse [--run-id ID]` | raw → processed; default: latest complete raw run |
| `load [--run-id ID]` | processed → DuckDB; default: latest processed run |
| `fx` | load FX rates for the currencies in `books` |
| `run [--limit N] [--max-pages N] [--fx/--no-fx]` | fetch → parse → load (→ fx) |
| `stats` | row counts per table, last `pipeline_runs` rows, books per category (top 10) |
| `--version` | prints the version |

Logging to stderr, UTC timestamps, `run_id` and `step` in every line of a step. Exit code 0
on success, 1 on a failed step.

## Configuration (`BOOKS_` env vars, `.env.example` commented)

`BASE_URL` (`https://books.toscrape.com/`), `DATA_DIR` (`data`), `USER_AGENT`,
`MIN_INTERVAL_S` (0.5), `TIMEOUT_S` (20), `MAX_RETRIES` (4), `FX_URL`, `FX_QUOTES`
(`EUR,USD,BRL`), `LOG_LEVEL` (`INFO`). No secrets.

## Tests (offline by default)

- Fixtures in `tests/fixtures/site/`, saved once from the live site with their bytes intact:
  `index.html`, `catalogue/page-2.html`, `catalogue/page-50.html` (no `next`), three product
  pages (one with a description; one copied and edited to drop the description, noted in
  `tests/fixtures/README.md`). A Frankfurter JSON fixture.
- `test_parse.py`: exact fields for "A Light in the Attic" (UPC `a897fe39b1053632`, £51.77,
  stock 22, rating 3, category Poetry); listing next link and 20 product URLs; last page has no
  next; hypothesis round trip for `parse_price`.
- `test_fetch.py` (MockTransport): limit and max-pages respected; manifest sha256 matches the
  files; robots disallow skips; 404 robots allows; 503 then 200 retries; rate limiter asks the
  fake sleep for the right interval; existing run dir refused.
- `test_transform.py`: sha mismatch → integrity reject; broken product page → reject; same raw
  → byte-identical-content processed output (compare rows, not file bytes).
- `test_load.py`: idempotent double load; older run does not regress `books`; snapshot count
  check; `books_priced` with and without FX rows; UTC round trip.
- `test_fx.py`, `test_cli.py` (CliRunner: `--help`, `--version`, `parse`/`load`/`stats` on a
  fixture raw run).
- One `@pytest.mark.network` test against the live site (`--limit 2`), deselected by default.

## Tooling

- `pyproject.toml` only, `uv_build` backend, `requires-python = ">=3.12"`, `.python-version`
  3.12, committed `uv.lock`, PEP 735 `dev` group (pytest, pytest-timeout, pytest-cov,
  hypothesis, ruff, mypy). Author `Emanuel Luis <emanuel.filho08@gmail.com>`, license MIT.
- ruff line-length 100, `extend-select = ["BLE"]`; mypy strict on `src`.
- pytest `-ra --strict-markers --strict-config`, `timeout`, `-m "not network"` in addopts.
- Makefile with `##` help: `install`, `lint` (= CI lint job), `format`, `test` (coverage gate
  85 %), `test-fast` (no coverage), `test-network`, `demo` (`run --limit 40 --max-pages 2 --fx`
  then `stats`), `docker-build`, `docker-run`, `clean`.
- Dockerfile: multi-stage, uv in the builder, pinned `python:3.12.x-slim-bookworm` runtime,
  non-root user, `BOOKS_DATA_DIR=/data` volume, `HEALTHCHECK` running `books-scraping
  --version`, entry point `books-scraping`, default `run --limit 20`. `.dockerignore`.
- CI `ci.yml`: push to `main`, pull_request, workflow_dispatch, weekly cron; lint → test and
  docker build (+ `--version` smoke); actions pinned by SHA, `permissions: {}` at the top and
  `contents: read` per job, `persist-credentials: false`, `timeout-minutes`, setup-uv cache,
  `uv sync --locked`. `security.yml`: pip-audit on `uv export --frozen`, zizmor on the
  workflows. Dependabot weekly, grouped, for github-actions and uv.
- `.gitattributes` with `* text=auto eol=lf`.

## Docs

README (English, per the portfolio README standard: what it demonstrates, a flow diagram with
the three layers named (D2 since 2026-10-27, see DECISIONS 13), tech stack, one-command quickstart, CLI, data contracts and quality
checks, configuration, structure, politeness notes, license), CHANGELOG (`[Unreleased]`),
MIT LICENSE, CLAUDE.md (Commands, Repo map, Invariants, Conventions).

## Removed

`main.py`, `requirements.txt`, `src/__init__.py`, `src/scrapping.py`, `src/database/`
(Selenium, geckodriver path, import-time engine and session, currencylayer call).
