import subprocess
import sys
from functools import partial

import pytest
from conftest import FakeSite
from test_fx import transport as fx_transport
from typer.testing import CliRunner

from books_scraping import __version__, cli
from books_scraping.config import Settings
from books_scraping.fetch import crawl
from books_scraping.fx import load_fx

runner = CliRunner()


@pytest.fixture(autouse=True)
def data_env(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOOKS_DATA_DIR", str(settings.data_dir))
    monkeypatch.setenv("BOOKS_MIN_INTERVAL_S", "0")
    monkeypatch.setattr(
        cli, "crawl", partial(crawl, transport=FakeSite().transport, sleep=lambda _s: None)
    )
    monkeypatch.setattr(
        cli, "load_fx", partial(load_fx, transport=fx_transport([]), sleep=lambda _s: None)
    )


def test_help_and_version() -> None:
    result = runner.invoke(cli.app, ["--help"])
    assert result.exit_code == 0 and "run" in result.output
    result = runner.invoke(cli.app, ["--version"])
    assert result.exit_code == 0 and result.output.strip() == __version__


def test_steps_on_a_raw_run(settings: Settings, raw_run: str) -> None:
    assert runner.invoke(cli.app, ["parse"]).exit_code == 0
    assert (settings.data_dir / "processed" / raw_run / "books.parquet").is_file()
    assert runner.invoke(cli.app, ["load", "--run-id", raw_run]).exit_code == 0
    assert runner.invoke(cli.app, ["fx"]).exit_code == 0
    result = runner.invoke(cli.app, ["stats"])
    assert result.exit_code == 0
    assert "books: 3" in result.output and "fx_rates: 3" in result.output
    assert "  Poetry: 1" in result.output


def test_fetch_prints_the_run_id(settings: Settings) -> None:
    result = runner.invoke(cli.app, ["fetch", "--limit", "1"])
    assert result.exit_code == 0
    run_id = result.stdout.strip()
    assert (settings.data_dir / "raw" / run_id / "run.json").is_file()


def test_run_end_to_end_and_reload_is_stable(settings: Settings) -> None:
    result = runner.invoke(cli.app, ["run", "--max-pages", "1", "--fx"])
    assert result.exit_code == 0, result.output
    run_id = result.stdout.strip().splitlines()[-1]
    before = runner.invoke(cli.app, ["stats"]).stdout
    assert runner.invoke(cli.app, ["load", "--run-id", run_id]).exit_code == 0
    after = runner.invoke(cli.app, ["stats"]).stdout
    assert before.split("last pipeline")[0] == after.split("last pipeline")[0]
    assert "books: 2" in after


def test_missing_runs_exit_1() -> None:
    for command in (["parse"], ["load"], ["stats"]):
        result = runner.invoke(cli.app, command)
        assert result.exit_code == 1, command


def test_failed_step_exits_1(settings: Settings, raw_run: str) -> None:
    (settings.data_dir / "raw" / raw_run / "run.json").unlink()
    result = runner.invoke(cli.app, ["parse", "--run-id", raw_run])
    assert result.exit_code == 1 and "incomplete" in result.output


def test_failed_crawl_exits_1(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        cli, "crawl", partial(crawl, transport=FakeSite(pages={}).transport, sleep=lambda _s: None)
    )
    assert runner.invoke(cli.app, ["fetch"]).exit_code == 1


def test_python_dash_m_runs_the_cli() -> None:
    out = subprocess.run(
        [sys.executable, "-m", "books_scraping", "--version"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert out.returncode == 0 and out.stdout.strip() == __version__
