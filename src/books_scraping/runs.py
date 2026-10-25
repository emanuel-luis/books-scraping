"""Run ids, the on-disk layout of the layers and the latest-run lookup."""

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class StepError(RuntimeError):
    """A pipeline step failed; the CLI turns it into exit code 1."""


def utc_now() -> datetime:
    return datetime.now(UTC)


def naive_utc(value: datetime) -> datetime:
    """UTC wall-clock time without tzinfo: the Parquet and DuckDB columns are UTC TIMESTAMPs."""
    return value.astimezone(UTC).replace(tzinfo=None)


def new_run_id(now: datetime | None = None) -> str:
    """UTC start time as YYYYMMDDTHHMMSSZ; sorts in time order."""
    return (now or utc_now()).astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


@dataclass(frozen=True)
class RunPaths:
    data_dir: Path

    @property
    def raw_root(self) -> Path:
        return self.data_dir / "raw"

    @property
    def processed_root(self) -> Path:
        return self.data_dir / "processed"

    @property
    def warehouse(self) -> Path:
        return self.data_dir / "warehouse.duckdb"

    def raw_dir(self, run_id: str) -> Path:
        return self.raw_root / run_id

    def processed_dir(self, run_id: str) -> Path:
        return self.processed_root / run_id


def _succeeded(run_dir: Path) -> bool:
    """The run finished (run.json written last) and its step reported ok."""
    try:
        summary = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(summary, dict) and summary.get("status") == "ok"


def latest_run(root: Path) -> str | None:
    """Newest run directory under root whose step finished with status ok."""
    if not root.is_dir():
        return None
    done = sorted(p.name for p in root.iterdir() if _succeeded(p))
    return done[-1] if done else None


class _StepLogger(logging.LoggerAdapter[logging.Logger]):
    def process(self, msg: Any, kwargs: Any) -> tuple[Any, Any]:
        extra = self.extra or {}
        return f"run_id={extra['run_id']} step={extra['step']} {msg}", kwargs


def step_logger(run_id: str, step: str) -> logging.LoggerAdapter[logging.Logger]:
    return _StepLogger(logging.getLogger("books_scraping"), {"run_id": run_id, "step": step})
