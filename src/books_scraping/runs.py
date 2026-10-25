"""Run ids, the on-disk layout of the layers and the latest-run lookup."""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class StepError(RuntimeError):
    """A pipeline step failed; the CLI turns it into exit code 1."""


def utc_now() -> datetime:
    return datetime.now(UTC)


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


def latest_run(root: Path) -> str | None:
    """Newest run directory under root that has a run.json (a complete run)."""
    if not root.is_dir():
        return None
    done = sorted(p.name for p in root.iterdir() if (p / "run.json").is_file())
    return done[-1] if done else None


class _StepLogger(logging.LoggerAdapter[logging.Logger]):
    def process(self, msg: Any, kwargs: Any) -> tuple[Any, Any]:
        extra = self.extra or {}
        return f"run_id={extra['run_id']} step={extra['step']} {msg}", kwargs


def step_logger(run_id: str, step: str) -> logging.LoggerAdapter[logging.Logger]:
    return _StepLogger(logging.getLogger("books_scraping"), {"run_id": run_id, "step": step})
