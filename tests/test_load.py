import json
from datetime import date, datetime
from decimal import Decimal

import pytest
from conftest import A_LIGHT, PAGES, FakeSite, crawl_site

from books_scraping import load
from books_scraping.config import Settings
from books_scraping.load import connect, load_run
from books_scraping.models import ManifestEntry
from books_scraping.runs import RunPaths, StepError
from books_scraping.transform import transform

OLD, NEW = "20260101T000000Z", "20260102T000000Z"
TABLES = ("books", "book_snapshots", "fx_rates")


def dump(paths: RunPaths) -> dict[str, list[tuple[object, ...]]]:
    con = connect(paths.warehouse)
    try:
        out = {t: con.execute(f"SELECT * FROM {t} ORDER BY ALL").fetchall() for t in TABLES}
        out["runs"] = con.execute(
            "SELECT run_id, step, status, rows_in, rows_out, rows_rejected, detail "
            "FROM pipeline_runs WHERE step <> 'load' ORDER BY ALL"
        ).fetchall()
        out["load_runs"] = con.execute(
            "SELECT run_id, step, rows_out FROM pipeline_runs WHERE step = 'load' ORDER BY ALL"
        ).fetchall()
        return out
    finally:
        con.close()


def query(paths: RunPaths, sql: str) -> list[tuple[object, ...]]:
    con = connect(paths.warehouse)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def prepare(settings: Settings, run_id: str, price: bytes | None = None) -> RunPaths:
    pages = dict(PAGES)
    if price is not None:
        pages["/" + A_LIGHT] = pages["/" + A_LIGHT].replace("£51.77".encode(), price)
    crawl_site(settings, FakeSite(pages=pages), run_id=run_id)
    paths = RunPaths(settings.data_dir)
    transform(paths, run_id)
    return paths


def test_load_twice_changes_nothing(settings: Settings, raw_run: str) -> None:
    paths = RunPaths(settings.data_dir)
    transform(paths, raw_run)
    load_run(paths, raw_run)
    first = dump(paths)
    load_run(paths, raw_run)
    assert dump(paths) == first
    assert len(first["books"]) == len(first["book_snapshots"]) == 3
    assert [r[1] for r in first["runs"]] == ["fetch", "parse"]
    assert first["load_runs"] == [(raw_run, "load", 3)]


def test_older_run_does_not_regress_books(settings: Settings) -> None:
    prepare(settings, OLD)
    paths = prepare(settings, NEW, price="£60.00".encode())
    load_run(paths, NEW)
    load_run(paths, OLD)
    row = query(
        paths,
        "SELECT price, first_seen_run_id, last_seen_run_id FROM books "
        "WHERE upc = 'a897fe39b1053632'",
    )
    assert row == [(Decimal("60.00"), OLD, NEW)]
    assert query(paths, "SELECT count(*) FROM book_snapshots") == [(6,)]
    history = query(
        paths, "SELECT run_id, price FROM book_snapshots WHERE upc = 'a897fe39b1053632' ORDER BY 1"
    )
    assert history == [(OLD, Decimal("51.77")), (NEW, Decimal("60.00"))]


def test_newer_run_updates_in_order(settings: Settings) -> None:
    prepare(settings, OLD)
    paths = prepare(settings, NEW, price="£60.00".encode())
    load_run(paths, OLD)
    load_run(paths, NEW)
    assert query(paths, "SELECT price FROM books WHERE upc = 'a897fe39b1053632'") == [
        (Decimal("60.00"),)
    ]


def corrupt_and_reparse(paths: RunPaths, run_id: str) -> None:
    """Change one saved page: the reparse rejects it (integrity) and yields one row fewer."""
    (paths.raw_dir(run_id) / "pages" / A_LIGHT).write_bytes(b"tampered")
    assert transform(paths, run_id).rows_out == 2


def test_reparsed_run_with_fewer_rows_reloads(settings: Settings, raw_run: str) -> None:
    paths = RunPaths(settings.data_dir)
    transform(paths, raw_run)
    load_run(paths, raw_run)
    corrupt_and_reparse(paths, raw_run)
    assert load_run(paths, raw_run).rows_out == 2
    first = dump(paths)
    assert len(first["book_snapshots"]) == len(first["books"]) == 2
    assert query(paths, "SELECT count(*) FROM books WHERE upc = 'a897fe39b1053632'") == [(0,)]
    load_run(paths, raw_run)
    assert dump(paths) == first


def test_book_falls_back_to_its_older_snapshot(settings: Settings) -> None:
    prepare(settings, OLD)
    paths = prepare(settings, NEW, price="£60.00".encode())
    load_run(paths, OLD)
    load_run(paths, NEW)
    corrupt_and_reparse(paths, NEW)
    load_run(paths, NEW)
    assert query(
        paths,
        "SELECT price, first_seen_run_id, last_seen_run_id FROM books "
        "WHERE upc = 'a897fe39b1053632'",
    ) == [(Decimal("51.77"), OLD, OLD)]
    assert query(paths, "SELECT run_id FROM book_snapshots WHERE upc = 'a897fe39b1053632'") == [
        (OLD,)
    ]


def test_snapshot_count_mismatch_fails_and_rolls_back(
    settings: Settings, raw_run: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = RunPaths(settings.data_dir)
    transform(paths, raw_run)
    short = load._UPSERT_SNAPSHOTS.replace("FROM read_parquet(?)", "FROM read_parquet(?) LIMIT 1")
    monkeypatch.setattr(load, "_UPSERT_SNAPSHOTS", short)
    with pytest.raises(StepError, match="boundary check failed: 1 snapshots for 3 rows"):
        load_run(paths, raw_run)
    assert query(paths, "SELECT count(*) FROM books") == [(0,)]
    assert query(paths, "SELECT count(*) FROM pipeline_runs") == [(0,)]


def test_unprocessed_run_is_refused(settings: Settings) -> None:
    with pytest.raises(StepError, match="incomplete"):
        load_run(RunPaths(settings.data_dir), OLD)


def test_books_priced_with_and_without_fx(settings: Settings, raw_run: str) -> None:
    paths = RunPaths(settings.data_dir)
    transform(paths, raw_run)
    load_run(paths, raw_run)
    sql = "SELECT price_eur, price_usd, price_brl FROM books_priced WHERE upc = 'a897fe39b1053632'"
    assert query(paths, sql) == [(None, None, None)]
    con = connect(paths.warehouse)
    for day, eur in (("2026-10-22", "1.1"), ("2026-10-23", "1.1943")):  # the latest date wins
        con.execute(
            "INSERT INTO fx_rates VALUES (?, 'GBP', 'EUR', ?, 'test', now())",
            [date.fromisoformat(day), Decimal(eur)],
        )
    con.close()
    expected = (Decimal("51.77") * Decimal("1.1943")).quantize(Decimal("0.01"))
    assert query(paths, sql) == [(expected, None, None)]


def test_timestamps_round_trip_as_utc(settings: Settings, raw_run: str) -> None:
    paths = RunPaths(settings.data_dir)
    transform(paths, raw_run)
    load_run(paths, raw_run)
    manifest = (paths.raw_dir(raw_run) / "manifest.jsonl").read_text("utf-8").splitlines()
    entries = [ManifestEntry.model_validate_json(x) for x in manifest]
    expected = {e.fetched_at.replace(tzinfo=None) for e in entries if e.kind == "product"}
    stored = {r[0] for r in query(paths, "SELECT fetched_at FROM book_snapshots")}
    assert stored == expected
    assert all(isinstance(t, datetime) and t.tzinfo is None for t in stored)
    raw_json = json.loads((paths.raw_dir(raw_run) / "run.json").read_text("utf-8"))
    started = query(paths, "SELECT started_at FROM pipeline_runs WHERE step = 'fetch'")[0][0]
    assert isinstance(started, datetime)
    assert started.isoformat() == raw_json["started_at"].removesuffix("Z").split("+")[0]
