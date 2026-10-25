import json
from pathlib import Path

from books_scraping.runs import latest_run


def make_run(root: Path, run_id: str, run_json: str | None) -> None:
    (root / run_id).mkdir(parents=True)
    if run_json is not None:
        (root / run_id / "run.json").write_text(run_json, encoding="utf-8")


def test_latest_run_picks_the_newest_successful_run(tmp_path: Path) -> None:
    make_run(tmp_path, "20260101T000000Z", json.dumps({"status": "ok"}))
    make_run(tmp_path, "20260102T000000Z", json.dumps({"status": "failed"}))
    make_run(tmp_path, "20260103T000000Z", None)  # still running or crashed
    make_run(tmp_path, "20260104T000000Z", "{not json")
    make_run(tmp_path, "20260105T000000Z", "[]")
    assert latest_run(tmp_path) == "20260101T000000Z"


def test_latest_run_without_runs(tmp_path: Path) -> None:
    assert latest_run(tmp_path / "missing") is None
    assert latest_run(tmp_path) is None
