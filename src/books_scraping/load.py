"""Load step: processed Parquet -> DuckDB serving layer. Idempotent per run."""

from pathlib import Path

import duckdb

from books_scraping.models import StepSummary
from books_scraping.runs import RunPaths, StepError, naive_utc, step_logger, utc_now

# All timestamps are TIMESTAMP columns holding UTC wall-clock time (no TIMESTAMPTZ: it needs
# pytz to round-trip into Python). A test asserts the round trip.
DDL = """
CREATE TABLE IF NOT EXISTS books (
    upc VARCHAR PRIMARY KEY, url VARCHAR, title VARCHAR, category VARCHAR,
    price DECIMAL(10,2), currency VARCHAR, stock INTEGER, rating INTEGER,
    num_reviews INTEGER, description VARCHAR,
    first_seen_run_id VARCHAR, last_seen_run_id VARCHAR, updated_at TIMESTAMP
);
CREATE TABLE IF NOT EXISTS book_snapshots (
    run_id VARCHAR, upc VARCHAR, price DECIMAL(10,2), currency VARCHAR, stock INTEGER,
    rating INTEGER, fetched_at TIMESTAMP,
    PRIMARY KEY (run_id, upc)
);
CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id VARCHAR, step VARCHAR, status VARCHAR, started_at TIMESTAMP, finished_at TIMESTAMP,
    rows_in INTEGER, rows_out INTEGER, rows_rejected INTEGER, detail VARCHAR,
    PRIMARY KEY (run_id, step)
);
CREATE TABLE IF NOT EXISTS fx_rates (
    rate_date DATE, base VARCHAR, quote VARCHAR, rate DECIMAL(18,6), source VARCHAR,
    fetched_at TIMESTAMP,
    PRIMARY KEY (rate_date, base, quote)
);
CREATE OR REPLACE VIEW books_priced AS
WITH latest AS (
    SELECT base, quote, arg_max(rate, rate_date) AS rate FROM fx_rates GROUP BY base, quote
)
SELECT b.*,
    round(b.price * eur.rate, 2) AS price_eur,
    round(b.price * usd.rate, 2) AS price_usd,
    round(b.price * brl.rate, 2) AS price_brl
FROM books b
LEFT JOIN latest eur ON eur.base = b.currency AND eur.quote = 'EUR'
LEFT JOIN latest usd ON usd.base = b.currency AND usd.quote = 'USD'
LEFT JOIN latest brl ON brl.base = b.currency AND brl.quote = 'BRL';
"""

_UPSERT_BOOKS = """
INSERT INTO books
SELECT upc, url, title, category, price, currency, stock, rating, num_reviews, description,
       run_id, run_id, ?
FROM read_parquet(?)
ON CONFLICT (upc) DO UPDATE SET
    url = excluded.url, title = excluded.title, category = excluded.category,
    price = excluded.price, currency = excluded.currency, stock = excluded.stock,
    rating = excluded.rating, num_reviews = excluded.num_reviews,
    description = excluded.description, last_seen_run_id = excluded.last_seen_run_id,
    updated_at = excluded.updated_at
WHERE excluded.last_seen_run_id >= books.last_seen_run_id
"""

_UPSERT_SNAPSHOTS = """
INSERT INTO book_snapshots
SELECT run_id, upc, price, currency, stock, rating, fetched_at FROM read_parquet(?)
ON CONFLICT (run_id, upc) DO UPDATE SET
    price = excluded.price, currency = excluded.currency, stock = excluded.stock,
    rating = excluded.rating, fetched_at = excluded.fetched_at
"""

# A run parsed again can yield fewer rows (a parser fix, an integrity reject): its snapshots
# that the new Parquet no longer has are stale. Only those keys are deleted, so no key is
# deleted and re-inserted in the same transaction.
_DROP_STALE_SNAPSHOTS = """
DELETE FROM book_snapshots
WHERE run_id = ? AND upc NOT IN (SELECT upc FROM read_parquet(?))
"""

# A book is only as current as its snapshots: without any it goes, and first/last seen follow
# the remaining runs. A book that lost its newest snapshot takes price, currency, stock and
# rating back from the snapshot it now falls back to; the descriptive columns (title,
# description...) keep their last loaded values until a run that has the book is loaded again.
_DROP_ORPHAN_BOOKS = "DELETE FROM books WHERE upc NOT IN (SELECT upc FROM book_snapshots)"

_SEEN_RUNS = """
UPDATE books SET first_seen_run_id = s.first_run, last_seen_run_id = s.last_run
FROM (
    SELECT upc, min(run_id) AS first_run, max(run_id) AS last_run
    FROM book_snapshots GROUP BY upc
) s
WHERE books.upc = s.upc
  AND (books.first_seen_run_id <> s.first_run OR books.last_seen_run_id <> s.last_run)
"""

# No-op in the normal flow, where the last-seen snapshot was written from the same row.
_SYNC_LAST_SNAPSHOT = """
UPDATE books SET price = s.price, currency = s.currency, stock = s.stock, rating = s.rating
FROM book_snapshots s
WHERE s.upc = books.upc AND s.run_id = books.last_seen_run_id
  AND (books.price <> s.price OR books.currency <> s.currency
       OR books.stock <> s.stock OR books.rating <> s.rating)
"""

_UPSERT_RUN = """
INSERT INTO pipeline_runs VALUES (?,?,?,?,?,?,?,?,?)
ON CONFLICT (run_id, step) DO UPDATE SET
    status = excluded.status, started_at = excluded.started_at,
    finished_at = excluded.finished_at, rows_in = excluded.rows_in,
    rows_out = excluded.rows_out, rows_rejected = excluded.rows_rejected,
    detail = excluded.detail
"""


def connect(path: Path) -> duckdb.DuckDBPyConnection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(path))
    con.execute(DDL)
    return con


def record_run(con: duckdb.DuckDBPyConnection, summary: StepSummary) -> None:
    common = {"run_id", "step", "status", "started_at", "finished_at"}
    detail = summary.model_dump_json(exclude=common | {"rows_in", "rows_out", "rows_rejected"})
    con.execute(
        _UPSERT_RUN,
        [
            summary.run_id, summary.step, summary.status, naive_utc(summary.started_at),
            naive_utc(summary.finished_at), summary.rows_in, summary.rows_out,
            summary.rows_rejected, detail,
        ],
    )  # fmt: skip


def load_run(paths: RunPaths, run_id: str) -> StepSummary:
    started = utc_now()
    log = step_logger(run_id, "load")
    processed = paths.processed_dir(run_id)
    parquet = (processed / "books.parquet").as_posix()
    parse_json = processed / "run.json"
    if not parse_json.is_file():
        raise StepError(f"processed run {run_id} is missing or incomplete (no run.json)")
    parse_summary = StepSummary.model_validate_json(parse_json.read_text(encoding="utf-8"))

    con = connect(paths.warehouse)
    try:
        con.begin()
        try:
            expected = con.execute("SELECT count(*) FROM read_parquet(?)", [parquet]).fetchone()
            assert expected is not None
            con.execute(_UPSERT_BOOKS, [naive_utc(parse_summary.finished_at), parquet])
            con.execute(_UPSERT_SNAPSHOTS, [parquet])
            con.execute(_DROP_STALE_SNAPSHOTS, [run_id, parquet])
            con.execute(_DROP_ORPHAN_BOOKS)
            con.execute(_SEEN_RUNS)
            con.execute(_SYNC_LAST_SNAPSHOT)
            snaps = con.execute(
                "SELECT count(*) FROM book_snapshots WHERE run_id = ?", [run_id]
            ).fetchone()
            if snaps is None or snaps[0] != expected[0]:
                raise StepError(
                    f"boundary check failed: {snaps and snaps[0]} snapshots for {expected[0]} rows"
                )
            raw_json = paths.raw_dir(run_id) / "run.json"
            if raw_json.is_file():
                record_run(
                    con, StepSummary.model_validate_json(raw_json.read_text(encoding="utf-8"))
                )
            record_run(con, parse_summary)
            summary = StepSummary(
                run_id=run_id,
                step="load",
                status="ok",
                started_at=started,
                finished_at=utc_now(),
                rows_in=expected[0],
                rows_out=expected[0],
            )
            record_run(con, summary)
            con.commit()
        except BaseException:
            con.rollback()
            raise
    finally:
        con.close()
    log.info("%d books loaded", summary.rows_out)
    return summary
