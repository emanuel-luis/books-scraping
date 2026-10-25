from decimal import Decimal

import httpx
import pytest
from conftest import FIXTURES

from books_scraping.config import Settings
from books_scraping.fx import load_fx, parse_rates
from books_scraping.load import connect, load_run
from books_scraping.runs import RunPaths, StepError
from books_scraping.transform import transform

BODY = (FIXTURES / "frankfurter_latest.json").read_text("utf-8")


def transport(requests: list[httpx.Request], status: int = 200) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(status, text=BODY)

    return httpx.MockTransport(handler)


def test_parse_rates_keeps_decimal_text() -> None:
    rates = parse_rates(BODY, ["EUR", "USD", "BRL", "JPY"])
    assert {r.quote: r.rate for r in rates} == {
        "EUR": Decimal("1.1943"),
        "USD": Decimal("1.3368"),
        "BRL": Decimal("6.7462"),
    }
    assert {r.base for r in rates} == {"GBP"} and rates[0].rate_date.isoformat() == "2026-10-23"


def loaded(settings: Settings, raw_run: str) -> RunPaths:
    paths = RunPaths(settings.data_dir)
    transform(paths, raw_run)
    load_run(paths, raw_run)
    return paths


def count(paths: RunPaths) -> int:
    con = connect(paths.warehouse)
    try:
        row = con.execute("SELECT count(*) FROM fx_rates").fetchone()
        return int(row[0]) if row else -1
    finally:
        con.close()


def test_load_fx_is_idempotent(settings: Settings, raw_run: str) -> None:
    paths = loaded(settings, raw_run)
    requests: list[httpx.Request] = []
    for _ in range(2):
        summary = load_fx(settings, raw_run, transport=transport(requests), sleep=lambda _s: None)
    assert summary.rows_out == 3 and count(paths) == 3
    assert str(requests[0].url) == (
        "https://api.frankfurter.dev/v1/latest?base=GBP&symbols=EUR,USD,BRL"
    )


def test_no_books_means_no_requests(settings: Settings) -> None:
    requests: list[httpx.Request] = []
    summary = load_fx(settings, "-", transport=transport(requests))
    assert requests == [] and summary.rows_out == 0


def test_fx_error_status_fails_the_step(settings: Settings, raw_run: str) -> None:
    loaded(settings, raw_run)
    with pytest.raises(StepError, match="422"):
        load_fx(settings, raw_run, transport=transport([], 422), sleep=lambda _s: None)


def test_fx_transport_error_fails_the_step(settings: Settings, raw_run: str) -> None:
    loaded(settings, raw_run)

    def boom(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    with pytest.raises(StepError, match="failed"):
        load_fx(settings, raw_run, transport=httpx.MockTransport(boom), sleep=lambda _s: None)
