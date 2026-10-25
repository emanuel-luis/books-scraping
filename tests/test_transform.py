import hashlib
import json
from pathlib import Path

import duckdb
import pytest
from conftest import A_LIGHT, IN_HER_WAKE, RUN_ID, site_file

from books_scraping.config import Settings
from books_scraping.runs import RunPaths, StepError
from books_scraping.transform import transform


def rows(paths: RunPaths, run_id: str = RUN_ID) -> list[tuple[object, ...]]:
    parquet = (paths.processed_dir(run_id) / "books.parquet").as_posix()
    return duckdb.sql(f"SELECT * FROM read_parquet('{parquet}') ORDER BY upc").fetchall()


def rejects(paths: RunPaths, run_id: str = RUN_ID) -> list[dict[str, str]]:
    text = (paths.processed_dir(run_id) / "rejects.jsonl").read_text("utf-8")
    return [json.loads(x) for x in text.splitlines()]


def rewrite_manifest_sha(raw: Path, rel: str, body: bytes) -> None:
    """Replace a saved page and keep the manifest consistent with it."""
    (raw / "pages" / rel).write_bytes(body)
    lines = []
    for line in (raw / "manifest.jsonl").read_text("utf-8").splitlines():
        entry = json.loads(line)
        if entry["url"].endswith(rel):
            entry["sha256"] = hashlib.sha256(body).hexdigest()
        lines.append(json.dumps(entry))
    (raw / "manifest.jsonl").write_text("\n".join(lines) + "\n", "utf-8")


def test_transform_writes_processed_run(settings: Settings, raw_run: str) -> None:
    paths = RunPaths(settings.data_dir)
    summary = transform(paths, raw_run)
    assert (summary.rows_in, summary.rows_out, summary.rows_rejected) == (3, 3, 0)
    out = paths.processed_dir(raw_run)
    assert sorted(p.name for p in out.iterdir()) == ["books.parquet", "rejects.jsonl", "run.json"]
    assert not any(p.name.startswith(".") for p in out.parent.iterdir())
    upcs = [r[0] for r in rows(paths)]
    assert len(upcs) == 3 and upcs == sorted(upcs)
    types = duckdb.sql(
        f"DESCRIBE SELECT price FROM read_parquet('{(out / 'books.parquet').as_posix()}')"
    ).fetchall()
    assert types[0][1] == "DECIMAL(10,2)"


def test_same_raw_gives_same_rows(settings: Settings, raw_run: str) -> None:
    paths = RunPaths(settings.data_dir)
    transform(paths, raw_run)
    first = rows(paths)
    transform(paths, raw_run)
    assert rows(paths) == first


def test_sha_mismatch_is_an_integrity_reject(settings: Settings, raw_run: str) -> None:
    paths = RunPaths(settings.data_dir)
    page = paths.raw_dir(raw_run) / "pages" / A_LIGHT
    page.write_bytes(page.read_bytes() + b"<!-- tampered -->")
    summary = transform(paths, raw_run)
    assert (summary.rows_out, summary.rows_rejected) == (2, 1)
    assert rejects(paths)[0]["stage"] == "integrity"


def test_missing_file_is_an_integrity_reject(settings: Settings, raw_run: str) -> None:
    paths = RunPaths(settings.data_dir)
    (paths.raw_dir(raw_run) / "pages" / A_LIGHT).unlink()
    transform(paths, raw_run)
    assert rejects(paths)[0]["stage"] == "integrity"


def test_broken_and_undecodable_pages_are_parse_rejects(settings: Settings, raw_run: str) -> None:
    paths = RunPaths(settings.data_dir)
    raw = paths.raw_dir(raw_run)
    rewrite_manifest_sha(raw, A_LIGHT, b"<html><body>maintenance</body></html>")
    rewrite_manifest_sha(raw, IN_HER_WAKE, b"\xff\xfe not utf-8")
    summary = transform(paths, raw_run)
    assert (summary.rows_out, summary.rows_rejected) == (1, 2)
    assert {r["stage"] for r in rejects(paths)} == {"parse"}


def test_invalid_values_are_validate_rejects(settings: Settings, raw_run: str) -> None:
    paths = RunPaths(settings.data_dir)
    body = site_file(A_LIGHT).replace(b"a897fe39b1053632", b"NOT-A-UPC")
    rewrite_manifest_sha(paths.raw_dir(raw_run), A_LIGHT, body)
    transform(paths, raw_run)
    (reject,) = rejects(paths)
    assert reject["stage"] == "validate" and "upc" in reject["error"]


def test_duplicate_upc_keeps_first(settings: Settings, raw_run: str) -> None:
    paths = RunPaths(settings.data_dir)
    raw = paths.raw_dir(raw_run)
    lines = (raw / "manifest.jsonl").read_text("utf-8").splitlines()
    product = next(x for x in lines if '"kind":"product"' in x)
    (raw / "manifest.jsonl").write_text("\n".join([*lines, product]) + "\n", "utf-8")
    summary = transform(paths, raw_run)
    assert (summary.rows_in, summary.rows_out, summary.duplicates) == (4, 3, 1)


def test_incomplete_raw_run_is_refused(settings: Settings, raw_run: str) -> None:
    paths = RunPaths(settings.data_dir)
    (paths.raw_dir(raw_run) / "run.json").unlink()
    with pytest.raises(StepError, match="incomplete"):
        transform(paths, raw_run)
