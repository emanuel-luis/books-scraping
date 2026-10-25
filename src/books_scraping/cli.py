"""Typer CLI: books-scraping fetch | parse | load | fx | run | stats."""

import logging
import sys
import time
from collections.abc import Callable
from typing import Annotated

import typer

from books_scraping import __version__
from books_scraping.config import Settings
from books_scraping.fetch import crawl
from books_scraping.fx import load_fx
from books_scraping.load import connect, load_run
from books_scraping.models import StepSummary
from books_scraping.runs import RunPaths, StepError, latest_run, new_run_id
from books_scraping.transform import transform

app = typer.Typer(add_completion=False, no_args_is_help=True, help="books.toscrape.com pipeline.")

Limit = Annotated[int | None, typer.Option(min=1, help="Stop after N products.")]
MaxPages = Annotated[int | None, typer.Option(min=1, help="Stop after N listing pages.")]
RunId = Annotated[str | None, typer.Option(help="Run to use; default: the latest.")]


class _UtcFormatter(logging.Formatter):
    converter: Callable[[float | None], time.struct_time] = time.gmtime


def _version(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit


@app.callback()
def main(
    version: Annotated[bool, typer.Option("--version", callback=_version, is_eager=True)] = False,
) -> None:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(_UtcFormatter("%(asctime)sZ %(levelname)s %(message)s"))
    logging.basicConfig(level=Settings().log_level.upper(), handlers=[handler], force=True)
    logging.getLogger("httpx").setLevel(logging.WARNING)  # one INFO line per request is noise


def _step(fn: Callable[[], StepSummary]) -> StepSummary:
    """Run a step; a failure becomes exit code 1."""
    try:
        summary = fn()
    except StepError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    if summary.status != "ok":
        typer.echo(f"error: step {summary.step} failed (run {summary.run_id})", err=True)
        raise typer.Exit(1)
    return summary


def _resolve(root_run: str | None, root: str, paths: RunPaths) -> str:
    run_id = root_run or latest_run(paths.raw_root if root == "raw" else paths.processed_root)
    if run_id is None:
        typer.echo(f"error: no successful {root} run found under {paths.data_dir}", err=True)
        raise typer.Exit(1)
    return run_id


@app.command()
def fetch(limit: Limit = None, max_pages: MaxPages = None) -> None:
    """Crawl the site into a new raw run and print its run_id."""
    summary = _step(lambda: crawl(Settings(), limit=limit, max_pages=max_pages))
    typer.echo(summary.run_id)


@app.command()
def parse(run_id: RunId = None) -> None:
    """Raw run -> processed run (default: latest successful raw run)."""
    paths = RunPaths(Settings().data_dir)
    run_id = _resolve(run_id, "raw", paths)
    _step(lambda: transform(paths, run_id))


@app.command()
def load(run_id: RunId = None) -> None:
    """Processed run -> DuckDB (default: latest processed run)."""
    paths = RunPaths(Settings().data_dir)
    run_id = _resolve(run_id, "processed", paths)
    _step(lambda: load_run(paths, run_id))


@app.command()
def fx() -> None:
    """Load FX rates for the currencies in books."""
    settings = Settings()
    _step(lambda: load_fx(settings, new_run_id()))


@app.command()
def run(
    limit: Limit = None,
    max_pages: MaxPages = None,
    with_fx: Annotated[bool, typer.Option("--fx/--no-fx")] = False,
) -> None:
    """fetch -> parse -> load (-> fx)."""
    settings = Settings()
    paths = RunPaths(settings.data_dir)
    run_id = _step(lambda: crawl(settings, limit=limit, max_pages=max_pages)).run_id
    _step(lambda: transform(paths, run_id))
    _step(lambda: load_run(paths, run_id))
    if with_fx:
        _step(lambda: load_fx(settings, run_id))
    typer.echo(run_id)


@app.command()
def stats() -> None:
    """Row counts per table, the last pipeline runs and the top categories."""
    paths = RunPaths(Settings().data_dir)
    if not paths.warehouse.is_file():
        typer.echo(f"error: no warehouse at {paths.warehouse}", err=True)
        raise typer.Exit(1)
    con = connect(paths.warehouse)
    try:
        typer.echo("rows per table")
        for table in ("books", "book_snapshots", "pipeline_runs", "fx_rates"):
            row = con.execute(f"SELECT count(*) FROM {table}").fetchone()
            typer.echo(f"  {table}: {row[0] if row else 0}")
        typer.echo("last pipeline runs")
        for r in con.execute(
            "SELECT run_id, step, status, rows_in, rows_out, rows_rejected FROM pipeline_runs "
            "ORDER BY run_id DESC, step LIMIT 10"
        ).fetchall():
            typer.echo(f"  {r[0]} {r[1]:<6} {r[2]:<6} in={r[3]} out={r[4]} rejected={r[5]}")
        typer.echo("books per category (top 10)")
        for category, n in con.execute(
            "SELECT category, count(*) AS n FROM books GROUP BY category "
            "ORDER BY n DESC, category LIMIT 10"
        ).fetchall():
            typer.echo(f"  {category}: {n}")
    finally:
        con.close()
