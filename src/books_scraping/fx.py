"""Optional FX step: Frankfurter (ECB reference rates) -> fx_rates."""

import json
import time
from collections.abc import Callable
from datetime import date
from decimal import Decimal

import httpx

from books_scraping.config import Settings
from books_scraping.fetch import Fetcher
from books_scraping.load import connect, naive_utc
from books_scraping.models import FxRate, StepSummary
from books_scraping.runs import RunPaths, StepError, step_logger, utc_now


def parse_rates(text: str, quotes: list[str]) -> list[FxRate]:
    """Parse a Frankfurter /latest body; rates go from JSON text to Decimal, never via float."""
    data = json.loads(text, parse_float=Decimal)
    fetched_at = utc_now()
    return [
        FxRate(
            rate_date=date.fromisoformat(data["date"]),
            base=data["base"],
            quote=q,
            rate=data["rates"][q],
            fetched_at=fetched_at,
        )
        for q in quotes
        if q in data["rates"]
    ]


def load_fx(
    settings: Settings,
    run_id: str,
    *,
    transport: httpx.BaseTransport | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> StepSummary:
    started = utc_now()
    log = step_logger(run_id, "fx")
    quotes = [q.strip().upper() for q in settings.fx_quotes.split(",") if q.strip()]
    con = connect(RunPaths(settings.data_dir).warehouse)
    rates: list[FxRate] = []
    try:
        currencies = [r[0] for r in con.execute("SELECT DISTINCT currency FROM books").fetchall()]
        with Fetcher(settings, transport=transport, sleep=sleep) as fetcher:
            for base in currencies:
                symbols = ",".join(q for q in quotes if q != base)
                url = f"{settings.fx_url.rstrip('/')}/latest?base={base}&symbols={symbols}"
                try:
                    response = fetcher.get(url)
                except httpx.TransportError as exc:
                    raise StepError(f"fx request failed: {exc}") from exc
                if response.status_code != 200:
                    raise StepError(f"fx request answered {response.status_code}: {url}")
                rates += parse_rates(response.text, quotes)
        if rates:
            con.executemany(
                """INSERT INTO fx_rates VALUES (?,?,?,?,?,?)
               ON CONFLICT (rate_date, base, quote) DO UPDATE SET
                   rate = excluded.rate, source = excluded.source,
                   fetched_at = excluded.fetched_at""",
                [
                    (r.rate_date, r.base, r.quote, r.rate, r.source, naive_utc(r.fetched_at))
                    for r in rates
                ],
            )
    finally:
        con.close()
    log.info("%d rates loaded", len(rates))
    return StepSummary(
        run_id=run_id,
        step="fx",
        status="ok",
        started_at=started,
        finished_at=utc_now(),
        rows_in=len(rates),
        rows_out=len(rates),
    )
