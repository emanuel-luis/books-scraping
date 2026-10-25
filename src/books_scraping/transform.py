"""Parse step: raw run -> validated processed run (Parquet + rejects)."""

import hashlib
import shutil
from typing import Literal

import duckdb
from pydantic import ValidationError

from books_scraping.models import Book, ManifestEntry, Reject, StepSummary
from books_scraping.parse import ParseError, parse_product
from books_scraping.runs import RunPaths, StepError, naive_utc, step_logger, utc_now

Stage = Literal["integrity", "parse", "validate"]

_BOOKS_DDL = """
CREATE TABLE books (
    upc VARCHAR, url VARCHAR, title VARCHAR, category VARCHAR, price DECIMAL(10,2),
    currency VARCHAR, stock INTEGER, rating INTEGER, num_reviews INTEGER,
    description VARCHAR, fetched_at TIMESTAMP, run_id VARCHAR
)
"""


def transform(paths: RunPaths, run_id: str) -> StepSummary:
    started = utc_now()
    log = step_logger(run_id, "parse")
    raw = paths.raw_dir(run_id)
    if not (raw / "run.json").is_file():
        raise StepError(f"raw run {run_id} is missing or incomplete (no run.json)")

    books: dict[str, Book] = {}
    rejects: list[Reject] = []
    rows_in = duplicates = 0
    with (raw / "manifest.jsonl").open(encoding="utf-8") as manifest:
        entries = [ManifestEntry.model_validate_json(line) for line in manifest if line.strip()]

    for entry in entries:
        if entry.kind != "product" or entry.status != 200 or entry.path is None:
            continue
        rows_in += 1

        def reject(stage: Stage, error: str, entry: ManifestEntry = entry) -> None:
            rejects.append(Reject(url=entry.url, path=entry.path, stage=stage, error=error))
            log.warning("rejected %s at %s: %s", entry.url, stage, error)

        try:
            body = (raw / entry.path).read_bytes()
        except OSError as exc:
            reject("integrity", f"cannot read file: {exc}")
            continue
        if hashlib.sha256(body).hexdigest() != entry.sha256:
            reject("integrity", "sha256 does not match the manifest")
            continue
        try:
            # The site sends text/html without a charset: decode explicitly, never guess.
            fields = parse_product(body.decode("utf-8"), entry.url)
        except (UnicodeDecodeError, ParseError) as exc:
            reject("parse", str(exc))
            continue
        try:
            book = Book(**fields, fetched_at=entry.fetched_at, run_id=run_id)
        except ValidationError as exc:
            reject("validate", "; ".join(f"{e['loc']}: {e['msg']}" for e in exc.errors()))
            continue
        if book.upc in books:
            duplicates += 1
            continue
        books[book.upc] = book

    out = paths.processed_dir(run_id)
    tmp = out.with_name(f".{run_id}.tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    con = duckdb.connect()
    try:
        con.execute(_BOOKS_DDL)
        if books:
            con.executemany(
            "INSERT INTO books VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                (
                    b.upc, b.url, b.title, b.category, b.price, b.currency, b.stock, b.rating,
                    b.num_reviews, b.description, naive_utc(b.fetched_at), b.run_id,
                )
                for b in sorted(books.values(), key=lambda b: b.upc)
            ],
        )  # fmt: skip
        parquet = (tmp / "books.parquet").as_posix()
        con.execute(f"COPY books TO '{parquet}' (FORMAT parquet)")
    finally:
        con.close()
    (tmp / "rejects.jsonl").write_text(
        "".join(r.model_dump_json() + "\n" for r in rejects), encoding="utf-8"
    )
    summary = StepSummary(
        run_id=run_id,
        step="parse",
        status="ok",
        started_at=started,
        finished_at=utc_now(),
        rows_in=rows_in,
        rows_out=len(books),
        rows_rejected=len(rejects),
        duplicates=duplicates,
    )
    (tmp / "run.json").write_text(summary.model_dump_json(indent=2), encoding="utf-8")
    shutil.rmtree(out, ignore_errors=True)
    tmp.rename(out)
    log.info("%d rows in, %d out, %d rejected", rows_in, len(books), len(rejects))
    return summary
